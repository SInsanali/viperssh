#!/bin/bash
# Preview bin/expect.sh's connection status output against a simulated server
# (tests/fake_ssh/ssh), so the format can be tuned without a live host.
#
# Usage: tests/preview.sh <scenario> [--vault [PASSWORD]]
#
#   --vault           also show the vault save/update prompt (nothing is saved)
#   --vault PASSWORD  ...starting with PASSWORD as the saved password
#
# The fake login password is hunter2. Type "exit" to leave the fake shell, or
# idle-logout / server-gone / server-closed to see how a timeout or the server
# ending the session is reported.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FAKE_DIR="$SCRIPT_DIR/fake_ssh"

usage() {
    echo "Usage: tests/preview.sh <scenario> [--vault [PASSWORD]]"
    echo ""
    echo "Scenarios (login password is hunter2):"
    grep '^#   [a-z]' "$FAKE_DIR/ssh" | sed 's/^#//'
}

scenario="$1"
if [[ -z "$scenario" || "$scenario" == "-h" || "$scenario" == "--help" ]]; then
    usage
    exit 0
fi
if ! grep -q "^#   $scenario " "$FAKE_DIR/ssh"; then
    echo "Unknown scenario: $scenario"
    echo ""
    usage
    exit 1
fi
shift

if [[ "$1" == "--vault" ]]; then
    # expect.sh writes the password to save into this fd; discard it
    exec 3>/dev/null
    export VIPER_PW_FD=3
    [[ -n "$2" ]] && export VIPER_PASSWORD="$2"
fi

state="$(mktemp "${TMPDIR:-/tmp}/viper-preview.XXXXXX")"
trap 'rm -f "$state"' EXIT

FAKE_SSH_SCENARIO="$scenario" FAKE_SSH_STATE="$state" PATH="$FAKE_DIR:$PATH" \
    "$PROJECT_DIR/bin/expect.sh" app1.dev.example.local
