package com.flownote.fieldapp;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;

import java.io.IOException;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

final class CryptoBox {
    private static final String KEY_ALIAS = "flownote.android.local.v1";
    private static final String PREFIX = "enc:v1:";

    private final SecretKey key;

    CryptoBox(SecretKey key) {
        if (key == null) {
            throw new IllegalArgumentException("단말 보안 키가 필요합니다.");
        }
        this.key = key;
    }

    CryptoBox() {
        try {
            KeyStore keyStore = KeyStore.getInstance("AndroidKeyStore");
            keyStore.load(null);
            SecretKey existing = (SecretKey) keyStore.getKey(KEY_ALIAS, null);
            if (existing != null) {
                key = existing;
                return;
            }
            KeyGenerator generator = KeyGenerator.getInstance(
                    KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            generator.init(new KeyGenParameterSpec.Builder(
                    KEY_ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(256)
                    .build());
            key = generator.generateKey();
        } catch (GeneralSecurityException | IOException exc) {
            throw new IllegalStateException("단말 보안 키를 사용할 수 없습니다.", exc);
        }
    }

    boolean isEncrypted(String value) {
        return value != null && value.startsWith(PREFIX);
    }

    String encrypt(String plainText) {
        if (plainText == null || isEncrypted(plainText)) {
            return plainText;
        }
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key);
            byte[] encrypted = cipher.doFinal(plainText.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            return PREFIX + Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + ":"
                    + Base64.encodeToString(encrypted, Base64.NO_WRAP);
        } catch (GeneralSecurityException exc) {
            throw new IllegalStateException("로컬 데이터를 암호화할 수 없습니다.", exc);
        }
    }

    String decrypt(String protectedText) {
        if (protectedText == null || !isEncrypted(protectedText)) {
            return protectedText;
        }
        try {
            String[] parts = protectedText.substring(PREFIX.length()).split(":", 2);
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key,
                    new GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)));
            byte[] plain = cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP));
            return new String(plain, java.nio.charset.StandardCharsets.UTF_8);
        } catch (GeneralSecurityException | RuntimeException exc) {
            throw new IllegalStateException("로컬 보안 키가 없거나 암호문이 손상되었습니다.", exc);
        }
    }

    Cipher newEncryptCipher() throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, key);
        return cipher;
    }

    Cipher newDecryptCipher(byte[] iv) throws GeneralSecurityException {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(128, iv));
        return cipher;
    }
}
