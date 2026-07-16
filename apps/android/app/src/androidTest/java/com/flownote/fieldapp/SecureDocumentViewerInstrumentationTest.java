package com.flownote.fieldapp;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.ComponentName;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.pm.PackageManager;
import android.test.InstrumentationTestCase;
import android.view.WindowManager;

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
}
