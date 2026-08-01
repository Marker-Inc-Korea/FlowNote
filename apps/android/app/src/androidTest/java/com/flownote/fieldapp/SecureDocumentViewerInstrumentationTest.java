package com.flownote.fieldapp;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.ComponentName;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.pm.PackageManager;
import android.test.InstrumentationTestCase;
import android.view.WindowManager;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageView;

import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

public final class SecureDocumentViewerInstrumentationTest extends InstrumentationTestCase {
    public void testViewerIsNotExportedAndSetsSecureWindowFlag() throws Exception {
        Instrumentation instrumentation = getInstrumentation();
        ActivityInfo info = instrumentation.getTargetContext().getPackageManager().getActivityInfo(
                new ComponentName(instrumentation.getTargetContext(), SecureDocumentViewerActivity.class),
                PackageManager.GET_META_DATA
        );
        assertFalse(info.exported);

        Intent intent = new Intent(instrumentation.getTargetContext(), SecureDocumentViewerActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        Activity activity = instrumentation.startActivitySync(intent);
        try {
            int flags = activity.getWindow().getAttributes().flags;
            assertTrue((flags & WindowManager.LayoutParams.FLAG_SECURE) != 0);
        } finally {
            activity.finish();
        }
    }

    public void testStartupCleanupRemovesOpaqueInternalCacheFile() throws Exception {
        java.io.File file = SecureViewerFiles.create(getInstrumentation().getTargetContext());
        assertTrue(file.createNewFile() || file.exists());
        SecureViewerFiles.clean(getInstrumentation().getTargetContext());
        assertFalse(file.exists());
    }

    public void testCiphertextCannotBeDecryptedWithDifferentKey() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256);
        SecretKey firstKey = generator.generateKey();
        SecretKey differentKey = generator.generateKey();
        String ciphertext = new CryptoBox(firstKey).encrypt("현장 기록 원문");

        try {
            new CryptoBox(differentKey).decrypt(ciphertext);
            fail("잘못된 키 복호화가 성공하면 안 됩니다.");
        } catch (IllegalStateException expected) {
            assertTrue(expected.getMessage().contains("로컬 보안 키"));
        }
    }

    public void testMainFieldControlsUseMinimumTouchTargetsAndLiveStatus() {
        Intent intent = new Intent(getInstrumentation().getTargetContext(), MainActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        Activity activity = getInstrumentation().startActivitySync(intent);
        try {
            UiAudit audit = new UiAudit();
            inspect(activity.getWindow().getDecorView(), audit);
            int minimumPixels = Math.round(
                    56 * activity.getResources().getDisplayMetrics().density
            );
            assertTrue("화면에 주요 작업 버튼이 있어야 합니다.", audit.buttonCount >= 8);
            assertTrue("56dp보다 작은 버튼이 있습니다.", audit.smallestButtonHeight >= minimumPixels);
            assertTrue("전송·작업 상태 live region이 필요합니다.", audit.liveRegionCount >= 3);
            assertTrue("선택 사진 미리보기 설명이 필요합니다.", audit.photoPreviewFound);
            assertTrue("전송 상태 아이콘과 한글 설명이 필요합니다.", audit.outboxStatusIconFound);
        } finally {
            activity.finish();
        }
    }

    private static void inspect(View view, UiAudit audit) {
        if (view instanceof Button) {
            audit.buttonCount++;
            audit.smallestButtonHeight = Math.min(
                    audit.smallestButtonHeight,
                    ((Button) view).getMinHeight()
            );
        }
        if (view.getAccessibilityLiveRegion() == View.ACCESSIBILITY_LIVE_REGION_POLITE) {
            audit.liveRegionCount++;
        }
        if (view instanceof ImageView
                && "선택한 현장 사진 미리보기".contentEquals(view.getContentDescription())) {
            audit.photoPreviewFound = true;
        }
        if (view instanceof ImageView && view.getContentDescription() != null
                && view.getContentDescription().toString().matches(
                "(전송 완료|전송 대기|전송 실패|보안 저장소 오류) 아이콘"
        )) {
            audit.outboxStatusIconFound = true;
        }
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int index = 0; index < group.getChildCount(); index++) {
                inspect(group.getChildAt(index), audit);
            }
        }
    }

    private static final class UiAudit {
        int buttonCount;
        int smallestButtonHeight = Integer.MAX_VALUE;
        int liveRegionCount;
        boolean photoPreviewFound;
        boolean outboxStatusIconFound;
    }
}
