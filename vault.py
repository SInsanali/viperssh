"""Password vault for ViperSSH — AES-encrypted per-environment password storage."""

import base64
import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

VAULT_DIR = Path(__file__).resolve().parent
VAULT_CONFIG = VAULT_DIR / ".viper_vault_config"
VAULT_FILE = VAULT_DIR / ".viper_vault"
VAULT_PASS_FILE = VAULT_DIR / ".viper_vault_pass"

PBKDF2_ITERATIONS = 480_000
SALT_SIZE = 16


def _write_secure(path: Path, data: bytes) -> None:
    """Write data to a file atomically with 0600 permissions."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_")
    try:
        os.write(fd, data)
        os.fchmod(fd, 0o600)
        os.close(fd)
        os.rename(tmp, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _write_secure_text(path: Path, text: str) -> None:
    """Write text to a file atomically with 0600 permissions."""
    _write_secure(path, text.encode())


class Vault:
    """Encrypted password vault scoped by environment name."""

    def __init__(self) -> None:
        self._fernet: Optional[Fernet] = None
        self._master_pw: Optional[str] = None
        self._passwords: dict[str, str] = {}

    # ── Config toggle ──

    def is_enabled(self) -> bool:
        try:
            return VAULT_CONFIG.read_text().strip() == "enabled"
        except OSError:
            return False

    def set_enabled(self, enabled: bool) -> None:
        _write_secure_text(VAULT_CONFIG, "enabled" if enabled else "disabled")

    # ── Master password helpers ──

    def get_master_from_file(self) -> Optional[str]:
        """Read master password from .viper_vault_pass if it exists."""
        try:
            pw = VAULT_PASS_FILE.read_text().strip()
            return pw if pw else None
        except OSError:
            return None

    def vault_exists(self) -> bool:
        return VAULT_FILE.exists()

    # ── Key derivation ──

    @staticmethod
    def _derive_key(master_pw: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        return base64.urlsafe_b64encode(kdf.derive(master_pw.encode()))

    # ── Create / Unlock ──

    def create(self, master_pw: str) -> None:
        """Create a new empty vault with the given master password."""
        self._master_pw = master_pw
        self._passwords = {}
        self._fernet = Fernet(self._derive_key(master_pw, os.urandom(SALT_SIZE)))
        self._save()

    def unlock(self, master_pw: str) -> bool:
        """Decrypt the vault file. Returns True on success."""
        try:
            raw = VAULT_FILE.read_bytes()
        except OSError:
            return False

        if len(raw) < SALT_SIZE:
            return False

        salt = raw[:SALT_SIZE]
        encrypted = raw[SALT_SIZE:]

        key = self._derive_key(master_pw, salt)
        fernet = Fernet(key)

        try:
            plaintext = fernet.decrypt(encrypted)
        except InvalidToken:
            return False

        try:
            data = json.loads(plaintext)
        except (json.JSONDecodeError, ValueError):
            return False

        if not isinstance(data, dict):
            return False

        self._fernet = fernet
        self._master_pw = master_pw
        self._passwords = data
        return True

    def is_unlocked(self) -> bool:
        return self._fernet is not None

    # ── CRUD ──

    def get_password(self, env: str) -> Optional[str]:
        return self._passwords.get(env)

    def set_password(self, env: str, pw: str) -> None:
        self._passwords[env] = pw
        self._save()

    def delete_password(self, env: str) -> None:
        self._passwords.pop(env, None)
        self._save()

    def list_environments(self, config_envs: list[str]) -> dict[str, bool]:
        """Return {env_name: has_saved_password} for all config environments."""
        return {env: env in self._passwords for env in config_envs}

    # ── Persistence ──

    def _save(self) -> None:
        """Encrypt and write the vault with a fresh salt."""
        if self._master_pw is None:
            return

        salt = os.urandom(SALT_SIZE)
        key = self._derive_key(self._master_pw, salt)
        fernet = Fernet(key)
        encrypted = fernet.encrypt(json.dumps(self._passwords).encode())
        _write_secure(VAULT_FILE, salt + encrypted)
        self._fernet = fernet
