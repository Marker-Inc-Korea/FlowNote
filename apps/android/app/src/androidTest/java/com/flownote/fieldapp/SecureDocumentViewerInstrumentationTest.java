package com.flownote.fieldapp;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.ComponentName;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.pm.PackageManager;
import android.test.InstrumentationTestCase;
import android.view.WindowManager;

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
}
