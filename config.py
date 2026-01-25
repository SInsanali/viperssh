"""Configuration loading for ViperSSH."""

from pathlib import Path
from typing import Optional


class Config:
    """Loads and manages ViperSSH configuration."""

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        self.config_dir = Path(config_dir) if config_dir else Path(__file__).parent / "etc"
        self.suffixes_file = self.config_dir / "suffixes.conf"
        self.host_list_dir = self.config_dir / "host_list"

        self._suffixes: dict[str, str] = {}
        self._environments: list[str] = []
        self._hosts_cache: dict[str, list[str]] = {}

    def load(self) -> None:
        """Load all configuration files."""
        self._load_suffixes()
        self._discover_environments()

    def _read_config_lines(self, filepath: Path) -> list[str]:
        """Read non-empty, non-comment lines from a config file."""
        lines = []
        for line in filepath.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                lines.append(stripped)
        return lines

    def _load_suffixes(self) -> None:
        """Load environment suffixes from suffixes.conf."""
        if not self.suffixes_file.exists():
            self._raise_missing_file_error(
                self.suffixes_file,
                self.suffixes_file.parent / "suffixes.conf.example"
            )

        self._suffixes = {}
        for line in self._read_config_lines(self.suffixes_file):
            if "=" in line:
                key, value = line.split("=", 1)
                self._suffixes[key.strip()] = value.strip()

    def _discover_environments(self) -> None:
        """Discover available environments from host list files."""
        if not self.host_list_dir.exists():
            raise FileNotFoundError(f"Host list directory not found: {self.host_list_dir}")

        self._environments = sorted(
            host_file.stem for host_file in self.host_list_dir.glob("*.hosts")
        )

        if not self._environments:
            examples = list(self.host_list_dir.glob("*.hosts.example"))
            if examples:
                example = examples[0]
                target = example.with_suffix("").with_suffix(".hosts")
                raise FileNotFoundError(
                    f"No environment files found in {self.host_list_dir}\n"
                    f"Copy an example file to get started:\n"
                    f"  cp {example} {target}"
                )
            raise FileNotFoundError(f"No .hosts files found in {self.host_list_dir}")

    def _raise_missing_file_error(self, missing: Path, example: Path) -> None:
        """Raise a helpful error for missing config files."""
        if example.exists():
            raise FileNotFoundError(
                f"Configuration not found: {missing}\n"
                f"Copy the example file to get started:\n"
                f"  cp {example} {missing}"
            )
        raise FileNotFoundError(f"Configuration file not found: {missing}")

    @property
    def environments(self) -> list[str]:
        """Return list of available environments."""
        return self._environments.copy()

    def display_name(self, environment: str) -> str:
        """Convert internal env name to display name (underscores to spaces)."""
        return environment.replace("_", " ")

    def get_suffix(self, environment: str) -> str:
        """Get the FQDN suffix for an environment."""
        return self._suffixes.get(environment, "")

    def get_hosts(self, environment: str) -> list[str]:
        """Get list of hosts for an environment."""
        if environment in self._hosts_cache:
            return self._hosts_cache[environment].copy()

        host_file = self.host_list_dir / f"{environment}.hosts"
        if not host_file.exists():
            return []

        hosts = self._read_config_lines(host_file)
        self._hosts_cache[environment] = hosts
        return hosts.copy()

    def build_target(self, environment: str, hostname: str) -> str:
        """Build the full connection target for a host.

        If hostname contains '.' or '@', use as-is.
        Otherwise, append the environment suffix.
        """
        if "." in hostname or "@" in hostname:
            return hostname
        return f"{hostname}{self.get_suffix(environment)}"
