#!/usr/bin/env bash
# Push the hanzi-bg project to the tablet (Termux) over SSH.
#
# Transport rules learned from the cyber-bob tablet deploy:
#   - Termux's sshd serves no SFTP subsystem, so scp needs -O (legacy SCP).
#   - scp's -p is a BOOLEAN flag; the PORT is -P. They must not share an
#     options array, or scp treats "8022" as a source path.
#   - Native Windows binaries need native Windows paths, not /c/... MSYS paths.
#   - scp -r into an existing directory nests (dest/src/). This script stages
#     into a fresh directory and moves the payload into place.
#
# Usage:
#   ./push-tablet.sh              push the project to ~/hanzi-bg
#   ./push-tablet.sh status       report what is on the device (read-only)
#   ./push-tablet.sh verify       re-verify the deployed tree (read-only)
#
# Environment:
#   SSH_HOST   tablet address as seen from this PC (default 192.168.0.66)
#   SSH_PORT   Termux sshd port (default 8022)

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMPDIR="${TMPDIR:-/tmp}"
mkdir -p "$TMPDIR"

# The key and the user are this machine's defaults; both can be
# overridden, so the script is not tied to one computer.
KEY="${KEY:-$HOME/.ssh/id_ed25519}"
SSH_USER="${SSH_USER:-u0_a301}"
SSH_HOST="${SSH_HOST:-192.168.0.66}"
SSH_PORT="${SSH_PORT:-8022}"
REMOTE_HOME="/data/data/com.termux/files/home"
DEST_NAME="hanzi-bg"
DEST="$REMOTE_HOME/$DEST_NAME"

SSH_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 -i "$KEY" -p "$SSH_PORT")
SCP_OPTS=(-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "$KEY" -O -P "$SSH_PORT")

say()  { printf '%s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# Build output, Gradle caches and __pycache__ are regenerable and huge
# (android/app/build alone is 815 MB); everything else — including the
# generated data/ the app ships — is pushed.
EXCLUDES=(
  --exclude=./android/app/build
  --exclude=./android/build
  --exclude=./android/.gradle
  --exclude=./android/.kotlin
  --exclude=./.pytest_cache
  --exclude=./pipeline/.pytest_cache
  --exclude=./simulation/.pytest_cache
  --exclude='*/__pycache__'
  --exclude='*/.pytest_cache'
)

require_ssh() {
  ssh "${SSH_OPTS[@]}" "$SSH_USER@$SSH_HOST" true 2>/dev/null \
    || fail "SSH to $SSH_HOST:$SSH_PORT failed - open Termux on the tablet and run: sshd"
}

build_payload() {
  PAYLOAD_TAR="$TMPDIR/hanzi-bg-push.tar.gz"
  rm -f "$PAYLOAD_TAR"
  say "== packing project (excluding Gradle build output and caches) =="
  tar -cf - "${EXCLUDES[@]}" -C "$HERE" . | gzip -1 > "$PAYLOAD_TAR" \
    || fail "could not pack the project"
  say "   payload: $(du -h "$PAYLOAD_TAR" | cut -f1)"
}

push_payload() {
  local tar="$1"
  local remote_tar="$REMOTE_HOME/.hanzi-bg-push.tar.gz"
  local win_tar
  win_tar="$(cygpath -w "$tar" 2>/dev/null || echo "$tar")"
  win_tar="${win_tar//\\//}"

  say "== uploading to $SSH_HOST:$SSH_PORT =="
  scp "${SCP_OPTS[@]}" "$win_tar" "$SSH_USER@$SSH_HOST:$remote_tar" \
    || fail "scp failed"

  say "== unpacking into $DEST =="
  ssh "${SSH_OPTS[@]}" "$SSH_USER@$SSH_HOST" "
    set -e
    rm -rf '$DEST.new' '$DEST.old'
    mkdir -p '$DEST.new'
    tar -xzf '$remote_tar' -C '$DEST.new'
    if [ -e '$DEST' ]; then mv '$DEST' '$DEST.old'; fi
    mv '$DEST.new' '$DEST'
    rm -rf '$DEST.old' '$remote_tar'
    echo '   staged -> $DEST'
  " || fail "could not unpack the payload on the device"
}

verify() {
  say "== verifying on the device =="
  local manifest="$TMPDIR/hanzi-bg-manifest.txt"
  # sha256 of every tracked+artifact file, relative paths, sorted.
  ( cd "$HERE" && find . \
      -path ./android/app/build -prune -o \
      -path ./android/build -prune -o \
      -path ./android/.gradle -prune -o \
      -path ./android/.kotlin -prune -o \
      -name '__pycache__' -prune -o \
      -name '.pytest_cache' -prune -o \
      -type f -print0 \
    | sort -z \
    | xargs -0 sha256sum ) > "$manifest" || fail "could not hash the local tree"
  local win_manifest
  win_manifest="$(cygpath -w "$manifest" 2>/dev/null || echo "$manifest")"
  win_manifest="${win_manifest//\\//}"
  scp "${SCP_OPTS[@]}" "$win_manifest" "$SSH_USER@$SSH_HOST:$REMOTE_HOME/.hanzi-bg-manifest.txt" \
    || fail "could not upload the manifest"

  ssh "${SSH_OPTS[@]}" "$SSH_USER@$SSH_HOST" "
    cd '$DEST' || exit 1
    out=\$(sha256sum -c '$REMOTE_HOME/.hanzi-bg-manifest.txt' 2>&1)
    ok=\$(printf '%s\n' \"\$out\" | grep -c ': OK\$' || true)
    bad=\$(printf '%s\n' \"\$out\" | grep -c ': FAILED' || true)
    miss=\$(printf '%s\n' \"\$out\" | grep -c 'No such file' || true)
    echo \"   ok: \$ok  failed: \$bad  missing: \$miss\"
    if [ \"\$bad\" -gt 0 ] || [ \"\$miss\" -gt 0 ]; then
      printf '%s\n' \"\$out\" | grep -v ': OK\$' | head -20
    fi
    rm -f '$REMOTE_HOME/.hanzi-bg-manifest.txt'
    [ \"\$bad\" -eq 0 ] && [ \"\$miss\" -eq 0 ]
  " || fail "verification failed on the device"
}

status() {
  ssh "${SSH_OPTS[@]}" "$SSH_USER@$SSH_HOST" "
    echo 'destination: $DEST'
    if [ -d '$DEST' ]; then
      du -sh '$DEST'
      find '$DEST' -type f | wc -l | sed 's/^/files: /'
    else
      echo 'not deployed'
    fi
  "
}

case "${1:-push}" in
  push)
    require_ssh
    build_payload
    push_payload "$PAYLOAD_TAR"
    rm -f "$PAYLOAD_TAR"
    verify
    status
    ;;
  status) require_ssh; status ;;
  verify) require_ssh; verify ;;
  *) fail "usage: $0 [push|status|verify]" ;;
esac
