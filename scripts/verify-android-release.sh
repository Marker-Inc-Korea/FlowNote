#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <run_id> <signed.apk> <evidence_dir> [--install] [--rollback <previous.apk>]" >&2
  exit 2
}

[[ $# -ge 3 ]] || usage
run_id="$1"
apk="$2"
evidence_root="$3"
shift 3

[[ -f "$apk" ]] || { echo "signed APK not found: $apk" >&2; exit 1; }
command -v apksigner >/dev/null || { echo "apksigner is required" >&2; exit 1; }
command -v adb >/dev/null || { echo "adb is required" >&2; exit 1; }

run_dir="$evidence_root/$run_id"
packages_dir="$run_dir/packages"
android_logs_dir="$run_dir/android-logs"
scenario_dir="$run_dir/scenario-results"
integrity_dir="$run_dir/integrity"
mkdir -p "$packages_dir" "$android_logs_dir" "$scenario_dir" "$integrity_dir"

shasum -a 256 "$apk" > "$packages_dir/android-package-sha256.txt"
apksigner verify --verbose --print-certs "$apk" > "$packages_dir/android-signature.txt"
adb devices -l > "$android_logs_dir/adb-devices.txt"

device_count="$(adb devices | awk 'NR > 1 && $2 == "device" { count++ } END { print count+0 }')"
[[ "$device_count" == "1" ]] || {
  echo "exactly one approved Android device must be connected; found $device_count" >&2
  exit 1
}

adb shell dumpsys deviceidle > "$android_logs_dir/deviceidle-before.txt"
adb shell dumpsys package com.flownote.fieldapp > "$packages_dir/android-package-before.txt" || true
adb shell settings get global adb_enabled > "$integrity_dir/android-adb-enabled.txt"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install)
      adb install -r "$apk" > "$packages_dir/android-install-upgrade.txt"
      shift
      ;;
    --rollback)
      [[ $# -ge 2 && -f "$2" ]] || usage
      apksigner verify --verbose --print-certs "$2" > "$packages_dir/android-rollback-signature.txt"
      shasum -a 256 "$2" > "$packages_dir/android-rollback-sha256.txt"
      current_cert="$(awk -F': ' '/Signer #1 certificate SHA-256 digest:/ { print $2; exit }' "$packages_dir/android-signature.txt")"
      rollback_cert="$(awk -F': ' '/Signer #1 certificate SHA-256 digest:/ { print $2; exit }' "$packages_dir/android-rollback-signature.txt")"
      [[ -n "$current_cert" && "$current_cert" == "$rollback_cert" ]] || {
        echo "rollback APK signer does not match the release candidate" >&2
        exit 1
      }
      adb install -r -d "$2" > "$packages_dir/android-rollback-install.txt"
      shift 2
      ;;
    *) usage ;;
  esac
done

adb shell dumpsys package com.flownote.fieldapp > "$packages_dir/android-package-after.txt" || true
adb shell dumpsys deviceidle > "$android_logs_dir/deviceidle-after.txt"
adb logcat -d -v threadtime FlowNoteDelivery:I '*:S' > "$android_logs_dir/delivery-log.txt" || true

scenario_template="$scenario_dir/android-scenarios.csv"
if [[ ! -e "$scenario_template" ]]; then
  {
    echo 'scenario_id,condition,delivery_run_id,message_id,created_at_utc,recovery_ready_at_utc,displayed_at_utc,receipt_at_utc,page_seconds,result,evidence,notes'
    echo 'AND-NOTIFY-NORMAL,normal,,,,,,,,NOT_RUN,,'
    echo 'AND-NOTIFY-DOZE,doze,,,,,,,,NOT_RUN,,'
    echo 'AND-NOTIFY-DISCONNECT,disconnect_5m,,,,,,,,NOT_RUN,,'
    echo 'AND-NOTIFY-BOOT,reboot,,,,,,,,NOT_RUN,,'
    echo 'AND-NOTIFY-ADDRESS,address_change,,,,,,,,NOT_RUN,,'
    echo 'AND-NOTIFY-FORCESTOP,kiosk_restart,,,,,,,,NOT_RUN,,'
  } > "$scenario_template"
fi

echo "Android release evidence preserved at $run_dir"
