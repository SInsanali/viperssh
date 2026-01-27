"""Configuration loading for ViperSSH."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class HostInfo:
    """Represents a host with display name and connection target."""

    display_name: str
    target: str


class Config:
    """Loads and manages ViperSSH configuration from hosts.yaml."""

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        self.config_dir = Path(config_dir) if config_dir else Path(__file__).parent / "etc"
        self.config_file = self.config_dir / "hosts.yaml"
        self._data: dict = {}
        self._environments: list[str] = []

    def load(self) -> None:
        """Load configuration from hosts.yaml."""
        if not self.config_file.exists():
            example = self.config_file.with_suffix(".yaml.example")
            if example.exists():
                raise FileNotFoundError(
                    f"Configuration not found: {self.config_file}\n"
                    f"Copy the example file to get started:\n"
                    f"  cp {example} {self.config_file}"
                )
            raise FileNotFoundError(f"Configuration file not found: {self.config_file}")

        with open(self.config_file) as f:
            data = yaml.safe_load(f)

        if not data or "environments" not in data:
            raise ValueError(f"Invalid config: {self.config_file} must have 'environments' section")

        self._data = data["environments"]
        self._environments = list(self._data.keys())

        if not self._environments:
            raise ValueError(f"No environments defined in {self.config_file}")

    @property
    def environments(self) -> list[str]:
        """Return list of available environments."""
        return self._environments.copy()

    def display_name(self, environment: str) -> str:
        """Convert internal env name to display name (underscores to spaces)."""
        return environment.replace("_", " ")

    def get_suffix(self, environment: str) -> str:
        """Get the FQDN suffix for an environment."""
        suffix = self._data.get(environment, {}).get("suffix")
        return suffix if suffix else ""

    def get_hosts(self, environment: str) -> list[HostInfo]:
        """Get list of hosts for an environment.

        Supports two formats:
        - String: "hostname" -> HostInfo("hostname", "hostname")
        - Dict: {alias: target} -> HostInfo(alias, target)
        """
        raw_hosts = self._data.get(environment, {}).get("hosts", [])
        result = []
        for h in raw_hosts:
            if isinstance(h, str):
                result.append(HostInfo(h, h))
            elif isinstance(h, dict) and len(h) == 1:
                alias, target = next(iter(h.items()))
                result.append(HostInfo(alias, target))
        return result

    def build_target(self, environment: str, hostname: str) -> str:
        """Build the full connection target for a host.

        If hostname contains '.' or '@', use as-is.
        Otherwise, append the environment suffix.
        """
        if "." in hostname or "@" in hostname:
            return hostname
        return f"{hostname}{self.get_suffix(environment)}"
