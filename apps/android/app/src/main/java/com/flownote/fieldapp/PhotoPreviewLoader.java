package com.flownote.fieldapp;

import android.content.ContentResolver;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.os.Build;
import android.util.Size;

import java.io.IOException;
import java.io.InputStream;

final class PhotoPreviewLoader {
    private PhotoPreviewLoader() {
    }

    static Bitmap load(
            ContentResolver resolver,
            Uri photoUri,
            int targetWidth,
            int targetHeight
    ) throws IOException {
        if (Build.VERSION.SDK_INT >= 29) {
            return resolver.loadThumbnail(
                    photoUri,
                    new Size(targetWidth, targetHeight),
                    null
            );
        }

        BitmapFactory.Options bounds = new BitmapFactory.Options();
        bounds.inJustDecodeBounds = true;
        try (InputStream input = requireInput(resolver, photoUri)) {
            BitmapFactory.decodeStream(input, null, bounds);
        }
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) {
            throw new IOException("사진 크기를 확인할 수 없습니다.");
        }

        BitmapFactory.Options sampled = new BitmapFactory.Options();
        sampled.inSampleSize = sampleSize(
                bounds.outWidth,
                bounds.outHeight,
                targetWidth,
                targetHeight
        );
        try (InputStream input = requireInput(resolver, photoUri)) {
            Bitmap bitmap = BitmapFactory.decodeStream(input, null, sampled);
            if (bitmap == null) {
                throw new IOException("사진 미리보기를 만들 수 없습니다.");
            }
            return bitmap;
        }
    }

    static int sampleSize(int width, int height, int targetWidth, int targetHeight) {
        int sample = 1;
        while (width / (sample * 2) >= targetWidth
                && height / (sample * 2) >= targetHeight) {
            sample *= 2;
        }
        return sample;
    }

    private static InputStream requireInput(ContentResolver resolver, Uri photoUri)
            throws IOException {
        InputStream input = resolver.openInputStream(photoUri);
        if (input == null) {
            throw new IOException("사진을 열 수 없습니다.");
        }
        return input;
    }
}
