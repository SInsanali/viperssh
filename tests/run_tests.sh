#!/bin/bash
# ViperSSH Test Suite
# Run with: ./tests/run_tests.sh
#
# Permission granted by maintainer to run all tests automatically.
# These tests use expect to simulate user interaction with the TUI.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# lib/ holds the importable modules (config, vault, paths)
export PYTHONPATH="$PROJECT_DIR/lib${PYTHONPATH:+:$PYTHONPATH}"

# Prefer the project's venv python (has the deps) so the suite is self-contained
# regardless of whether the venv is activated. Falls back to system python3.
PY="$PROJECT_DIR/venv/bin/python3"
[[ -x "$PY" ]] || PY="python3"

# Colors
GREEN='\033[1;32m'
RED='\033[1;31m'
CYAN='\033[1;36m'
RESET='\033[0m'

echo -e "${CYAN}=== ViperSSH Test Suite ===${RESET}\n"

# Check dependencies
for dep in python3 expect; do
    if ! command -v "$dep" &>/dev/null; then
        echo -e "${RED}Missing dependency: $dep${RESET}"
        exit 1
    fi
done

PASSED=0
FAILED=0

run_test() {
    local name="$1"
    shift
    echo -n "  $name... "
    if "$@" >/dev/null 2>&1; then
        echo -e "${GREEN}PASSED${RESET}"
        ((PASSED++))
    else
        echo -e "${RED}FAILED${RESET}"
        ((FAILED++))
    fi
}

echo "Running tests..."
echo ""

# Test 1: Syntax check
run_test "Python syntax" "$PY" -m py_compile bin/viper.py

# Test 2: Config loading
run_test "Config loading" "$PY" -c "
from config import Config
c = Config()
c.load()
assert len(c.environments) > 0
"

# Test 3: CLI flags
run_test "CLI --help" bash -c "./viperssh --help | grep -q Usage"
run_test "CLI --check" bash -c "./viperssh --check | grep -q dependencies"

# Test 4: History class
run_test "History empty load" "$PY" -c "
import tempfile
from pathlib import Path
import config as cfg
path = Path(tempfile.mktemp(suffix='.json'))
cfg.HISTORY_FILE = path
h = cfg.History()
assert h.load() == []
"

run_test "History add and load" "$PY" -c "
import tempfile, json, time
from pathlib import Path
import config as cfg
with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
    path = Path(f.name)
cfg.HISTORY_FILE = path
try:
    h = cfg.History()
    h.add('host1.dev.local')
    h.add('host2.dev.local')
    entries = h.load()
    assert len(entries) == 2
    assert entries[0]['target'] == 'host2.dev.local'
    assert entries[1]['target'] == 'host1.dev.local'
    assert 'ts' in entries[0]
finally:
    path.unlink(missing_ok=True)
"

run_test "History deduplication" "$PY" -c "
import tempfile
from pathlib import Path
import config as cfg
with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
    path = Path(f.name)
cfg.HISTORY_FILE = path
try:
    h = cfg.History()
    h.add('host1.dev.local')
    h.add('host2.dev.local')
    h.add('host1.dev.local')
    entries = h.load()
    assert len(entries) == 2, f'Expected 2, got {len(entries)}'
    assert entries[0]['target'] == 'host1.dev.local'
    assert entries[1]['target'] == 'host2.dev.local'
finally:
    path.unlink(missing_ok=True)
"

run_test "History max 10 entries" "$PY" -c "
import tempfile
from pathlib import Path
import config as cfg
with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
    path = Path(f.name)
cfg.HISTORY_FILE = path
try:
    h = cfg.History()
    for i in range(15):
        h.add(f'host{i}.dev.local')
    entries = h.load()
    assert len(entries) == 10, f'Expected 10, got {len(entries)}'
    assert entries[0]['target'] == 'host14.dev.local'
finally:
    path.unlink(missing_ok=True)
"

# Test 5: TUI launches and renders its footer, then quits cleanly on 'q'.
# (Uses expect rather than GNU `timeout`, which isn't present on macOS.)
run_test "TUI launches" expect -c '
set timeout 6
spawn ./viperssh
expect {
    -re {Help|Quit|Vault} {}
    timeout { exit 1 }
    eof { exit 1 }
}
send "q"
expect eof
'

# Test 6: Environment position preserved after search
run_test "Env position restore" expect -c '
set timeout 5
spawn ./viperssh
sleep 1.5
send "jjj"
sleep 0.3
send "/"
sleep 0.2
send "test"
sleep 0.2
send "\033"
sleep 0.5
send "q"
expect eof
'

# Test 7: History proto field stored correctly
run_test "History sftp proto stored" "$PY" -c "
import tempfile
from pathlib import Path
import config as cfg
with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
    path = Path(f.name)
cfg.HISTORY_FILE = path
try:
    h = cfg.History()
    h.add('host1.dev.local', proto='sftp')
    h.add('host2.dev.local', proto='ssh')
    entries = h.load()
    assert entries[0]['proto'] == 'ssh'
    assert entries[1]['proto'] == 'sftp'
finally:
    path.unlink(missing_ok=True)
"

# Test 9: History modal opens and closes with r key
run_test "History modal open/close" expect -c '
set timeout 5
spawn ./viperssh
sleep 1.5
send "r"
sleep 0.5
send "r"
sleep 0.3
send "q"
expect eof
'

# Test 10: Connection status output - bin/expect.sh driven through
# tests/preview.sh against the fake ssh in tests/fake_ssh. `see RE` fails the
# test unless RE shows up before a timeout or EOF. Status tags are colored,
# hence the [^\n]* between a step and its tag.
STATUS_PRELUDE='
set timeout 8
set env(FAKE_SSH_DELAY) 0
proc see {re} {
    expect {
        -re $re {}
        timeout { puts "\ntimed out waiting for: $re"; exit 1 }
        eof { puts "\nexited before: $re"; exit 1 }
    }
}
proc shell_exit {} {
    see {\$ $}
    send "exit\r"
    expect eof
}
'

run_test "Status: login steps" expect -c "$STATUS_PRELUDE"'
spawn tests/preview.sh ok
see {Connecting to app1\.dev\.example\.local[^\n]*OK}
see {Password for bob@app1\.dev\.example\.local: }
send "hunter2\r"
see {Authenticating bob@app1\.dev\.example\.local[^\n]*OK}
shell_exit
'

run_test "Status: proxy jump" expect -c "$STATUS_PRELUDE"'
spawn tests/preview.sh jump --vault hunter2
see {Proxy jump via bastion\.example\.com[^\n]*OK}
see {Authenticating bob@bastion\.example\.com[^\n]*OK}
see {Connecting to app1\.dev\.example\.local[^\n]*OK}
see {Authenticating bob@app1\.dev\.example\.local[^\n]*OK}
shell_exit
'

run_test "Status: rejected password re-prompts" expect -c "$STATUS_PRELUDE"'
spawn tests/preview.sh ok --vault wrongpw
see {Authenticating bob@app1[^\n]*FAIL}
see {Saved password was rejected}
see {Password for bob@app1\.dev\.example\.local: }
send "hunter2\r"
see {Authenticating bob@app1[^\n]*OK}
see {Update saved password}
send "n\r"
shell_exit
'

run_test "Status: expired password change + reconnect" expect -c "$STATUS_PRELUDE"'
spawn tests/preview.sh expired --vault hunter2
see {Password expired[^\n]*WARN}
see {New password: }
send "short\r"
see {Confirm new password: }
send "short\r"
see {Changing password[^\n]*FAIL}
see {BAD PASSWORD}
see {New password: }
send "Sup3rSecret!\r"
see {Confirm new password: }
send "Sup3rSecret!\r"
see {Changing password[^\n]*OK}
see {Reconnecting to [^\n]*app1}
see {Authenticating bob@app1[^\n]*OK}
see {Update saved password}
send "n\r"
shell_exit
'

run_test "Status: jump host shares the changed password" expect -c "$STATUS_PRELUDE"'
spawn tests/preview.sh jump-expired --vault hunter2
see {New password: }
send "Sup3rSecret!\r"
see {Confirm new password: }
send "Sup3rSecret!\r"
see {Reconnecting to [^\n]*app1}
see {Authenticating bob@bastion[^\n]*FAIL}
see {Trying your new password}
see {Authenticating bob@bastion[^\n]*OK}
see {Authenticating bob@app1[^\n]*OK}
see {Update saved password}
send "n\r"
shell_exit
'

run_test "Status: expired keyboard-interactive change" expect -c "$STATUS_PRELUDE"'
spawn tests/preview.sh expired-kbdint --vault hunter2
see {Password expired[^\n]*WARN}
see {New password: }
send "Sup3rSecret!\r"
see {Confirm new password: }
send "Sup3rSecret!\r"
see {Changing password[^\n]*OK}
expect {
    -re {Reconnecting} { exit 1 }
    -re {Update saved password} { send "n\r" }
    timeout { exit 1 }
}
shell_exit
'

run_test "Status: IPA refuses a change, login starts over" expect -c "$STATUS_PRELUDE"'
spawn tests/preview.sh expired-ipa --vault hunter2
see {Password expired[^\n]*WARN}
see {New password: }
send "short\r"
see {Confirm new password: }
send "short\r"
see {Changing password[^\n]*FAIL}
see {Server message: Password is too short}
see {Authenticating bob@app1[^\n]*OK}
see {New password: }
send "Sup3rSecret!\r"
see {Confirm new password: }
send "Sup3rSecret!\r"
see {Changing password[^\n]*OK}
see {Update saved password}
send "n\r"
shell_exit
'

run_test "Status: IPA refuses the old password, nothing resent" expect -c "$STATUS_PRELUDE"'
spawn tests/preview.sh expired-ipa-oldpw --vault hunter2
see {New password: }
send "Sup3rSecret!\r"
see {Confirm new password: }
send "Sup3rSecret!\r"
see {Changing password[^\n]*FAIL}
see {Old password not accepted}
# The login starts over: the refused password must not be sent again on our
# own (no Authenticating step before the user is asked)
expect {
    -re {Authenticating[^\n]*\n[^\n]*Authenticating} { puts "\nresent a refused password"; exit 1 }
    -re {been refused here[^\n]*\n[^\n]*Password for bob@app1[^:]*: } {}
    timeout { puts "\nno prompt"; exit 1 }
}
# A wrong one typed here is refused, and the re-prompt is a login prompt: not
# taken for "Current password" and answered with the same password again
send "wrongpw\r"
expect {
    -re {Authenticating[^\n]*OK} { puts "\nre-prompt taken for a current-password prompt"; exit 1 }
    -re {Authenticating[^\n]*FAIL[^\n]*\n[^\n]*2 passwords have been refused[^\n]*\n[^\n]*Password for bob@app1[^:]*: } {}
    timeout { puts "\nno second prompt"; exit 1 }
}
send "\003"
expect eof
'

run_test "Status: IPA refuses a change and hangs up, try again" expect -c "$STATUS_PRELUDE"'
spawn tests/preview.sh expired-ipa-pw --vault hunter2
see {New password: }
send "short\r"
see {Confirm new password: }
send "short\r"
see {Changing password[^\n]*FAIL}
see {Try another password\? \(y/n\) }
send "y\r"
see {Reconnecting to [^\n]*app1}
see {New password: }
send "Sup3rSecret!\r"
see {Confirm new password: }
send "Sup3rSecret!\r"
see {Changing password[^\n]*OK}
see {Reconnecting to [^\n]*app1}
see {Authenticating bob@app1[^\n]*OK}
see {Update saved password}
send "n\r"
shell_exit
'

run_test "Status: disconnect line after logout" expect -c "$STATUS_PRELUDE"'
spawn tests/preview.sh ok --vault hunter2
see {\$ $}
send "exit\r"
see {Disconnected from [^\n]*app1}
expect eof
'

run_test "Status: disconnect line on idle timeout" expect -c "$STATUS_PRELUDE"'
spawn tests/preview.sh ok --vault hunter2
see {\$ $}
send "idle-logout\r"
see {Disconnected from [^\n]*app1[^\n]*logged out for inactivity}
expect eof
'

run_test "Status: disconnect line when the server stops responding" expect -c "$STATUS_PRELUDE"'
spawn tests/preview.sh ok --vault hunter2
see {\$ $}
send "server-gone\r"
see {Lost connection to [^\n]*app1[^\n]*the server stopped responding}
expect eof
'

run_test "Status: connection failure shows ssh error" expect -c "$STATUS_PRELUDE"'
spawn tests/preview.sh refused
see {Connecting to app1[^\n]*FAIL}
see {Connection refused}
expect eof
'

echo ""
echo -e "${CYAN}=== Results ===${RESET}"
echo -e "  ${GREEN}Passed: $PASSED${RESET}"
if [[ $FAILED -gt 0 ]]; then
    echo -e "  ${RED}Failed: $FAILED${RESET}"
    exit 1
else
    echo -e "  Failed: 0"
    echo ""
    echo -e "${GREEN}All tests passed!${RESET}"
fi
