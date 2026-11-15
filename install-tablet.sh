#!/usr/bin/env bash
# Install the hanzi-bg app on the tablet over adb.
#
# The APK must be signed: the release build is unsigned (apksigner: "DOES NOT
# VERIFY"), so the debug build is the installable one. It carries the current
# content.db (21 200 896 B) and all 5732 audio clips.
#
# Transport: the tablet is reachable over the LAN, but adb needs either USB or
# wireless debugging. MIUI blocks a package install from Termux's own UID
# (XSpaceManagerServiceImpl.getDefaultUserId -> "You either need MANAGE_USERS
# or CREATE_USERS permission"), and Termux cannot set service.adb.tcp.port, so
# there is no install path from inside the tablet. adb is the only route.
#
# Usage:
#   ./install-tablet.sh              install (and launch + verify)
#   ./install-tablet.sh install      install only
#   ./install-tablet.sh verify       check the installed app
#
# Environment:
#   ADB          path to adb (default: the winget platform-tools copy)
#   APK          apk to install (default: the fresh debug build)
#   SERIAL       device serial (default: whatever adb reports)

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ADB="${ADB:-/c/Users/IPP/AppData/Local/Microsoft/WinGet/Packages/Google.PlatformTools_Microsoft.Winget.Source_8wekyb3d8bbwe/platform-tools/adb.exe}"
APK="${APK:-$HERE/android/app/build/outputs/apk/debug/app-debug.apk}"
# The debug build type sets applicationIdSuffix = ".debug", so the package
# is bg.hanzi.learn.debug while the activity class stays bg.hanzi.learn.
PKG="bg.hanzi.learn.debug"
ACTIVITY="bg.hanzi.learn.MainActivity"

say()  { printf '%s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ -x "$ADB" ] || [ -f "$ADB" ] || fail "adb not found at $ADB"
[ -f "$APK" ] || fail "apk not found at $APK"

# The device must be present and authorised. "unauthorized" means the tablet
# is showing the RSA prompt and nobody accepted it yet.
require_device() {
  local line state
  line="$("$ADB" devices | sed -n '2p')"
  [ -n "$line" ] || fail "no device visible to adb - plug the tablet in (USB debugging ON, screen unlocked) or run: ./install-tablet.sh connect <ip>:<port> [code]"
  state="$(printf '%s' "$line" | awk '{print $2}')"
  case "$state" in
    device) say "   device: $line" ;;
    unauthorized) fail "device is UNAUTHORIZED - accept the 'Allow USB debugging?' prompt on the tablet (tick 'Always allow')" ;;
    offline) fail "device is OFFLINE - replug the cable or re-run adb connect" ;;
    *) fail "device state '$state' - see: $ADB devices" ;;
  esac
}

# Wireless debugging (Android 11+): the tablet shows an IP:port and a 6-digit
# code under Developer options -> Wireless debugging -> Pair device with
# pairing code. `adb pair` authorises the PC, `adb connect` opens the session.
connect_device() {
  local endpoint="$1" code="${2:-}"
  [ -n "$endpoint" ] || fail "usage: $0 connect <ip>:<port> [6-digit pairing code]"
  if [ -n "$code" ]; then
    say "== pairing with $endpoint =="
    "$ADB" pair "$endpoint" "$code" 2>&1 | tail -3
  fi
  say "== connecting to $endpoint =="
  "$ADB" connect "$endpoint" 2>&1 | tail -3
  "$ADB" devices -l 2>&1 | tail -3
}

install_apk() {
  say "== installing $(basename "$APK") =="
  say "   size: $(du -h "$APK" | cut -f1)"
  "$ADB" install -r "$APK" 2>&1 | tail -5
}

verify_app() {
  say "== verifying the installed app =="
  "$ADB" shell pm list packages 2>&1 | grep "$PKG" \
    && say "   package present" \
    || fail "package $PKG not found on the device"
  "$ADB" shell pm path "$PKG" 2>&1 | grep -q "package:" \
    && say "   apk installed at: $("$ADB" shell pm path "$PKG" 2>&1 | tr -d '\r')" \
    || fail "no apk path for $PKG"
}

launch_app() {
  say "== launching the app =="
  "$ADB" shell am start -n "$PKG/$ACTIVITY" 2>&1 | tail -3
  sleep 6
  say "   content.db copied to app storage?"
  "$ADB" shell "run-as $PKG ls -l /data/data/$PKG/databases 2>/dev/null || ls /data/data/$PKG/databases" 2>&1 | tr -d '\r' | head -5
  say "   crashes so far:"
  "$ADB" logcat -d -b crash 2>&1 | grep -c FATAL | sed 's/^/   FATAL count: /'
}

case "${1:-install}" in
  install)
    require_device
    install_apk
    verify_app
    launch_app
    ;;
  verify)
    require_device
    verify_app
    ;;
  connect) connect_device "${2:-}" "${3:-}" ;;
  *) fail "usage: $0 [install|verify|connect <ip>:<port> [code]]" ;;
esac
