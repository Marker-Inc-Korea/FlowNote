#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <run_id> <signed.apk|signed.aab> <evidence_root> [--install] [--rollback <previous.apk>] [--device-serial <adb-serial>]" >&2
  exit 2
}

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null || fail "$1 is required"
}

[[ $# -ge 3 ]] || usage
run_id="$1"
artifact="$2"
evidence_root="$3"
shift 3

install_requested=false
candidate_install_verified=false
rollback_apk=""
device_serial=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --install)
      install_requested=true
      shift
      ;;
    --rollback)
      [[ $# -ge 2 ]] || usage
      rollback_apk="$2"
      shift 2
      ;;
    --device-serial)
      [[ $# -ge 2 && -n "$2" ]] || usage
      device_serial="$2"
      shift 2
      ;;
    *) usage ;;
  esac
done

[[ -f "$artifact" ]] || fail "signed Android artifact not found: $artifact"
case "${artifact##*.}" in
  apk) artifact_type="APK" ;;
  aab) artifact_type="AAB" ;;
  *) fail "release artifact must have an .apk or .aab extension" ;;
esac
if [[ "$artifact_type" == "AAB" && ( "$install_requested" == true || -n "$rollback_apk" ) ]]; then
  fail "AAB cannot be installed or rolled back directly; provide the MDM-delivered signed APK"
fi
if [[ ( "$install_requested" == true || -n "$rollback_apk" ) && -z "$device_serial" ]]; then
  fail "--device-serial is required for install or rollback to prevent targeting an unapproved device"
fi
if [[ -n "$rollback_apk" && ! -f "$rollback_apk" ]]; then
  fail "previous approved APK not found: $rollback_apk"
fi

run_dir="$evidence_root/$run_id"
packages_dir="$run_dir/packages"
android_logs_dir="$run_dir/android-logs"
scenario_dir="$run_dir/scenario-results"
integrity_dir="$run_dir/integrity"
mkdir -p "$packages_dir" "$android_logs_dir" "$scenario_dir" "$integrity_dir"

require_command shasum
artifact_name="$(basename "$artifact")"
shasum -a 256 "$artifact" > "$packages_dir/android-package-sha256.txt"

candidate_signer=""
candidate_version_code=""
candidate_version_name=""
if [[ "$artifact_type" == "APK" ]]; then
  require_command apksigner
  require_command aapt
  apksigner verify --verbose --print-certs "$artifact" > "$packages_dir/android-signature.txt"
  aapt dump badging "$artifact" > "$packages_dir/android-package-badging.txt"
  if command -v apkanalyzer >/dev/null; then
    apkanalyzer manifest print "$artifact" > "$packages_dir/android-manifest.xml"
    manifest_format="xml"
  else
    aapt dump xmltree "$artifact" AndroidManifest.xml \
      > "$packages_dir/android-manifest.xml"
    manifest_format="aapt_xmltree"
  fi
  candidate_signer="$(awk -F': ' '/Signer #1 certificate SHA-256 digest:/ { print $2; exit }' "$packages_dir/android-signature.txt")"
  candidate_version_code="$(sed -n "s/^package:.*versionCode='\([^']*\)'.*/\1/p" "$packages_dir/android-package-badging.txt" | head -n 1)"
  candidate_version_name="$(sed -n "s/^package:.*versionName='\([^']*\)'.*/\1/p" "$packages_dir/android-package-badging.txt" | head -n 1)"
  grep -q "name='com.flownote.fieldapp'" "$packages_dir/android-package-badging.txt" || fail "unexpected Android applicationId"
  ! grep -q '^application-debuggable' "$packages_dir/android-package-badging.txt" || fail "release APK is debuggable"
  if [[ "$manifest_format" == "xml" ]]; then
    grep -Eq 'android:allowBackup="false"|android:allowBackup="0"' "$packages_dir/android-manifest.xml" || fail "release APK does not disable Android backup"
    grep -Eq 'android:usesCleartextTraffic="false"|android:usesCleartextTraffic="0"' "$packages_dir/android-manifest.xml" || fail "release APK does not disable cleartext traffic"
  else
    grep -Eq 'android:allowBackup.*0x0$' "$packages_dir/android-manifest.xml" \
      || fail "release APK does not disable Android backup"
    grep -Eq 'android:usesCleartextTraffic.*0x0$' "$packages_dir/android-manifest.xml" \
      || fail "release APK does not disable cleartext traffic"
    ! grep -Eq 'android:debuggable.*0xffffffff$' "$packages_dir/android-manifest.xml" \
      || fail "release APK is debuggable"
  fi
  [[ -n "$candidate_signer" && -n "$candidate_version_code" ]] || fail "APK signer or versionCode could not be read"
else
  require_command jarsigner
  require_command keytool
  jarsigner -verify -verbose -certs "$artifact" > "$packages_dir/android-aab-signature.txt"
  grep -q 'jar verified.' "$packages_dir/android-aab-signature.txt" || fail "AAB JAR signature verification failed"
  keytool -printcert -jarfile "$artifact" > "$packages_dir/android-aab-certificate.txt"
  candidate_signer="$(
    sed -n 's/^[[:space:]]*SHA256:[[:space:]]*//p' \
      "$packages_dir/android-aab-certificate.txt" | head -n 1
  )"
  if command -v bundletool >/dev/null; then
    bundletool dump manifest --bundle="$artifact" --module=base \
      > "$packages_dir/android-manifest.xml"
  elif [[ -n "${BUNDLETOOL_JAR:-}" && -f "${BUNDLETOOL_JAR}" ]]; then
    require_command java
    java -jar "$BUNDLETOOL_JAR" dump manifest --bundle="$artifact" --module=base \
      > "$packages_dir/android-manifest.xml"
  else
    fail "bundletool or BUNDLETOOL_JAR is required to inspect an AAB base manifest"
  fi
  candidate_version_code="$(
    sed -n 's/.*android:versionCode="\([^"]*\)".*/\1/p' \
      "$packages_dir/android-manifest.xml" | head -n 1
  )"
  candidate_version_name="$(
    sed -n 's/.*android:versionName="\([^"]*\)".*/\1/p' \
      "$packages_dir/android-manifest.xml" | head -n 1
  )"
  grep -Eq '<manifest[^>]*package="com\.flownote\.fieldapp"' \
    "$packages_dir/android-manifest.xml" || fail "unexpected Android applicationId"
  ! grep -Eq 'android:debuggable="(true|1)"' \
    "$packages_dir/android-manifest.xml" || fail "release AAB is debuggable"
  grep -Eq 'android:allowBackup="(false|0)"' \
    "$packages_dir/android-manifest.xml" || fail "release AAB does not disable Android backup"
  grep -Eq 'android:usesCleartextTraffic="(false|0)"' \
    "$packages_dir/android-manifest.xml" || fail "release AAB does not disable cleartext traffic"
  [[ -n "$candidate_signer" && "$candidate_version_code" =~ ^[0-9]+$ ]] \
    || fail "AAB signer or numeric versionCode could not be read"
fi

if [[ -n "$device_serial" ]]; then
  require_command adb
  adb devices -l > "$android_logs_dir/adb-devices.txt"
  device_state="$(adb -s "$device_serial" get-state 2>/dev/null || true)"
  [[ "$device_state" == "device" ]] || fail "approved device serial is not connected and authorized: $device_serial"
  printf '%s\n' "$device_serial" > "$android_logs_dir/approved-adb-serial.txt"
  adb -s "$device_serial" shell dumpsys deviceidle > "$android_logs_dir/deviceidle-before.txt"
  adb -s "$device_serial" shell dumpsys package com.flownote.fieldapp > "$packages_dir/android-package-before.txt" || true
  adb -s "$device_serial" shell settings get global adb_enabled > "$integrity_dir/android-adb-enabled.txt"
fi

if [[ "$install_requested" == true || -n "$rollback_apk" ]]; then
  adb -s "$device_serial" install -r "$artifact" > "$packages_dir/android-install-upgrade.txt"
  grep -q 'Success' "$packages_dir/android-install-upgrade.txt" || fail "release candidate installation did not report Success"
  candidate_install_verified=true
fi

if [[ -n "$rollback_apk" ]]; then
  require_command apksigner
  require_command aapt
  apksigner verify --verbose --print-certs "$rollback_apk" > "$packages_dir/android-rollback-signature.txt"
  shasum -a 256 "$rollback_apk" > "$packages_dir/android-rollback-sha256.txt"
  aapt dump badging "$rollback_apk" > "$packages_dir/android-rollback-badging.txt"
  rollback_signer="$(awk -F': ' '/Signer #1 certificate SHA-256 digest:/ { print $2; exit }' "$packages_dir/android-rollback-signature.txt")"
  rollback_version_code="$(sed -n "s/^package:.*versionCode='\([^']*\)'.*/\1/p" "$packages_dir/android-rollback-badging.txt" | head -n 1)"
  [[ -n "$candidate_signer" && "$candidate_signer" == "$rollback_signer" ]] || fail "rollback APK signer does not match the release candidate"
  [[ "$rollback_version_code" =~ ^[0-9]+$ && "$candidate_version_code" =~ ^[0-9]+$ ]] || fail "candidate or rollback versionCode is not numeric"
  (( rollback_version_code < candidate_version_code )) || fail "rollback APK must have a lower versionCode than the release candidate"

  outbox_audit_nonce="${run_id}-rollback-$(date +%s)-$$"
  adb -s "$device_serial" shell am start -W \
    --activity-clear-top \
    -n com.flownote.fieldapp/.MainActivity \
    --es flownote_outbox_audit_nonce "$outbox_audit_nonce" \
    > "$android_logs_dir/android-outbox-audit-launch.txt"
  outbox_audit_line=""
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    adb -s "$device_serial" logcat -d -v brief FlowNoteOutbox:I '*:S' \
      > "$android_logs_dir/android-outbox-audit-log.txt" || true
    outbox_audit_line="$(
      grep -F "audit_nonce=$outbox_audit_nonce " \
        "$android_logs_dir/android-outbox-audit-log.txt" | tail -n 1 || true
    )"
    [[ -z "$outbox_audit_line" ]] || break
    sleep 1
  done
  [[ -n "$outbox_audit_line" ]] || fail "candidate APK did not report the on-device outbox state"
  outbox_pending="$(sed -n 's/.* pending=\([0-9][0-9]*\) .*/\1/p' <<< "$outbox_audit_line")"
  [[ "$outbox_pending" =~ ^[0-9]+$ ]] || fail "on-device outbox pending count could not be read"
  [[ "$outbox_pending" == "0" ]] || fail \
    "rollback is blocked because the approved device has $outbox_pending pending outbox item(s)"
  printf '%s\n' "$outbox_audit_line" > "$integrity_dir/android-outbox-before-rollback.txt"

  adb -s "$device_serial" install -r -d "$rollback_apk" > "$packages_dir/android-rollback-install.txt"
  grep -q 'Success' "$packages_dir/android-rollback-install.txt" || fail "previous approved APK rollback did not report Success"
fi

if [[ -n "$device_serial" ]]; then
  adb -s "$device_serial" shell dumpsys package com.flownote.fieldapp > "$packages_dir/android-package-after.txt" || true
  adb -s "$device_serial" shell dumpsys deviceidle > "$android_logs_dir/deviceidle-after.txt"
  adb -s "$device_serial" logcat -d -v threadtime FlowNoteDelivery:I '*:S' > "$android_logs_dir/delivery-log.txt" || true
fi

scenario_template="$scenario_dir/android-delivery.csv"
if [[ ! -e "$scenario_template" ]]; then
  {
    echo 'scenario_id,condition,delivery_run_id,message_id,created_at_utc,recovery_ready_at_utc,displayed_at_utc,receipt_at_utc,page_seconds,elapsed_seconds,allowed_seconds,result,evidence'
    echo 'AND-NOTIFY-NORMAL,normal,,,,,,,,,,NOT_RUN,'
    echo 'AND-NOTIFY-DOZE,doze,,,,,,,,,,NOT_RUN,'
    echo 'AND-NOTIFY-DISCONNECT,disconnect_5m,,,,,,,,,,NOT_RUN,'
    echo 'AND-NOTIFY-BOOT,reboot,,,,,,,,,,NOT_RUN,'
    echo 'AND-NOTIFY-ADDRESS,address_change,,,,,,,,,,NOT_RUN,'
    echo 'AND-NOTIFY-ACCESS-EXPIRY,access_token_expiry,,,,,,,,,,NOT_RUN,'
    echo 'AND-NOTIFY-REFRESH-REJECTED,refresh_rejected,,,,,,,,,,NOT_RUN,'
    echo 'AND-NOTIFY-FORCESTOP,force_stop_kiosk_restart,,,,,,,,,,NOT_RUN,'
    echo 'AND-FIELD-COMMENT-RESTART-LOGIN-RETRY,field_comment_failure_restart_login_retry,,,,,,,,,,NOT_RUN,'
    echo 'AND-PHOTO-RESTART-LOGIN-RETRY,photo_failure_restart_login_retry,,,,,,,,,,NOT_RUN,'
    echo 'AND-HANDOVER-RESTART-LOGIN-RETRY,handover_failure_restart_login_retry,,,,,,,,,,NOT_RUN,'
    echo 'AND-HANDOVER-OFFLINE,offline_handover_reboot_retry,,,,,,,,,,NOT_RUN,'
    echo 'AND-HANDOVER-IDEMPOTENCY,response_loss_same_key_retry,,,,,,,,,,NOT_RUN,'
    echo 'AND-OUTBOX-DEVICE-INACTIVE,inactive_device_blocks_tokens_and_outbox,,,,,,,,,,NOT_RUN,'
    echo 'AND-OUTBOX-KEYSTORE,keystore_failure_preservation_guidance,,,,,,,,,,NOT_RUN,'
    echo 'AND-ROLLBACK-PENDING-OUTBOX,pending_outbox_blocks_rollback,,,,,,,,,,NOT_RUN,'
  } > "$scenario_template"
fi

ux_template="$scenario_dir/android-field-ux.csv"
if [[ ! -e "$ux_template" ]]; then
  {
    echo 'scenario_id,condition,input_kind,participant_code,attempt,success,elapsed_seconds,help_requests,critical_blockers,source_id,handover_id,evidence,result'
    echo 'AND-UX-GLOVE-FIELD-COMMENT,gloves,field_comment,,,,,,,,,,NOT_RUN'
    echo 'AND-UX-GLOVE-PHOTO,gloves,photo,,,,,,,,,,NOT_RUN'
    echo 'AND-UX-GLOVE-HANDOVER,gloves,handover,,,,,,,,,,NOT_RUN'
    echo 'AND-UX-ONEHAND-FIELD-COMMENT,one_hand,field_comment,,,,,,,,,,NOT_RUN'
    echo 'AND-UX-ONEHAND-PHOTO,one_hand,photo,,,,,,,,,,NOT_RUN'
    echo 'AND-UX-ONEHAND-HANDOVER,one_hand,handover,,,,,,,,,,NOT_RUN'
    echo 'AND-UX-MOUNTED-FIELD-COMMENT,mounted_device,field_comment,,,,,,,,,,NOT_RUN'
    echo 'AND-UX-MOUNTED-PHOTO,mounted_device,photo,,,,,,,,,,NOT_RUN'
    echo 'AND-UX-MOUNTED-HANDOVER,mounted_device,handover,,,,,,,,,,NOT_RUN'
    echo 'AND-UX-PHOTO-RESET,photo_select_preview_save_reset,photo,,,,,,,,,,NOT_RUN'
  } > "$ux_template"
fi

{
  echo "result=PASS"
  echo "verification_scope=package_static_and_requested_install_only"
  echo "operational_scenarios=NOT_RUN"
  echo "run_id=$run_id"
  echo "artifact=$artifact_name"
  echo "artifact_type=$artifact_type"
  echo "version_name=$candidate_version_name"
  echo "version_code=$candidate_version_code"
  echo "signer_sha256=$candidate_signer"
  echo "device_serial=$device_serial"
  echo "install_verified=$candidate_install_verified"
  [[ -z "$rollback_apk" ]] || echo "rollback_verified=true"
} > "$packages_dir/android-release-verification.txt"

echo "Android release evidence preserved at $run_dir"
