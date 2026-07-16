package com.flownote.fieldapp;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class BootCompletedReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || !Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            return;
        }
        if (!new SecureSessionStore(context).hasSession()) {
            return;
        }
        Intent service = new Intent(context, NotificationPollingService.class);
        context.startForegroundService(service);
    }
}
