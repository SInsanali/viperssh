"""Central path resolver for ViperSSH.

Single source of truth for every filesystem path the app uses. All modules
import their paths from here instead of recomputing ``Path(__file__).parent``.

Layout (relative to the repo root, which is the parent of this ``lib/`` dir):

    bin/   executables (viper.py, expect.sh)
    lib/   library modules (this file, config.py, vault.py)
    etc/   user configuration (hosts.yaml)
    var/   runtime state (history, favorites, theme, vault/)
"""

import os
from pathlib import Path

# Repo root is the parent of lib/.
ROOT = Path(__file__).resolve().parent.parent

BIN = ROOT / "bin"
ETC = ROOT / "etc"
VAR = ROOT / "var"
VAULT_DIR = VAR / "vault"

# Executables
EXPECT_SCRIPT = BIN / "expect.sh"

# Configuration
DEFAULT_CONFIG_DIR = ETC

# Runtime state
HISTORY_FILE = VAR / "history.json"
FAVORITES_FILE = VAR / "favorites.json"
THEME_FILE = VAR / "theme"
INITIALIZED_MARKER = VAR / "initialized"
LAUNCH_ANIM_FILE = VAR / "launch_anim"
SNAKE_ANIM_FILE = VAR / "snake_anim"
SNAKE_SCORE_FILE = VAR / "snake_score"   # easter-egg game high score

# Vault
VAULT_CONFIG = VAULT_DIR / "config"
VAULT_FILE = VAULT_DIR / "vault.enc"
VAULT_PASS_FILE = VAULT_DIR / "master"


def ensure_dirs() -> None:
    """Create the runtime state directories if they don't exist."""
    VAR.mkdir(parents=True, exist_ok=True)
    VAULT_DIR.mkdir(parents=True, exist_ok=True)


# Legacy root dotfile -> new var/ location. Used by migrate_legacy().
_LEGACY_MAP = {
    ROOT / ".viper_history": HISTORY_FILE,
    ROOT / ".viper_favorites": FAVORITES_FILE,
    ROOT / ".viper_theme": THEME_FILE,
    ROOT / ".viperssh_initialized": INITIALIZED_MARKER,
    ROOT / ".viper_vault_config": VAULT_CONFIG,
    ROOT / ".viper_vault": VAULT_FILE,
    ROOT / ".viper_vault_pass": VAULT_PASS_FILE,
}


def migrate_legacy() -> None:
    """Move pre-reorg root dotfiles into var/. Idempotent and best-effort.

    Only moves a file when the legacy path exists and the new target does not,
    so it's safe to call on every startup and never clobbers newer state.
    """
    moved = False
    for old, new in _LEGACY_MAP.items():
        try:
            if old.exists() and not new.exists():
                if not moved:
                    ensure_dirs()
                    moved = True
                new.parent.mkdir(parents=True, exist_ok=True)
                os.replace(old, new)
        except OSError:
            pass
