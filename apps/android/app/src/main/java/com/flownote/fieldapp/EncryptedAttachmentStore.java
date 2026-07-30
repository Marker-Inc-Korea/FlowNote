package com.flownote.fieldapp;

import android.content.ContentResolver;
import android.content.Context;
import android.net.Uri;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.GeneralSecurityException;
import javax.crypto.Cipher;
import javax.crypto.CipherInputStream;
import javax.crypto.CipherOutputStream;

final class EncryptedAttachmentStore {
    private static final String PREFIX = "encfile:";
    private final File directory;
    private final CryptoBox cryptoBox;

    EncryptedAttachmentStore(Context context, CryptoBox cryptoBox) {
        directory = new File(context.getFilesDir(), "outbox-attachments");
        this.cryptoBox = cryptoBox;
    }

    String importFrom(ContentResolver resolver, Uri uri, String localId) throws IOException {
        if (!directory.exists() && !directory.mkdirs()) {
            throw new IOException("암호화 첨부 저장소를 만들 수 없습니다.");
        }
        File destination = new File(directory, localId + ".bin");
        try {
            Cipher cipher = cryptoBox.newEncryptCipher();
            try (InputStream input = new BufferedInputStream(requireInput(resolver, uri));
                 OutputStream raw = new BufferedOutputStream(new FileOutputStream(destination))) {
                byte[] iv = cipher.getIV();
                raw.write(iv.length);
                raw.write(iv);
                try (CipherOutputStream output = new CipherOutputStream(raw, cipher)) {
                    byte[] buffer = new byte[8192];
                    int read;
                    while ((read = input.read(buffer)) >= 0) {
                        output.write(buffer, 0, read);
                    }
                }
            }
            return PREFIX + destination.getName();
        } catch (GeneralSecurityException exc) {
            throw new IOException("첨부를 암호화할 수 없습니다.", exc);
        }
    }

    InputStream open(String reference) throws IOException {
        if (reference == null || !reference.startsWith(PREFIX)) {
            throw new IOException("암호화 첨부 참조가 아닙니다.");
        }
        File source = new File(directory, reference.substring(PREFIX.length()));
        FileInputStream raw = new FileInputStream(source);
        try {
            int ivLength = raw.read();
            if (ivLength < 12 || ivLength > 32) {
                throw new IOException("암호화 첨부 헤더가 손상되었습니다.");
            }
            byte[] iv = new byte[ivLength];
            if (raw.read(iv) != ivLength) {
                throw new IOException("암호화 첨부 IV가 손상되었습니다.");
            }
            return new CipherInputStream(new BufferedInputStream(raw), cryptoBox.newDecryptCipher(iv));
        } catch (GeneralSecurityException | IOException exc) {
            raw.close();
            throw exc instanceof IOException ? (IOException) exc : new IOException(exc);
        }
    }

    void delete(String reference) {
        if (reference == null || !reference.startsWith(PREFIX)) {
            return;
        }
        File target = new File(directory, reference.substring(PREFIX.length()));
        if (target.isFile() && !target.delete()) {
            target.deleteOnExit();
        }
    }

    private static InputStream requireInput(ContentResolver resolver, Uri uri) throws IOException {
        InputStream input = resolver.openInputStream(uri);
        if (input == null) {
            throw new IOException("선택한 사진을 열 수 없습니다.");
        }
        return input;
    }
}
