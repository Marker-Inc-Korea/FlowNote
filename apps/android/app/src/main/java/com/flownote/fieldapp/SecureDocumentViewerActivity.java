package com.flownote.fieldapp;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.pdf.PdfRenderer;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelFileDescriptor;
import android.view.MotionEvent;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class SecureDocumentViewerActivity extends Activity {
    public static final String EXTRA_SERVER_URL = "server_url";
    public static final String EXTRA_ACCESS_TOKEN = "access_token";
    public static final String EXTRA_DOCUMENT_ID = "document_id";
    public static final String EXTRA_VERSION_ID = "version_id";
    public static final String EXTRA_TITLE = "title";

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable autoClose = this::closeSecurely;

    private LinearLayout content;
    private TextView status;
    private File temporaryFile;
    private SecureDocumentPayload payload;
    private ParcelFileDescriptor pdfDescriptor;
    private PdfRenderer pdfRenderer;
    private Bitmap renderedBitmap;
    private int pdfPageIndex;
    private boolean ready;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        buildUi();
        loadDocument();
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(20, 18, 20, 18);
        root.setBackgroundColor(Color.WHITE);

        LinearLayout bar = new LinearLayout(this);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        TextView title = new TextView(this);
        title.setText(getIntent().getStringExtra(EXTRA_TITLE));
        title.setTextSize(19);
        title.setTextColor(Color.parseColor("#1F2A30"));
        bar.addView(title, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        Button close = new Button(this);
        close.setText("열람 종료");
        close.setAllCaps(false);
        close.setOnClickListener(view -> closeSecurely());
        bar.addView(close);
        root.addView(bar);

        status = new TextView(this);
        status.setText("보안 문서를 확인하는 중...");
        status.setTextColor(Color.parseColor("#3D4852"));
        status.setPadding(0, 8, 0, 8);
        root.addView(status);

        ScrollView scroll = new ScrollView(this);
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(content);
        root.addView(scroll, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(root);
    }

    private void loadDocument() {
        String serverUrl = getIntent().getStringExtra(EXTRA_SERVER_URL);
        String token = getIntent().getStringExtra(EXTRA_ACCESS_TOKEN);
        String documentId = getIntent().getStringExtra(EXTRA_DOCUMENT_ID);
        String versionId = getIntent().getStringExtra(EXTRA_VERSION_ID);
        if (serverUrl == null || token == null || documentId == null || versionId == null) {
            fail("열람 요청 정보가 올바르지 않습니다.");
            return;
        }
        executor.execute(() -> {
            try {
                temporaryFile = SecureViewerFiles.create(this);
                FlowNoteApiClient client = new FlowNoteApiClient(serverUrl, getContentResolver());
                client.setAccessToken(token);
                SecureDocumentPayload downloaded = client.downloadSecureDocument(
                        documentId, versionId, temporaryFile);
                handler.post(() -> show(downloaded));
            } catch (Exception exc) {
                handler.post(() -> fail("문서 열람 실패: " + UserErrorMessage.from(exc)));
            }
        });
    }

    private void show(SecureDocumentPayload downloaded) {
        payload = downloaded;
        try {
            if ("PDF".equals(downloaded.mediaKind)) {
                showPdf();
            } else if ("IMAGE".equals(downloaded.mediaKind)) {
                showImage();
            } else if ("TEXT".equals(downloaded.mediaKind)) {
                showText();
            } else {
                throw new IllegalArgumentException("지원하지 않는 문서 형식입니다.");
            }
            ready = true;
            status.setText("앱 내부 보안 열람 중 · 외부 열기와 공유가 차단됩니다.");
            resetAutoClose();
        } catch (Exception exc) {
            fail("문서가 손상되었거나 표시할 수 없습니다.");
        }
    }

    private void showImage() {
        Bitmap bitmap = BitmapFactory.decodeFile(payload.file.getAbsolutePath());
        if (bitmap == null) {
            throw new IllegalArgumentException("Image decode failed");
        }
        renderedBitmap = bitmap;
        ImageView image = new ImageView(this);
        image.setAdjustViewBounds(true);
        image.setScaleType(ImageView.ScaleType.FIT_CENTER);
        image.setImageBitmap(bitmap);
        content.addView(image);
    }

    private void showText() throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (FileInputStream input = new FileInputStream(payload.file)) {
            byte[] buffer = new byte[16 * 1024];
            int read;
            while ((read = input.read(buffer)) >= 0) {
                output.write(buffer, 0, read);
            }
        }
        TextView text = new TextView(this);
        text.setText(new String(output.toByteArray(), StandardCharsets.UTF_8));
        text.setTextSize(16);
        text.setTextColor(Color.parseColor("#1F2A30"));
        text.setTextIsSelectable(false);
        content.addView(text);
    }

    private void showPdf() throws Exception {
        pdfDescriptor = ParcelFileDescriptor.open(payload.file, ParcelFileDescriptor.MODE_READ_ONLY);
        pdfRenderer = new PdfRenderer(pdfDescriptor);
        if (pdfRenderer.getPageCount() < 1 || pdfRenderer.getPageCount() > payload.maxPdfPages) {
            throw new IllegalArgumentException("PDF page limit exceeded");
        }
        pdfPageIndex = 0;
        renderPdfPage();
    }

    private void renderPdfPage() {
        content.removeAllViews();
        try (PdfRenderer.Page page = pdfRenderer.openPage(pdfPageIndex)) {
            int targetWidth = Math.max(720, getResources().getDisplayMetrics().widthPixels - 40);
            int targetHeight = Math.max(1, targetWidth * page.getHeight() / page.getWidth());
            Bitmap bitmap = Bitmap.createBitmap(targetWidth, targetHeight, Bitmap.Config.ARGB_8888);
            bitmap.eraseColor(Color.WHITE);
            page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY);
            if (renderedBitmap != null) {
                renderedBitmap.recycle();
            }
            renderedBitmap = bitmap;
            ImageView image = new ImageView(this);
            image.setAdjustViewBounds(true);
            image.setImageBitmap(bitmap);
            content.addView(image);

            LinearLayout controls = new LinearLayout(this);
            Button previous = new Button(this);
            previous.setText("이전");
            previous.setEnabled(pdfPageIndex > 0);
            previous.setOnClickListener(view -> {
                pdfPageIndex--;
                renderPdfPage();
                resetAutoClose();
            });
            Button next = new Button(this);
            next.setText("다음");
            next.setEnabled(pdfPageIndex + 1 < pdfRenderer.getPageCount());
            next.setOnClickListener(view -> {
                pdfPageIndex++;
                renderPdfPage();
                resetAutoClose();
            });
            TextView pageLabel = new TextView(this);
            pageLabel.setText((pdfPageIndex + 1) + " / " + pdfRenderer.getPageCount() + "쪽");
            controls.addView(previous);
            controls.addView(pageLabel);
            controls.addView(next);
            content.addView(controls);
        }
    }

    @Override
    public boolean dispatchTouchEvent(MotionEvent event) {
        if (ready && event.getActionMasked() == MotionEvent.ACTION_DOWN) {
            resetAutoClose();
        }
        return super.dispatchTouchEvent(event);
    }

    private void resetAutoClose() {
        handler.removeCallbacks(autoClose);
        int seconds = payload == null ? 300 : Math.max(15, payload.autoCloseSeconds);
        handler.postDelayed(autoClose, seconds * 1000L);
    }

    private void fail(String message) {
        ready = false;
        status.setText(message);
        handler.postDelayed(this::closeSecurely, 2500L);
    }

    private void closeSecurely() {
        cleanup();
        finish();
    }

    private void cleanup() {
        handler.removeCallbacks(autoClose);
        if (renderedBitmap != null) {
            renderedBitmap.recycle();
            renderedBitmap = null;
        }
        if (pdfRenderer != null) {
            pdfRenderer.close();
            pdfRenderer = null;
        }
        try {
            if (pdfDescriptor != null) {
                pdfDescriptor.close();
            }
        } catch (Exception ignored) {
            // Best-effort close followed by deletion.
        }
        pdfDescriptor = null;
        SecureViewerFiles.delete(temporaryFile);
        temporaryFile = null;
    }

    @Override
    protected void onStop() {
        super.onStop();
        if (!isChangingConfigurations()) {
            closeSecurely();
        }
    }

    @Override
    protected void onDestroy() {
        cleanup();
        executor.shutdownNow();
        super.onDestroy();
    }
}
