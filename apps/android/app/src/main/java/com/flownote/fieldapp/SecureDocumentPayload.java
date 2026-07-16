package com.flownote.fieldapp;

import java.io.File;

public final class SecureDocumentPayload {
    public final File file;
    public final String mediaKind;
    public final String mimeType;
    public final int maxPdfPages;
    public final int autoCloseSeconds;

    SecureDocumentPayload(
            File file,
            String mediaKind,
            String mimeType,
            int maxPdfPages,
            int autoCloseSeconds
    ) {
        this.file = file;
        this.mediaKind = mediaKind;
        this.mimeType = mimeType;
        this.maxPdfPages = maxPdfPages;
        this.autoCloseSeconds = autoCloseSeconds;
    }
}
