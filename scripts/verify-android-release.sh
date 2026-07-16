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

evidence_dir="$evidence_root/$run_id/android-release"
mkdir -p "$evidence_dir"

shasum -a 256 "$apk" > "$evidence_dir/package-sha256.txt"
apksigner verify --verbose --print-certs "$apk" > "$evidence_dir/signature.txt"
adb devices -l > "$evidence_dir/adb-devices.txt"

device_count="$(adb devices | awk 'NR > 1 && $2 == "device" { count++ } END { print count+0 }')"
[[ "$device_count" == "1" ]] || {
  echo "exactly one approved Android device must be connected; found $device_count" >&2
  exit 1
}

adb shell dumpsys deviceidle > "$evidence_dir/deviceidle-before.txt"
adb shell dumpsys package com.flownote.fieldapp > "$evidence_dir/package-before.txt" || true
adb shell settings get global adb_enabled > "$evidence_dir/adb-enabled.txt"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install)
      adb install -r "$apk" > "$evidence_dir/install-upgrade.txt"
      shift
      ;;
    --rollback)
      [[ $# -ge 2 && -f "$2" ]] || usage
      apksigner verify --verbose --print-certs "$2" > "$evidence_dir/rollback-signature.txt"
      shasum -a 256 "$2" > "$evidence_dir/rollback-sha256.txt"
      current_cert="$(awk -F': ' '/Signer #1 certificate SHA-256 digest:/ { print $2; exit }' "$evidence_dir/signature.txt")"
      rollback_cert="$(awk -F': ' '/Signer #1 certificate SHA-256 digest:/ { print $2; exit }' "$evidence_dir/rollback-signature.txt")"
      [[ -n "$current_cert" && "$current_cert" == "$rollback_cert" ]] || {
        echo "rollback APK signer does not match the release candidate" >&2
        exit 1
      }
      adb install -r -d "$2" > "$evidence_dir/rollback-install.txt"
      shift 2
      ;;
    *) usage ;;
  esac
done

adb shell dumpsys package com.flownote.fieldapp > "$evidence_dir/package-after.txt" || true
adb logcat -d -v threadtime FlowNoteDelivery:I '*:S' > "$evidence_dir/delivery-log.txt" || true
echo "Android release evidence preserved at $evidence_dir"
