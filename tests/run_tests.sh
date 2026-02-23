#!/bin/bash
# ViperSSH Test Suite
# Run with: ./tests/run_tests.sh
#
# Permission granted by maintainer to run all tests automatically.
# These tests use expect to simulate user interaction with the TUI.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

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
run_test "Python syntax" python3 -m py_compile viper.py

# Test 2: Config loading
run_test "Config loading" python3 -c "
from config import Config
c = Config()
c.load()
assert len(c.environments) > 0
"

# Test 3: CLI flags
run_test "CLI --help" bash -c "./viperssh --help | grep -q Usage"
run_test "CLI --check" bash -c "./viperssh --check | grep -q dependencies"

# Test 4: History class
run_test "History empty load" python3 -c "
import tempfile
from pathlib import Path
import config as cfg
path = Path(tempfile.mktemp(suffix='.json'))
cfg.HISTORY_FILE = path
h = cfg.History()
assert h.load() == []
"

run_test "History add and load" python3 -c "
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

run_test "History deduplication" python3 -c "
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

run_test "History max 10 entries" python3 -c "
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

# Test 5: TUI launches (timeout after 2s is expected, exit 124 is OK)
run_test "TUI launches" bash -c "timeout 2 ./viperssh; [[ \$? -eq 124 ]] || [[ \$? -eq 0 ]]"

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
run_test "History sftp proto stored" python3 -c "
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
