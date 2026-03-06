#!/usr/bin/env python3
"""ViperSSH - A TUI SSH connection manager."""

import argparse
import getpass
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple, Optional

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Label, ListItem, ListView, Static

from config import Config, Favorites, History, HostInfo
from vault import Vault


class ConnectionRequest(NamedTuple):
    """Result returned when the user selects a host to connect to."""

    target: str
    proto: str = "ssh"
    env_name: Optional[str] = None


# Theme definitions
THEMES = {
    "viper": {
        "name": "Viper (Default)",
        "bg": "#0a0a0a",
        "panel_bg": "#0d0d0d",
        "env_color": "#00ff00",
        "host_color": "#ff0000",
        "accent": "#ff00ff",
    },
    "ocean": {
        "name": "Ocean",
        "bg": "#0a1628",
        "panel_bg": "#0d1e36",
        "env_color": "#00bfff",
        "host_color": "#7fffd4",
        "accent": "#ff6b9d",
    },
    "sunset": {
        "name": "Sunset",
        "bg": "#1a0a0a",
        "panel_bg": "#2d0d0d",
        "env_color": "#ff6600",
        "host_color": "#ffcc00",
        "accent": "#ff0066",
    },
    "matrix": {
        "name": "Matrix",
        "bg": "#000000",
        "panel_bg": "#001100",
        "env_color": "#00ff00",
        "host_color": "#00dd00",
        "accent": "#00ff00",
    },
    "frost": {
        "name": "Frost",
        "bg": "#0a1a2a",
        "panel_bg": "#102030",
        "env_color": "#88ccff",
        "host_color": "#aaddff",
        "accent": "#ff88cc",
    },
    # VS Code inspired themes
    "dracula": {
        "name": "Dracula",
        "bg": "#282a36",
        "panel_bg": "#44475a",
        "env_color": "#50fa7b",
        "host_color": "#ff79c6",
        "accent": "#f1fa8c",
    },
    "onedark": {
        "name": "One Dark",
        "bg": "#282c34",
        "panel_bg": "#3e4451",
        "env_color": "#98c379",
        "host_color": "#e06c75",
        "accent": "#61afef",
    },
    "monokai": {
        "name": "Monokai",
        "bg": "#272822",
        "panel_bg": "#3e3d32",
        "env_color": "#a6e22e",
        "host_color": "#f92672",
        "accent": "#e6db74",
    },
    "nord": {
        "name": "Nord",
        "bg": "#2e3440",
        "panel_bg": "#3b4252",
        "env_color": "#a3be8c",
        "host_color": "#bf616a",
        "accent": "#88c0d0",
    },
    "gruvbox": {
        "name": "Gruvbox",
        "bg": "#282828",
        "panel_bg": "#3c3836",
        "env_color": "#b8bb26",
        "host_color": "#fb4934",
        "accent": "#fabd2f",
    },
    "solarized": {
        "name": "Solarized Dark",
        "bg": "#002b36",
        "panel_bg": "#073642",
        "env_color": "#859900",
        "host_color": "#dc322f",
        "accent": "#268bd2",
    },
    "tokyonight": {
        "name": "Tokyo Night",
        "bg": "#1a1b26",
        "panel_bg": "#24283b",
        "env_color": "#9ece6a",
        "host_color": "#f7768e",
        "accent": "#7aa2f7",
    },
    "catppuccin": {
        "name": "Catppuccin",
        "bg": "#1e1e2e",
        "panel_bg": "#313244",
        "env_color": "#a6e3a1",
        "host_color": "#f38ba8",
        "accent": "#cba6f7",
    },
}

THEME_CONFIG_FILE = Path(__file__).resolve().parent / ".viper_theme"

# ASCII Art Banner
VIPER_BANNER = """
[bold green]██╗   ██╗██╗██████╗ ███████╗██████╗ [/][bold red]███████╗███████╗██╗  ██╗[/]
[bold green]██║   ██║██║██╔══██╗██╔════╝██╔══██╗[/][bold red]██╔════╝██╔════╝██║  ██║[/]
[bold green]██║   ██║██║██████╔╝█████╗  ██████╔╝[/][bold red]███████╗███████╗███████║[/]
[bold green]╚██╗ ██╔╝██║██╔═══╝ ██╔══╝  ██╔══██╗[/][bold red]╚════██║╚════██║██╔══██║[/]
[bold green] ╚████╔╝ ██║██║     ███████╗██║  ██║[/][bold red]███████║███████║██║  ██║[/]
[bold green]  ╚═══╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝[/][bold red]╚══════╝╚══════╝╚═╝  ╚═╝[/]
[dim green]═══════════════════════════════════════════════════════════════[/]"""

# Help menu content
HELP_TEXT = """[bold red]  NAVIGATION[/]
[dim]  ──────────────────────────────[/]
  [bold red]↑ ↓[/]  [dim]or[/]  [bold red]j k[/]   Move up/down
  [bold red]→[/]  [dim]or[/]  [bold red]Enter[/]  Select / Enter
  [bold red]←[/]  [dim]or[/]  [bold red]Esc[/]    Go back
  [bold red]Tab[/]           Switch panels

[bold green]  SEARCH[/]
[dim]  ──────────────────────────────[/]
  [bold red]/[/]             Focus search box
  [bold red]Esc[/]           Exit search
  [bold red]Enter[/]         Jump to results

[bold #ff00ff]  ACTIONS[/]
[dim]  ──────────────────────────────[/]
  [bold red]?[/]  [dim]or[/]  [bold red]h[/]      Toggle this menu
  [bold red]t[/]             Theme selector
  [bold red]r[/]             Recent connections
  [bold red]v[/]             Password vault
  [bold red]f[/]             Toggle favorite
  [bold red]s[/]             SFTP connect
  [bold red]q[/]             Quit
[dim]──────────────────────────────────[/]
[dim]       Press any key to close[/]"""


class HelpScreen(ModalScreen):
    """Modal help screen - closes on any key or click."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("?", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-container"):
            yield Static("[bold red]QUICK MENU[/]", id="help-title")
            yield Static(HELP_TEXT, id="help-body")

    def on_key(self, event) -> None:
        self.dismiss()

    def on_click(self, event) -> None:
        self.dismiss()


class ThemeListItem(ListItem):
    """A list item representing a theme."""

    def __init__(self, theme_id: str, theme_name: str, is_active: bool, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.theme_id = theme_id
        self.theme_name = theme_name
        self.is_active = is_active

    def compose(self) -> ComposeResult:
        marker = "[bold green]●[/]" if self.is_active else "[dim]○[/]"
        yield Label(f"  {marker} {self.theme_name}", classes="theme-label")

    def watch_highlighted(self, highlighted: bool) -> None:
        try:
            label = self.query_one(".theme-label")
        except Exception:
            return
        marker = "[bold green]●[/]" if self.is_active else "[dim]○[/]"
        if highlighted:
            label.update(f"[bold red]>[/] {marker} [bold]{self.theme_name}[/]")
        else:
            label.update(f"  {marker} {self.theme_name}")


class ThemeScreen(ModalScreen):
    """Modal theme selector screen."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("t", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    CSS = """
    ThemeScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }

    #theme-container {
        width: 50;
        height: auto;
        background: #0d0d0d;
        border: heavy #ff0000;
        padding: 1 2;
    }

    #theme-title {
        text-align: center;
        text-style: bold;
        color: #ff0000;
        padding-bottom: 1;
    }

    #theme-list {
        height: auto;
        max-height: 16;
    }

    #theme-list > ListItem {
        padding: 0 1;
    }

    #theme-list > ListItem.--highlight {
        background: #330000;
    }

    #theme-hint {
        text-align: center;
        color: #666666;
        padding-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="theme-container"):
            yield Static("[bold red]SELECT THEME[/]", id="theme-title")
            yield ListView(id="theme-list")
            yield Static("[dim]Enter[/] apply  [dim]Esc[/] close", id="theme-hint")

    def on_mount(self) -> None:
        """Populate theme list."""
        theme_list = self.query_one("#theme-list", ListView)
        current_theme = self.app._active_theme
        for theme_id, theme in THEMES.items():
            is_active = (theme_id == current_theme)
            item = ThemeListItem(theme_id, theme["name"], is_active)
            theme_list.append(item)
        theme_list.focus()
        self.call_later(lambda: setattr(theme_list, "index", 0))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle theme selection."""
        if isinstance(event.item, ThemeListItem):
            self.dismiss(event.item.theme_id)

    def action_cursor_down(self) -> None:
        self.query_one("#theme-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#theme-list", ListView).action_cursor_up()


def _relative_time(ts: float) -> str:
    """Return a human-friendly relative time string."""
    delta = int(time.time() - ts)
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


class HistoryListItem(ListItem):
    """A list item representing a history entry."""

    def __init__(self, target: str, ts: float, proto: str = "ssh", *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.target = target
        self.ts = ts
        self.proto = proto

    def _label_text(self, highlighted: bool = False) -> str:
        rel = _relative_time(self.ts)
        proto_tag = f" [dim cyan][{self.proto}][/]" if self.proto != "ssh" else ""
        if highlighted:
            return f"[bold red]>[/] {self.target}{proto_tag}  [dim yellow]{rel}[/]"
        return f"  {self.target}{proto_tag}  [dim yellow]{rel}[/]"

    def compose(self) -> ComposeResult:
        yield Label(self._label_text(), classes="history-label")

    def watch_highlighted(self, highlighted: bool) -> None:
        try:
            label = self.query_one(".history-label")
        except Exception:
            return
        label.update(self._label_text(highlighted))


class HistorySectionItem(ListItem):
    """A non-interactive section header in the history list."""

    def __init__(self, title: str, color: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.title = title
        self.color = color
        self.disabled = True

    def compose(self) -> ComposeResult:
        line = "─" * 38
        yield Label(f"[bold {self.color}]{self.title}[/] [dim]{line}[/]", classes="section-label")

    def watch_highlighted(self, highlighted: bool) -> None:
        pass


class HistoryScreen(ModalScreen):
    """Modal recent connections screen."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("r", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    CSS = """
    HistoryScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }

    #history-container {
        width: 50;
        height: auto;
        background: #0d0d0d;
        border: heavy #ff00ff;
        padding: 1 2;
    }

    #history-title {
        text-align: center;
        text-style: bold;
        color: #ff00ff;
        padding-bottom: 1;
    }

    #history-list {
        height: auto;
        max-height: 20;
    }

    #history-list > ListItem {
        padding: 0 1;
    }

    #history-list > ListItem.--highlight {
        background: #330033;
    }

    #history-empty {
        text-align: center;
        color: #444444;
        padding: 1 0;
    }

    #history-hint {
        text-align: center;
        color: #666666;
        padding-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="history-container"):
            yield Static("[bold #ff00ff]RECENT CONNECTIONS[/]", id="history-title")
            yield ListView(id="history-list")
            yield Static("", id="history-empty")
            yield Static("[dim]Enter[/] connect  [dim]Esc[/] close", id="history-hint")

    def on_mount(self) -> None:
        history = History().load()
        history_list = self.query_one("#history-list", ListView)
        empty_label = self.query_one("#history-empty", Static)

        if not history:
            empty_label.update("[dim]No history yet[/]")
            return

        ssh_entries = [e for e in history if e.get("proto", "ssh") == "ssh"]
        sftp_entries = [e for e in history if e.get("proto") == "sftp"]

        if ssh_entries:
            history_list.append(HistorySectionItem("SSH", "#00ff00"))
            for entry in ssh_entries:
                history_list.append(HistoryListItem(entry["target"], entry["ts"], "ssh"))

        if sftp_entries:
            history_list.append(HistorySectionItem("SFTP", "#00bfff"))
            for entry in sftp_entries:
                history_list.append(HistoryListItem(entry["target"], entry["ts"], "sftp"))

        history_list.focus()
        # Skip the section header at index 0 to focus the first selectable item
        self.call_later(lambda: setattr(history_list, "index", 1))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, HistoryListItem):
            self.dismiss(ConnectionRequest(event.item.target, event.item.proto))

    def action_cursor_down(self) -> None:
        self.query_one("#history-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#history-list", ListView).action_cursor_up()


class VaultEnvListItem(ListItem):
    """A list item representing an environment in the vault modal."""

    def __init__(self, env_name: str, has_password: bool, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.env_name = env_name
        self.has_password = has_password

    def _label_text(self, highlighted: bool = False) -> str:
        if self.has_password:
            marker = "[bold green]●[/]"
            tag = " [dim green]saved[/]"
        else:
            marker = "[dim red]○[/]"
            tag = " [dim red]no pw[/]"
        name = self.env_name.replace("_", " ")
        if highlighted:
            return f"[bold red]>[/] {marker} [bold]{name}[/]{tag}"
        return f"  {marker} {name}{tag}"

    def compose(self) -> ComposeResult:
        yield Label(self._label_text(), classes="vault-env-label")

    def watch_highlighted(self, highlighted: bool) -> None:
        try:
            label = self.query_one(".vault-env-label")
        except Exception:
            return
        label.update(self._label_text(highlighted))


class VaultScreen(ModalScreen):
    """Modal vault management screen."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("v", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("e", "toggle_vault", "Toggle"),
        Binding("d", "delete_password", "Delete"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    CSS = """
    VaultScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }

    #vault-container {
        width: 50;
        height: auto;
        background: #0d0d0d;
        border: heavy #ff00ff;
        padding: 1 2;
    }

    #vault-title {
        text-align: center;
        text-style: bold;
        color: #ff00ff;
        padding-bottom: 1;
    }

    #vault-status {
        text-align: center;
        padding-bottom: 1;
    }

    #vault-separator {
        color: #333333;
        padding-bottom: 1;
    }

    #vault-env-list {
        height: auto;
        max-height: 16;
    }

    #vault-env-list > ListItem {
        padding: 0 1;
    }

    #vault-env-list > ListItem.--highlight {
        background: #330033;
    }

    #vault-hint {
        text-align: center;
        color: #666666;
        padding-top: 1;
    }

    #vault-password-input {
        margin: 1 0;
        border: solid #ff00ff 50%;
        background: #1a1a1a;
        padding: 0 1;
    }

    #vault-input-label {
        text-align: center;
        color: #ff00ff;
        padding-top: 1;
    }
    """

    def __init__(self, vault: Vault, config_envs: list[str], *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.vault = vault
        self.config_envs = config_envs
        self._editing_env: Optional[str] = None

    def compose(self) -> ComposeResult:
        with Vertical(id="vault-container"):
            yield Static("[bold #ff00ff]PASSWORD VAULT[/]", id="vault-title")
            yield Static("", id="vault-status")
            yield Static("[dim]──────────────────────────────────────────[/]", id="vault-separator")
            yield ListView(id="vault-env-list")
            yield Static("", id="vault-input-label")
            yield Input(placeholder="enter password...", password=True, id="vault-password-input")
            yield Static("", id="vault-hint")

    def on_mount(self) -> None:
        self._update_status()
        self._populate_list()
        pw_input = self.query_one("#vault-password-input", Input)
        pw_input.display = False
        input_label = self.query_one("#vault-input-label", Static)
        input_label.display = False
        vault_list = self.query_one("#vault-env-list", ListView)
        vault_list.focus()
        if self.config_envs:
            self.call_later(lambda: setattr(vault_list, "index", 0))

    def _update_status(self) -> None:
        status = self.query_one("#vault-status", Static)
        enabled = self.vault.is_enabled()
        unlocked = self.vault.is_unlocked()
        if enabled:
            state = "[bold green]ENABLED[/]"
            lock = " [dim]|[/] [green]unlocked[/]" if unlocked else " [dim]|[/] [red]locked[/]"
        else:
            state = "[bold red]DISABLED[/]"
            lock = ""
        status.update(f"  Status: {state}{lock}")
        hint = self.query_one("#vault-hint", Static)
        hint.update("[dim]e[/] toggle  [dim]Enter[/] set pw  [dim]d[/] delete  [dim]Esc[/] close")

    def _populate_list(self) -> None:
        vault_list = self.query_one("#vault-env-list", ListView)
        vault_list.clear()
        if not self.vault.is_unlocked():
            return
        env_map = self.vault.list_environments(self.config_envs)
        for env, has_pw in env_map.items():
            vault_list.append(VaultEnvListItem(env, has_pw))

    def action_toggle_vault(self) -> None:
        enabled = self.vault.is_enabled()
        self.vault.set_enabled(not enabled)
        self._update_status()

    def action_delete_password(self) -> None:
        if not self.vault.is_unlocked():
            return
        vault_list = self.query_one("#vault-env-list", ListView)
        if vault_list.index is not None and vault_list.index < len(vault_list.children):
            item = vault_list.children[vault_list.index]
            if isinstance(item, VaultEnvListItem) and item.has_password:
                self.vault.delete_password(item.env_name)
                self._populate_list()
                if vault_list.children:
                    self.call_later(lambda: setattr(vault_list, "index", 0))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not self.vault.is_unlocked():
            return
        if isinstance(event.item, VaultEnvListItem):
            self._editing_env = event.item.env_name
            input_label = self.query_one("#vault-input-label", Static)
            input_label.display = True
            input_label.update(f"[bold #ff00ff]Password for[/] [bold]{event.item.env_name.replace('_', ' ')}[/]")
            pw_input = self.query_one("#vault-password-input", Input)
            pw_input.display = True
            pw_input.value = ""
            pw_input.focus()
            hint = self.query_one("#vault-hint", Static)
            hint.update("[dim]Enter[/] save  [dim]Esc[/] cancel")

    @on(Input.Submitted, "#vault-password-input")
    def on_password_submitted(self, event: Input.Submitted) -> None:
        if self._editing_env and event.value:
            self.vault.set_password(self._editing_env, event.value)
        self._editing_env = None
        pw_input = self.query_one("#vault-password-input", Input)
        pw_input.display = False
        pw_input.value = ""
        input_label = self.query_one("#vault-input-label", Static)
        input_label.display = False
        self._populate_list()
        self._update_status()
        vault_list = self.query_one("#vault-env-list", ListView)
        vault_list.focus()
        if vault_list.children:
            self.call_later(lambda: setattr(vault_list, "index", 0))

    def action_cursor_down(self) -> None:
        self.query_one("#vault-env-list", ListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#vault-env-list", ListView).action_cursor_up()


class HostListItem(ListItem):
    """A list item representing a host."""

    def __init__(self, host_info: HostInfo, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.display_name = host_info.display_name
        self.target = host_info.target
        self.is_alias = host_info.is_alias

    def compose(self) -> ComposeResult:
        yield Label(f"  {self.display_name}", classes="item-label")

    def watch_highlighted(self, highlighted: bool) -> None:
        try:
            label = self.query_one(".item-label")
        except Exception:
            return
        if highlighted:
            label.update(f"[bold red]> {self.display_name}[/]")
        else:
            label.update(f"  {self.display_name}")


class FavSectionItem(ListItem):
    """A non-interactive section header in the favorites list."""

    def __init__(self, env_display: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.env_display = env_display
        self.disabled = True

    def compose(self) -> ComposeResult:
        line = "\u2500" * 30
        yield Label(f"[bold yellow]{self.env_display}[/] [dim]{line}[/]", classes="section-label")

    def watch_highlighted(self, highlighted: bool) -> None:
        pass


class FavHostListItem(HostListItem):
    """A host list item from the favorites pseudo-environment."""

    def __init__(self, host_info: HostInfo, env_name: str, *args, **kwargs) -> None:
        super().__init__(host_info, *args, **kwargs)
        self.env_name = env_name

    def compose(self) -> ComposeResult:
        yield Label(f"  {self.display_name}", classes="item-label")

    def watch_highlighted(self, highlighted: bool) -> None:
        try:
            label = self.query_one(".item-label")
        except Exception:
            return
        if highlighted:
            label.update(f"[bold red]> {self.display_name}[/]")
        else:
            label.update(f"  {self.display_name}")


class EnvListItem(ListItem):
    """A list item representing an environment."""

    def __init__(self, env_name: str, display_name: str, host_count: int, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.env_name = env_name
        self.display_name = display_name
        self.host_count = host_count

    def compose(self) -> ComposeResult:
        yield Label(f"  {self.display_name:<20} [dim red]({self.host_count})[/]", classes="item-label")

    def watch_highlighted(self, highlighted: bool) -> None:
        try:
            label = self.query_one(".item-label")
        except Exception:
            return
        if highlighted:
            label.update(f"[bold green]> {self.display_name:<20}[/] [red]({self.host_count})[/]")
        else:
            label.update(f"  {self.display_name:<20} [dim red]({self.host_count})[/]")


class ViperApp(App):
    """Main Viper TUI application."""

    COMMANDS = set()

    CSS = """
    Screen {
        background: #0a0a0a;
        layout: vertical;
    }

    #banner {
        height: auto;
        text-align: center;
        padding: 1 0;
        dock: top;
    }

    #main-container {
        layout: horizontal;
        height: 1fr;
        margin: 0 0 0 2;
    }

    #env-panel {
        border: heavy #00ff00;
        background: #0d0d0d;
        padding: 0 1;
        width: 1fr;
        border-title-color: #00ff00;
        border-title-style: bold;
    }

    #host-panel {
        border: heavy #ff0000;
        background: #0d0d0d;
        padding: 0 1;
        width: 2fr;
        border-title-color: #ff0000;
        border-title-style: bold;
    }

    #env-list {
        height: 1fr;
        background: transparent;
        scrollbar-color: #00ff00;
        scrollbar-color-hover: #00ff00;
        scrollbar-color-active: #00ff00;
    }

    #env-filter-box {
        dock: top;
        margin: 1 0;
        border: solid #00ff00 50%;
        background: #1a1a1a;
        padding: 0 1;
        height: 3;
    }

    #search-box {
        dock: top;
        margin: 1 0;
        border: solid #ff0000 50%;
        background: #1a1a1a;
        padding: 0 1;
    }

    #search-box:focus {
        border: solid #ff0000;
    }

    #search-box > .input--placeholder {
        color: #444444;
    }

    #status-bar {
        dock: bottom;
        height: 3;
        padding: 1;
        background: #1a1a1a;
    }

    ListView {
        background: transparent;
    }

    ListView > ListItem {
        padding: 0 1;
        color: #666666;
        background: transparent;
    }

    ListView > ListItem:hover {
        background: #1a1a1a;
    }

    /* Environment list highlighting */
    #env-list > ListItem.--highlight {
        background: #003300;
    }

    /* Host columns layout */
    #host-columns {
        height: 1fr;
    }

    #host-list-left, #host-list-right {
        width: 1fr;
        height: 1fr;
        background: transparent;
        scrollbar-color: #ff0000;
    }

    /* Host list highlighting */
    #host-list-left > ListItem.--highlight,
    #host-list-right > ListItem.--highlight {
        background: #330000;
    }

    #target-display {
        text-style: bold;
        color: #ff00ff;
    }

    Footer {
        background: #1a1a1a;
        color: #00ff00;
    }

    Footer > .footer--key {
        background: #002200;
        color: #00ff00;
    }

    Footer > .footer--description {
        color: #888888;
    }

    /* Help modal styling */
    HelpScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }

    #help-container {
        width: 40;
        height: auto;
        background: #0d0d0d;
        border: heavy #ff0000;
        padding: 1 2;
    }

    #help-title {
        text-align: center;
        text-style: bold;
        color: #ff0000;
        padding-bottom: 1;
    }

    #help-body {
        width: auto;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("escape", "escape_back", "Back", show=False),
        Binding("left", "back", "Back", show=False),
        Binding("right", "go_right", "Select", show=False),
        Binding("/", "focus_search", "Search"),
        Binding("enter", "confirm", "Select", show=False),
        Binding("?", "help", "Help"),
        Binding("h", "help", "Help", show=False),
        Binding("t", "open_themes", "Themes"),
        Binding("r", "open_history", "Recent"),
        Binding("v", "open_vault", "Vault"),
        Binding("f", "toggle_favorite", "Fav", show=False),
        Binding("s", "sftp", "SFTP", show=False),
        Binding("q", "quit", "Quit"),
        Binding("tab", "switch_panel", "Switch", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    TITLE = "VIPERSSH"

    def __init__(self, config_dir: Optional[Path] = None, vault: Optional[Vault] = None) -> None:
        super().__init__()
        self.config = Config(config_dir)
        self.vault = vault or Vault()
        self.favorites = Favorites()
        self._fav_env_map: dict[str, str] = {}  # target -> env_name for favorites
        self.selected_env: Optional[str] = None
        self.current_hosts: list[HostInfo] = []
        self.filtered_hosts: list[HostInfo] = []
        self._active_theme = self._load_theme()
        self._saved_env_index: int = 0  # Track env position for search restore

    def _load_theme(self) -> str:
        """Load saved theme from config file."""
        if not THEME_CONFIG_FILE.exists():
            return "viper"
        try:
            return THEME_CONFIG_FILE.read_text().strip()
        except OSError:
            return "viper"

    def _save_theme(self, theme_id: str) -> None:
        """Save theme to config file."""
        try:
            THEME_CONFIG_FILE.write_text(theme_id)
        except OSError:
            pass

    def action_set_theme(self, theme_id: str) -> None:
        """Switch to a different theme."""
        if theme_id not in THEMES:
            return

        theme = THEMES[theme_id]
        self._active_theme = theme_id
        self._save_theme(theme_id)

        # Apply theme colors dynamically
        self.styles.background = theme["bg"]

        # Update panel colors
        env_panel = self.query_one("#env-panel")
        host_panel = self.query_one("#host-panel")

        env_panel.styles.border = ("heavy", theme["env_color"])
        env_panel.styles.border_title_color = theme["env_color"]

        host_panel.styles.border = ("heavy", theme["host_color"])
        host_panel.styles.border_title_color = theme["host_color"]

        # Update status bar (no border)

        self.notify(f"Theme: {theme['name']}", timeout=2)

    def compose(self) -> ComposeResult:
        yield Static(VIPER_BANNER, id="banner")
        with Horizontal(id="main-container"):
            with Vertical(id="env-panel") as env_panel:
                env_panel.border_title = "ENVIRONMENTS"
                yield Static("", id="env-filter-box")
                yield ListView(id="env-list")
            with Vertical(id="host-panel") as host_panel:
                host_panel.border_title = "HOSTS"
                yield Input(placeholder=">> filter hosts...", id="search-box")
                with Horizontal(id="host-columns"):
                    yield ListView(id="host-list-left")
                    yield ListView(id="host-list-right")
        with Container(id="status-bar"):
            yield Static(">> Select environment  [bold red]↑↓[/] [dim]navigate[/]  [bold red]Enter[/] [dim]select[/]  [bold red]?[/] [dim]help[/]  [bold red]q[/] [dim]quit[/]", id="target-display")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the app after mounting."""
        try:
            self.config.load()
        except FileNotFoundError as e:
            self.notify(str(e), severity="error")
            return

        if self._active_theme != "viper":
            self.action_set_theme(self._active_theme)

        self._populate_environments()
        env_list = self.query_one("#env-list", ListView)
        env_list.focus()
        if self.config.environments:
            self.call_later(lambda: setattr(env_list, "index", 0))

    def _populate_environments(self) -> None:
        """Populate the environment list."""
        env_list = self.query_one("#env-list", ListView)
        env_list.clear()

        # Insert favorites pseudo-environment at top if any exist
        fav_entries = self.favorites.load()
        if fav_entries:
            env_list.append(EnvListItem("__favorites__", "\u2605 Favorites", len(fav_entries)))

        for env in self.config.environments:
            hosts = self.config.get_hosts(env)
            display_name = self.config.display_name(env)
            env_list.append(EnvListItem(env, display_name, len(hosts)))

    def _populate_hosts(self, environment: str) -> None:
        """Populate the host list for the selected environment."""
        self.selected_env = environment
        self._fav_env_map.clear()

        if environment == "__favorites__":
            fav_entries = sorted(self.favorites.load(), key=lambda e: e.get("env_name", ""))
            self.current_hosts = []
            for entry in fav_entries:
                self.current_hosts.append(HostInfo(entry["display_name"], entry["target"], entry.get("is_alias", False)))
                self._fav_env_map[entry["target"]] = entry["env_name"]
        else:
            self.current_hosts = self.config.get_hosts(environment)

        self.filtered_hosts = self.current_hosts.copy()

        # Clear search
        search_box = self.query_one("#search-box", Input)
        search_box.value = ""

        self._refresh_host_list()

        # Update title
        if environment == "__favorites__":
            self.query_one("#host-panel").border_title = "HOSTS :: \u2605 FAVORITES"
        else:
            display = self.config.display_name(environment)
            self.query_one("#host-panel").border_title = f"HOSTS :: {display.upper()}"

    def _refresh_host_list(self) -> None:
        """Refresh the host list with current filter - split into two columns."""
        left_list = self.query_one("#host-list-left", ListView)
        right_list = self.query_one("#host-list-right", ListView)
        left_list.clear()
        right_list.clear()

        is_fav = self.selected_env == "__favorites__"

        if is_fav:
            # Single-column with section headers grouped by environment
            current_env = None
            for host_info in self.filtered_hosts:
                env = self._fav_env_map.get(host_info.target, "")
                if env != current_env:
                    current_env = env
                    left_list.append(FavSectionItem(self.config.display_name(env)))
                left_list.append(FavHostListItem(host_info, env))
        else:
            # Split hosts into two columns
            mid = (len(self.filtered_hosts) + 1) // 2
            left_hosts = self.filtered_hosts[:mid]
            right_hosts = self.filtered_hosts[mid:]

            for host_info in left_hosts:
                left_list.append(HostListItem(host_info))
            for host_info in right_hosts:
                right_list.append(HostListItem(host_info))

    def _update_status(self, message: str) -> None:
        """Update the status bar."""
        status = self.query_one("#target-display", Static)
        status.update(f">> {message}")

    @on(ListView.Highlighted, "#env-list")
    def on_env_highlighted(self, event: ListView.Highlighted) -> None:
        """Preview hosts when hovering over an environment."""
        if isinstance(event.item, EnvListItem) and self.selected_env is None:
            env_name = event.item.env_name
            self._fav_env_map.clear()

            if env_name == "__favorites__":
                fav_entries = sorted(self.favorites.load(), key=lambda e: e.get("env_name", ""))
                hosts = []
                for entry in fav_entries:
                    hosts.append(HostInfo(entry["display_name"], entry["target"], entry.get("is_alias", False)))
                    self._fav_env_map[entry["target"]] = entry["env_name"]
                # Temporarily set selected_env so _refresh_host_list uses FavHostListItem
                self.selected_env = "__favorites__"
            else:
                hosts = self.config.get_hosts(env_name)

            self.current_hosts = hosts
            self.filtered_hosts = hosts.copy()
            self._refresh_host_list()

            if env_name == "__favorites__":
                self.selected_env = None  # Reset — we're just previewing

            self.query_one("#host-panel").border_title = f"HOSTS :: {event.item.display_name.upper()}"
            self._update_status(f"{event.item.display_name}: {len(hosts)} hosts  [bold red]Enter[/] [dim]select[/]  [bold red]↑↓[/] [dim]browse[/]")

    @on(ListView.Selected, "#env-list")
    def on_env_selected(self, event: ListView.Selected) -> None:
        """Handle environment selection."""
        if isinstance(event.item, EnvListItem):
            self._populate_hosts(event.item.env_name)
            self._show_host_nav_status()
            self._focus_host_list()

    @on(ListView.Selected, "#host-list-left")
    @on(ListView.Selected, "#host-list-right")
    def on_host_selected(self, event: ListView.Selected) -> None:
        """Handle host selection - connect to the host."""
        if isinstance(event.item, FavHostListItem):
            env = event.item.env_name
            target = self.config.build_target(env, event.item.target, event.item.is_alias)
            self._update_status(f"Initiating connection: {target}")
            self._connect(target, env_name_override=env)
        elif isinstance(event.item, HostListItem):
            env = self._get_current_env()
            if env:
                target = self.config.build_target(env, event.item.target, event.item.is_alias)
                self._update_status(f"Initiating connection: {target}")
                self._connect(target)

    @on(Input.Changed, "#search-box")
    def on_search_changed(self, event: Input.Changed) -> None:
        """Filter hosts based on search input."""
        query = event.value.lower()
        if query:
            self.filtered_hosts = [h for h in self.current_hosts if query in h.display_name.lower()]
        else:
            self.filtered_hosts = self.current_hosts.copy()
        self._refresh_host_list()
        self._update_status(f"Filter: {len(self.filtered_hosts)} matches  [bold red]Enter[/] [dim]jump[/]  [bold red]Esc[/] [dim]exit search[/]")

    @on(Input.Submitted, "#search-box")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        """When enter is pressed in search, focus the host list."""
        if self.filtered_hosts:
            self._show_host_nav_status()
            self._focus_host_list()

    def on_key(self, event) -> None:
        """Handle escape from search box specially."""
        search_box = self.query_one("#search-box", Input)
        if event.key == "escape" and search_box.has_focus:
            event.prevent_default()
            event.stop()
            search_box.value = ""
            self.filtered_hosts = self.current_hosts.copy()
            self._refresh_host_list()
            self._return_to_env_list()

    def _return_to_env_list(self) -> None:
        """Return focus to environment list and reset state."""
        self._clear_host_highlights()
        env_list = self.query_one("#env-list", ListView)
        # Use saved position from when search was opened
        restore_index = self._saved_env_index
        self.selected_env = None
        search_box = self.query_one("#search-box", Input)
        search_box.value = ""
        self.filtered_hosts = self.current_hosts.copy()
        self._refresh_host_list()
        env_list.index = restore_index
        if env_list.children and restore_index < len(env_list.children):
            env_list.scroll_to_widget(env_list.children[restore_index])
        self._update_status("Select environment  [bold red]↑↓[/] [dim]navigate[/]  [bold red]Enter[/] [dim]select[/]  [bold red]?[/] [dim]help[/]  [bold red]q[/] [dim]quit[/]")
        self.query_one("#host-panel").border_title = "HOSTS"
        self.call_later(env_list.focus)

    def _show_host_nav_status(self) -> None:
        """Show status bar for host navigation."""
        env = self._get_current_env() or "?"
        display_env = "\u2605 Favorites" if env == "__favorites__" else env
        self._update_status(
            f"[bold]{display_env}[/]  "
            f"[bold red]↑↓[/] [dim]navigate[/]  "
            f"[bold red]Enter[/] [dim]ssh[/]  "
            f"[bold red]s[/] [dim]sftp[/]  "
            f"[bold red]f[/] [dim]fav[/]  "
            f"[bold red]/[/] [dim]search[/]  "
            f"[bold red]Esc[/] [dim]back[/]"
        )

    def action_back(self) -> None:
        """Go back - right column to left, left column to environments."""
        env_list = self.query_one("#env-list", ListView)
        left_list = self.query_one("#host-list-left", ListView)
        right_list = self.query_one("#host-list-right", ListView)

        if env_list.has_focus:
            return
        if right_list.has_focus:
            current_row = right_list.index if right_list.index is not None else 0
            self._focus_host_list(current_row)
        elif left_list.has_focus:
            self._return_to_env_list()

    def action_escape_back(self) -> None:
        """Context-aware escape: search->envs, hosts->envs, envs->quit."""
        search_box = self.query_one("#search-box", Input)
        env_list = self.query_one("#env-list", ListView)
        left_list = self.query_one("#host-list-left", ListView)
        right_list = self.query_one("#host-list-right", ListView)

        if search_box.has_focus:
            search_box.value = ""
            self._return_to_env_list()
        elif left_list.has_focus or right_list.has_focus:
            self._return_to_env_list()
        elif env_list.has_focus:
            self.exit()

    def action_focus_search(self) -> None:
        """Focus the search box."""
        # Save current environment position before entering search
        env_list = self.query_one("#env-list", ListView)
        if env_list.index is not None:
            self._saved_env_index = env_list.index
        self.query_one("#search-box", Input).focus()
        self._update_status("Search mode  [dim]type to filter[/]  [bold red]Enter[/] [dim]jump[/]  [bold red]Esc[/] [dim]exit[/]")

    def action_help(self) -> None:
        """Show help screen."""
        self.push_screen(HelpScreen())

    def action_open_themes(self) -> None:
        """Open theme selector screen."""
        def handle_theme(theme_id: Optional[str]) -> None:
            if theme_id:
                self.action_set_theme(theme_id)
        self.push_screen(ThemeScreen(), handle_theme)

    def action_open_history(self) -> None:
        """Open recent connections screen."""
        def handle_history(req: Optional[ConnectionRequest]) -> None:
            if req:
                self._connect(req.target, proto=req.proto)
        self.push_screen(HistoryScreen(), handle_history)

    def action_open_vault(self) -> None:
        """Open vault management screen."""
        envs = self.config.environments
        self.push_screen(VaultScreen(self.vault, envs))

    def action_sftp(self) -> None:
        """Connect to the selected host via SFTP."""
        left_list = self.query_one("#host-list-left", ListView)
        right_list = self.query_one("#host-list-right", ListView)
        if left_list.has_focus or right_list.has_focus:
            focused = left_list if left_list.has_focus else right_list
            item = self._get_selected_item(focused)
            if isinstance(item, FavHostListItem):
                target = self.config.build_target(item.env_name, item.target, item.is_alias)
                self._connect(target, proto="sftp", env_name_override=item.env_name)
            elif isinstance(item, HostListItem):
                env = self._get_current_env()
                if env:
                    target = self.config.build_target(env, item.target, item.is_alias)
                    self._connect(target, proto="sftp")

    def action_toggle_favorite(self) -> None:
        """Toggle favorite on the highlighted host."""
        left_list = self.query_one("#host-list-left", ListView)
        right_list = self.query_one("#host-list-right", ListView)
        if not (left_list.has_focus or right_list.has_focus):
            return
        focused = left_list if left_list.has_focus else right_list
        item = self._get_selected_item(focused)
        if not item:
            return

        if isinstance(item, FavHostListItem):
            # Remove from favorites
            self.favorites.remove(item.target, item.env_name)
            self.notify(f"Removed {item.display_name} from favorites", timeout=2)
            # Refresh the favorites view
            self._populate_hosts("__favorites__")
            self._populate_environments()
            # If no more favorites, go back to env list
            if not self.favorites.load():
                self._return_to_env_list()
            else:
                self._focus_host_list()
        else:
            # Add to favorites — resolve env_name from current context
            env = self._get_current_env()
            if env and env != "__favorites__":
                if self.favorites.is_favorite(item.target, env):
                    self.favorites.remove(item.target, env)
                    self.notify(f"Removed {item.display_name} from favorites", timeout=2)
                else:
                    self.favorites.add(item.target, item.display_name, env, item.is_alias)
                    self.notify(f"Added {item.display_name} to favorites \u2605", timeout=2)
                self._populate_environments()

    def action_switch_panel(self) -> None:
        """Switch focus between environment and host panels."""
        env_list = self.query_one("#env-list", ListView)
        left_list = self.query_one("#host-list-left", ListView)
        right_list = self.query_one("#host-list-right", ListView)

        if env_list.has_focus:
            left_list.focus()
        elif left_list.has_focus:
            right_list.focus()
        else:
            env_list.focus()

    def action_cursor_down(self) -> None:
        """Move cursor down (vim-style j)."""
        focused = self.focused
        if isinstance(focused, ListView):
            focused.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up (vim-style k)."""
        focused = self.focused
        if isinstance(focused, ListView):
            focused.action_cursor_up()

    def _clear_host_highlights(self) -> None:
        """Clear highlights from both host columns."""
        for list_id in ("#host-list-left", "#host-list-right"):
            host_list = self.query_one(list_id, ListView)
            host_list.index = None
            for item in host_list.children:
                if isinstance(item, HostListItem):
                    try:
                        label = item.query_one(".item-label")
                        label.update(f"  {item.display_name}")
                    except Exception:
                        pass

    def _focus_host_list(self, row: int = 0) -> None:
        """Focus host list (left column) and highlight specified row."""
        self._clear_host_highlights()
        left_list = self.query_one("#host-list-left", ListView)
        left_list.focus()
        if self.selected_env == "__favorites__":
            # Skip section header at index 0
            if left_list.children:
                self.call_later(lambda: setattr(left_list, "index", 1))
        else:
            mid = (len(self.filtered_hosts) + 1) // 2
            if mid > 0:
                target_row = min(row, mid - 1)
                self.call_later(lambda: setattr(left_list, "index", target_row))

    def _focus_right_list(self, row: int = 0) -> None:
        """Focus right host column and highlight specified row."""
        mid = (len(self.filtered_hosts) + 1) // 2
        right_hosts = self.filtered_hosts[mid:]
        if not right_hosts:
            return

        self._clear_host_highlights()
        right_list = self.query_one("#host-list-right", ListView)
        right_list.focus()
        target_row = min(row, len(right_hosts) - 1)
        self.call_later(lambda: setattr(right_list, "index", target_row))

    def action_go_right(self) -> None:
        """Right arrow - enter environment submenu or move to right column."""
        env_list = self.query_one("#env-list", ListView)
        left_list = self.query_one("#host-list-left", ListView)

        if env_list.has_focus:
            self._select_current_env()
        elif left_list.has_focus:
            current_row = left_list.index if left_list.index is not None else 0
            self._focus_right_list(current_row)

    def _get_selected_host(self, list_view: ListView) -> Optional[str]:
        """Get the target of the selected item in a list view."""
        if list_view.index is not None and list_view.index < len(list_view.children):
            item = list_view.children[list_view.index]
            if isinstance(item, HostListItem):
                return item.target
        return None

    def _get_selected_item(self, list_view: ListView) -> Optional[HostListItem]:
        """Get the selected HostListItem (or FavHostListItem) in a list view."""
        if list_view.index is not None and list_view.index < len(list_view.children):
            item = list_view.children[list_view.index]
            if isinstance(item, HostListItem):
                return item
        return None

    def _get_current_env(self) -> Optional[str]:
        """Get the current environment - either selected or highlighted."""
        if self.selected_env:
            return self.selected_env
        # Fallback to highlighted environment
        env_list = self.query_one("#env-list", ListView)
        if env_list.index is not None and env_list.index < len(env_list.children):
            item = env_list.children[env_list.index]
            if isinstance(item, EnvListItem):
                return item.env_name
        return None

    def action_confirm(self) -> None:
        """Enter key - select environment or connect to host."""
        search_box = self.query_one("#search-box", Input)
        if search_box.has_focus:
            if self.filtered_hosts:
                self._show_host_nav_status()
                self._focus_host_list()
            return

        env_list = self.query_one("#env-list", ListView)
        left_list = self.query_one("#host-list-left", ListView)
        right_list = self.query_one("#host-list-right", ListView)

        if env_list.has_focus:
            self._select_current_env()
        elif left_list.has_focus or right_list.has_focus:
            focused_list = left_list if left_list.has_focus else right_list
            self._connect_to_selected_host(focused_list)

    def _select_current_env(self) -> None:
        """Select the currently highlighted environment and move to hosts."""
        env_list = self.query_one("#env-list", ListView)
        if env_list.index is None or env_list.index >= len(env_list.children):
            return
        item = env_list.children[env_list.index]
        if isinstance(item, EnvListItem):
            self._populate_hosts(item.env_name)
            self._show_host_nav_status()
            self._focus_host_list()

    def _connect_to_selected_host(self, list_view: ListView) -> None:
        """Connect to the selected host in the given list view."""
        item = self._get_selected_item(list_view)
        if isinstance(item, FavHostListItem):
            target = self.config.build_target(item.env_name, item.target, item.is_alias)
            self._connect(target, env_name_override=item.env_name)
        elif isinstance(item, HostListItem):
            env = self._get_current_env()
            if env:
                target = self.config.build_target(env, item.target, item.is_alias)
                self._connect(target)

    def _connect(self, target: str, proto: str = "ssh", env_name_override: Optional[str] = None) -> None:
        """Connect to the specified target via SSH or SFTP."""
        env_name = env_name_override or self._get_current_env()
        History().add(target, proto=proto, env_name=env_name or "")
        self.exit(result=ConnectionRequest(target=target, proto=proto, env_name=env_name))


def _handle_post_connection(vault: Vault, env_name: Optional[str], returned_pw: str) -> None:
    """Save vault password if expect.sh sent one back via pipe."""
    if not vault.is_enabled() or not vault.is_unlocked() or not env_name:
        return
    if returned_pw:
        vault.set_password(env_name, returned_pw)


def _unlock_vault(vault: Vault) -> None:
    """Unlock or create vault, prompting for master password as needed."""
    master = vault.get_master_from_file()

    if vault.vault_exists():
        if master and vault.unlock(master):
            return
        # Prompt for master password
        for _ in range(3):
            master = getpass.getpass("\033[1;35m[VAULT]\033[0m Master password: ")
            if vault.unlock(master):
                return
            print("\033[1;31m[VAULT]\033[0m Wrong master password.")
        print("\033[1;31m[VAULT]\033[0m Vault locked — continuing without vault.")
    else:
        # Create new vault
        print("\033[1;35m[VAULT]\033[0m Creating new vault.")
        if not master:
            master = getpass.getpass("Set master password: ")
            confirm = getpass.getpass("Confirm master password: ")
            if master != confirm:
                print("\033[1;31m[VAULT]\033[0m Passwords don't match — vault not created.")
                return
        vault.create(master)
        print("\033[1;32m[VAULT]\033[0m Vault created.")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="ViperSSH - TUI SSH Connection Manager")
    parser.add_argument(
        "-c", "--config",
        type=Path,
        help="Path to config directory (default: ./etc)",
    )
    parser.add_argument(
        "--last",
        action="store_true",
        help="Reconnect to the most recent connection",
    )
    parser.add_argument(
        "--show-last",
        action="store_true",
        help="Show the most recent connection and exit",
    )
    args = parser.parse_args()

    # --show-last: just print and exit
    if args.show_last:
        history = History().load()
        if not history:
            print("No connection history.")
        else:
            entry = history[0]
            proto = entry.get("proto", "ssh")
            print(f"{entry['target']} ({proto})")
        return

    # --last: reconnect to most recent without launching TUI
    if args.last:
        history = History().load()
        if not history:
            print("No connection history.")
            return
        entry = history[0]
        result = ConnectionRequest(
            target=entry["target"],
            proto=entry.get("proto", "ssh"),
            env_name=entry.get("env"),
        )
    else:
        result = None

    vault = Vault()
    if vault.is_enabled():
        _unlock_vault(vault)

    if result is None:
        app = ViperApp(config_dir=args.config, vault=vault)
        result = app.run()

    if not result:
        return

    # If vault was enabled during the TUI session, unlock/create it now
    if vault.is_enabled() and not vault.is_unlocked():
        _unlock_vault(vault)

    target = result.target
    proto = result.proto
    env_name = result.env_name

    script_dir = Path(__file__).resolve().parent
    expect_script = script_dir / "expect.sh"
    use_expect = expect_script.exists()

    mode_label = " via \033[1;33mSFTP\033[0m" if proto == "sftp" else ""
    print(f"\n\033[1;32m[VIPERSSH]\033[0m Connecting to \033[1;36m{target}\033[0m{mode_label}\n")

    run_env = os.environ.copy()
    returned_pw = ""
    pw_read_fd = pw_write_fd = -1

    if use_expect:
        # Set vault password in environment if available
        if vault.is_enabled() and vault.is_unlocked() and env_name:
            pw = vault.get_password(env_name)
            if pw:
                run_env["VIPER_PASSWORD"] = pw

        # Create pipe for expect.sh to send back the working password
        pw_read_fd, pw_write_fd = os.pipe()
        run_env["VIPER_PW_FD"] = str(pw_write_fd)

    prev_sigint = signal.signal(signal.SIGINT, signal.SIG_IGN)

    if use_expect:
        ret = subprocess.call(
            [str(expect_script), target, proto],
            env=run_env, pass_fds=(pw_write_fd,),
        )
        # Close write end and read the password back from the pipe
        os.close(pw_write_fd)
        with os.fdopen(pw_read_fd, "r") as f:
            returned_pw = f.read()
    elif proto == "sftp":
        ret = subprocess.call(["sftp", target])
    else:
        ret = subprocess.call(["ssh", target])

    signal.signal(signal.SIGINT, prev_sigint)

    if use_expect:
        subprocess.call(["stty", "sane"], stderr=subprocess.DEVNULL)

    _handle_post_connection(vault, env_name, returned_pw)


if __name__ == "__main__":
    main()
