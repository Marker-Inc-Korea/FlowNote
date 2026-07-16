package com.flownote.fieldapp;

import android.content.Context;

import java.io.File;
import java.io.IOException;
import java.util.UUID;

public final class SecureViewerFiles {
    private static final String DIRECTORY = "secure-document-viewer";

    private SecureViewerFiles() {
    }

    public static File create(Context context) throws IOException {
        File directory = directory(context);
        if (!directory.exists() && !directory.mkdirs()) {
            throw new IOException("보안 열람 임시 영역을 만들 수 없습니다.");
        }
        return new File(directory, UUID.randomUUID().toString());
    }

    public static void clean(Context context) {
        File[] files = directory(context).listFiles();
        if (files == null) {
            return;
        }
        for (File file : files) {
            delete(file);
        }
    }

    public static void delete(File file) {
        if (file == null || !file.exists()) {
            return;
        }
        if (!file.delete()) {
            file.deleteOnExit();
        }
    }

    static File directory(Context context) {
        return new File(context.getCacheDir(), DIRECTORY);
    }
}
