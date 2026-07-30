package com.flownote.fieldapp;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

public final class BootCompletedReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || !Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            return;
        }
        try {
            if (!new SecureSessionStore(context).hasSession()) {
                return;
            }
        } catch (RuntimeException exc) {
            Log.e("FlowNoteDelivery", "boot secure storage unavailable", exc);
            return;
        }
        Intent service = new Intent(context, NotificationPollingService.class);
        context.startForegroundService(service);
    }
}
