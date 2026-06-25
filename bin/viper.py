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
from textual.color import Color
from textual.containers import Center, Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Label, ListItem, ListView, Static

# Ensure lib/ is importable whether launched via the wrapper or directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import paths
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
    "cyberpunk": {
        "name": "Cyberpunk",
        "bg": "#0a0a12",
        "panel_bg": "#12121f",
        "env_color": "#0ff0fc",
        "host_color": "#ff2a6d",
        "accent": "#d1f700",
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
    "blaze": {
        "name": "Blaze",
        "bg": "#120c08",
        "panel_bg": "#1e1410",
        "env_color": "#ff6b6b",
        "host_color": "#bf5af2",
        "accent": "#fbbf24",
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
    "ember": {
        "name": "Ember",
        "bg": "#1a0e0a",
        "panel_bg": "#261612",
        "env_color": "#ff9f43",
        "host_color": "#ee5a24",
        "accent": "#ffd32a",
    },
    "gruvbox": {
        "name": "Gruvbox",
        "bg": "#282828",
        "panel_bg": "#3c3836",
        "env_color": "#b8bb26",
        "host_color": "#fb4934",
        "accent": "#fabd2f",
    },
    "aurora": {
        "name": "Aurora",
        "bg": "#070e1a",
        "panel_bg": "#0e1a2b",
        "env_color": "#45ffbc",
        "host_color": "#c850c0",
        "accent": "#4facfe",
    },
    "midnight": {
        "name": "Midnight",
        "bg": "#0d0f18",
        "panel_bg": "#151929",
        "env_color": "#82aaff",
        "host_color": "#c792ea",
        "accent": "#89ddff",
    },
    "jade": {
        "name": "Jade",
        "bg": "#0a120e",
        "panel_bg": "#12201a",
        "env_color": "#36d399",
        "host_color": "#fbbd23",
        "accent": "#66cc8a",
    },
}

THEME_CONFIG_FILE = paths.THEME_FILE


def _get_theme(app=None) -> dict:
    """Get the active theme dict. Falls back to viper if no app context."""
    theme_id = getattr(app, "_active_theme", "viper") if app else "viper"
    return THEMES.get(theme_id, THEMES["viper"])


# Raw banner art split into (VIPER half, SSH half) per row — used both for the
# static banner and the animated launch sequence (recolored column-by-column).
_BANNER_ROWS = [
    ("██╗   ██╗██╗██████╗ ███████╗██████╗ ", "███████╗███████╗██╗  ██╗"),
    ("██║   ██║██║██╔══██╗██╔════╝██╔══██╗", "██╔════╝██╔════╝██║  ██║"),
    ("██║   ██║██║██████╔╝█████╗  ██████╔╝", "███████╗███████╗███████║"),
    ("╚██╗ ██╔╝██║██╔═══╝ ██╔══╝  ██╔══██╗", "╚════██║╚════██║██╔══██║"),
    (" ╚████╔╝ ██║██║     ███████╗██║  ██║", "███████║███████║██║  ██║"),
    ("  ╚═══╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝", "╚══════╝╚══════╝╚═╝  ╚═╝"),
]
_BANNER_WIDTH = max(len(env) + len(host) for env, host in _BANNER_ROWS)


def _banner_lines(env_color: str, host_color: str) -> list[str]:
    """The VIPERSSH wordmark as a list of themed markup lines (each _BANNER_WIDTH wide)."""
    lines = []
    for env_part, host_part in _BANNER_ROWS:
        pad = " " * (_BANNER_WIDTH - len(env_part) - len(host_part))
        lines.append(f"[bold {env_color}]{env_part}[/][bold {host_color}]{host_part}{pad}[/]")
    return lines


def _make_banner(env_color: str, host_color: str) -> str:
    return "\n" + "\n".join(_banner_lines(env_color, host_color))


def _make_banner_frame(env_color: str, host_color: str, hi_color: str,
                       pos: int, hi_width: int = 9) -> str:
    """Render the banner with a bright highlight band centered at column ``pos``.

    Sweeping ``pos`` left→right makes a "strike" of light run across the
    wordmark. Glyphs outside the band keep their base VIPER/SSH colors.
    """
    out_lines = []
    for env_part, host_part in _BANNER_ROWS:
        full = env_part + host_part
        split = len(env_part)
        chars = []
        for i, ch in enumerate(full):
            if ch == " ":
                chars.append(" ")
                continue
            if pos - hi_width <= i <= pos:
                color = hi_color
            else:
                color = env_color if i < split else host_color
            chars.append(f"[bold {color}]{ch}[/]")
        out_lines.append("".join(chars))
    sep = "═" * _BANNER_WIDTH
    return "\n" + "\n".join(out_lines) + f"\n[dim {env_color}]{sep}[/]"


# 8-bit retro snake gliding along the rule (head first, glides leftward).
# A bright head, solid body with alternating "scale" shades, and a dithered
# tail that melts into the theme background — all derived from the theme.
_SNAKE_SEGMENTS = [
    ("█", "head"),
    ("█", "body"),
    ("█", "scale"),
    ("█", "body"),
    ("█", "scale"),
    ("█", "body"),
    ("█", "scale"),
    ("▓", "tail1"),
    ("▒", "tail2"),
    ("░", "tail3"),
]


def _rule_color(env_color: str, bg: str) -> Color:
    """Dim base color of the separator rule (snake tail melts into this)."""
    return Color.parse(env_color).blend(Color.parse(bg), 0.80)


def _snake_colors(env_color: str, bg: str) -> dict[str, Color]:
    """Map snake segment roles to colors derived from the active theme."""
    env = Color.parse(env_color)
    bgc = Color.parse(bg)
    return {
        "head": env.blend(Color.parse("#ffffff"), 0.55),  # bright highlighted head
        "body": env,
        "scale": env.blend(bgc, 0.34),                    # darker scale segments
        "tail1": env.blend(bgc, 0.52),
        "tail2": env.blend(bgc, 0.70),
        "tail3": env.blend(bgc, 0.85),
    }


def _snake_lane_markup(env_color: str, bg: str, head: int, width: int) -> str:
    """One animation frame: the rule with the 8-bit snake at ``head``."""
    rule = _rule_color(env_color, bg)
    colors = _snake_colors(env_color, bg)
    cells: list[tuple[str, Color]] = [("═", rule)] * width
    for i, (ch, role) in enumerate(_SNAKE_SEGMENTS):
        pos = (head + i) % width
        cells[pos] = (ch, colors[role])
    return "".join(f"[{c.hex}]{ch}[/]" for ch, c in cells)


def _rule_markup(env_color: str, bg: str, width: int) -> str:
    """The plain (snake-off) separator rule."""
    return f"[{_rule_color(env_color, bg).hex}]{'═' * width}[/]"


class SnakeLane(Static):
    """A 'living rule' under the banner: a gradient snake glides along it.

    Reads colors from the active theme each frame, glides leftward and loops,
    and pauses itself while a modal screen covers the main view. When disabled
    it simply shows the plain separator rule.
    """

    FRAME_INTERVAL = 0.07   # ~14 fps

    def __init__(self, *args, **kwargs) -> None:
        super().__init__("", *args, **kwargs)
        self._timer = None
        self._head = 0

    def _width(self) -> int:
        return _BANNER_WIDTH

    def on_mount(self) -> None:
        self._render_plain()
        self._timer = self.set_interval(self.FRAME_INTERVAL, self._tick, pause=True)
        if getattr(self.app, "_snake_on", True):
            self.set_running(True)

    def set_running(self, running: bool) -> None:
        if self._timer is None:
            return
        if running:
            self._timer.resume()
        else:
            self._timer.pause()
            self._render_plain()

    def _render_plain(self) -> None:
        theme = _get_theme(self.app)
        self.update(_rule_markup(theme["env_color"], theme["bg"], self._width()))

    def _tick(self) -> None:
        # Don't burn cycles while a modal (vault/theme/help) covers the screen.
        if self.app.screen is not self.screen:
            return
        theme = _get_theme(self.app)
        self._head = (self._head - 1) % self._width()
        self.update(
            _snake_lane_markup(theme["env_color"], theme["bg"], self._head, self._width())
        )


# ── SnakeBox: a thick block snake crawling an invisible path around the banner ──

# Blank padding between the wordmark and the snake's path (kept small).
_BOX_PAD_X = 3
_BOX_PAD_Y = 1


def _box_dims() -> tuple[int, int, int]:
    """Interior width, box width, box height for the snake's path around the banner."""
    iw = _BANNER_WIDTH
    return iw, iw + 2 * _BOX_PAD_X + 2, len(_BANNER_ROWS) + 2 * _BOX_PAD_Y + 2


def _box_path() -> list[tuple[int, int]]:
    """Clockwise (row, col) cells around the box perimeter, starting top-left."""
    _iw, bw, bh = _box_dims()
    path = [(0, c) for c in range(bw)]                       # top  L→R
    path += [(r, bw - 1) for r in range(1, bh)]              # right T→B
    path += [(bh - 1, c) for c in range(bw - 2, -1, -1)]     # bottom R→L
    path += [(r, 0) for r in range(bh - 2, 0, -1)]           # left  B→T
    return path


_BOX_PATH = _box_path()


def _snake_box_markup(env_color: str, host_color: str, bg: str,
                      head: int, tongue_on: bool, running: bool) -> str:
    """Render the banner with the snake crawling an invisible perimeter path.

    Non-snake perimeter cells are blank (transparent) — only the snake shows.
    """
    iw, bw, bh = _box_dims()
    blines = _banner_lines(env_color, host_color)
    colors = _snake_colors(env_color, bg)
    tongue_color = Color.parse(host_color)

    snake: dict[tuple[int, int], tuple[str, Color]] = {}
    if running:
        p = len(_BOX_PATH)
        for i, (ch, role) in enumerate(_SNAKE_SEGMENTS):
            snake[_BOX_PATH[(head - i) % p]] = (ch, colors[role])
        if tongue_on:
            snake.setdefault(_BOX_PATH[(head + 1) % p], ("▪", tongue_color))

    def cell(r: int, c: int) -> str:
        if (r, c) in snake:
            ch, col = snake[(r, c)]
            return f"[{col.hex}]{ch}[/]"
        return " "

    banner_top = 1 + _BOX_PAD_Y
    pad = " " * _BOX_PAD_X
    rows = []
    for r in range(bh):
        if r == 0 or r == bh - 1:
            rows.append("".join(cell(r, c) for c in range(bw)))
        else:
            bi = r - banner_top
            if 0 <= bi < len(blines):
                mid = pad + blines[bi] + pad
            else:
                mid = " " * (bw - 2)
            rows.append(cell(r, 0) + mid + cell(r, bw - 1))
    return "\n".join(rows)


class SnakeBox(Static):
    """The VIPERSSH banner framed by a border the 8-bit snake crawls around.

    Renders the whole framed region itself (no transparency tricks), so the
    snake can round the corners over a self-owned rectangle. Theme-colored,
    pauses under modals, and shows just the plain frame when disabled.
    """

    FRAME_INTERVAL = 0.07

    def __init__(self, *args, **kwargs) -> None:
        # Start with real content (default theme) so `width: auto` can measure
        # the frame before on_mount swaps in the active theme.
        t = THEMES["viper"]
        initial = _snake_box_markup(t["env_color"], t["host_color"], t["bg"], 0, False, False)
        super().__init__(initial, *args, **kwargs)
        # Fixed size so Textual never has to measure an auto width (which fails
        # before the visual exists).
        _iw, bw, bh = _box_dims()
        self.styles.width = bw
        self.styles.height = bh
        self._timer = None
        self._head = 0
        self._frame = 0
        self._running = False

    def on_mount(self) -> None:
        self._redraw()
        self._timer = self.set_interval(self.FRAME_INTERVAL, self._tick, pause=True)
        self.set_running(getattr(self.app, "_snake_on", True))

    def set_running(self, running: bool) -> None:
        self._running = running
        if self._timer is not None:
            self._timer.resume() if running else self._timer.pause()
        self._redraw()

    def refresh_box(self) -> None:
        self._redraw()

    def _redraw(self) -> None:
        theme = _get_theme(self.app)
        tongue_on = (self._frame // 5) % 4 == 0
        self.update(_snake_box_markup(
            theme["env_color"], theme["host_color"], theme["bg"],
            self._head, tongue_on, self._running,
        ))

    def _tick(self) -> None:
        if self.app.screen is not self.screen:
            return
        self._head = (self._head + 1) % len(_BOX_PATH)
        self._frame += 1
        self._redraw()


def _make_help_text(host_color: str, env_color: str, accent: str) -> str:
    return f"""[bold {host_color}]  NAVIGATION[/]
[dim]  ──────────────────────────────[/]
  [bold {host_color}]↑ ↓[/]  [dim]or[/]  [bold {host_color}]j k[/]   Move up/down
  [bold {host_color}]→[/]  [dim]or[/]  [bold {host_color}]Enter[/]  Select / Enter
  [bold {host_color}]←[/]  [dim]or[/]  [bold {host_color}]Esc[/]    Go back
  [bold {host_color}]Tab[/]           Switch panels

[bold {env_color}]  SEARCH[/]
[dim]  ──────────────────────────────[/]
  [bold {host_color}]/[/]             Focus search box
  [bold {host_color}]Esc[/]           Exit search
  [bold {host_color}]Enter[/]         Jump to results

[bold {accent}]  ACTIONS[/]
[dim]  ──────────────────────────────[/]
  [bold {host_color}]?[/]  [dim]or[/]  [bold {host_color}]h[/]      Toggle this menu
  [bold {host_color}]t[/]             Theme selector
  [bold {host_color}]r[/]             Recent connections
  [bold {host_color}]v[/]             Password vault
  [bold {host_color}]f[/]             Toggle favorite
  [bold {host_color}]s[/]             SFTP connect
  [bold {host_color}]a[/]             Connect animation on/off
  [bold {host_color}]A[/]             Snake animation on/off
  [bold {host_color}]q[/]             Quit
[dim]──────────────────────────────────[/]
[dim]       Press any key to close[/]"""


class LaunchScreen(ModalScreen):
    """Brief animated 'launch sequence' shown after a host is selected.

    Sweeps a highlight across the VIPERSSH banner, shows the target, then
    exits the app with the pending ConnectionRequest so the SSH session
    starts. Any key skips straight to the connection.
    """

    CSS = """
    LaunchScreen {
        align: center middle;
        background: $background;
    }

    #launch-box {
        width: auto;
        height: auto;
    }

    #launch-banner {
        text-align: center;
        width: auto;
        height: auto;
    }

    #launch-target {
        text-align: center;
        width: auto;
        padding-top: 1;
    }
    """

    FRAME_INTERVAL = 0.04   # ~25 fps
    STEP = 4                # columns advanced per frame

    def __init__(self, request: ConnectionRequest, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._request = request
        self._pos = -9
        self._done = False
        self._timer = None

    def compose(self) -> ComposeResult:
        with Vertical(id="launch-box"):
            yield Static(id="launch-banner")
            yield Static(id="launch-target")

    def on_mount(self) -> None:
        theme = _get_theme(self.app)
        proto = self._request.proto.upper()
        verb = "OPENING SFTP" if self._request.proto == "sftp" else "CONNECTING"
        self.query_one("#launch-target", Static).update(
            f"[bold {theme['accent']}]{verb} TO[/] "
            f"[bold {theme['host_color']}]{self._request.target}[/]"
        )
        self._render_frame()
        self._timer = self.set_interval(self.FRAME_INTERVAL, self._tick)

    def _render_frame(self) -> None:
        theme = _get_theme(self.app)
        self.query_one("#launch-banner", Static).update(
            _make_banner_frame(
                theme["env_color"], theme["host_color"], theme["accent"], self._pos
            )
        )

    def _tick(self) -> None:
        self._pos += self.STEP
        if self._pos > _BANNER_WIDTH + 9:
            self._finish()
            return
        self._render_frame()

    def on_key(self, event) -> None:
        # Any key skips the animation and connects immediately.
        event.stop()
        self._finish()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        if self._timer is not None:
            self._timer.stop()
        self.app.exit(result=self._request)


class HelpScreen(ModalScreen):
    """Modal help screen - closes on any key or click."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("?", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        theme = _get_theme(self.app)
        with Vertical(id="help-container"):
            yield Static(f"[bold {theme['host_color']}]QUICK MENU[/]", id="help-title")
            yield Static(_make_help_text(theme["host_color"], theme["env_color"], theme["accent"]), id="help-body")

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
        theme = _get_theme(self.app)
        marker = f"[bold {theme['env_color']}]●[/]" if self.is_active else "[dim]○[/]"
        yield Label(f"  {marker} {self.theme_name}", classes="theme-label")

    def watch_highlighted(self, highlighted: bool) -> None:
        try:
            label = self.query_one(".theme-label")
        except Exception:
            return
        theme = _get_theme(self.app)
        marker = f"[bold {theme['env_color']}]●[/]" if self.is_active else "[dim]○[/]"
        if highlighted:
            label.update(f"[bold {theme['host_color']}]>[/] {marker} [bold]{self.theme_name}[/]")
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
        background: $surface;
        border: heavy $error;
        padding: 1 2;
    }

    #theme-title {
        text-align: center;
        text-style: bold;
        color: $error;
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
        background: $error-darken-3;
    }

    #theme-hint {
        text-align: center;
        color: #666666;
        padding-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        theme = _get_theme(self.app)
        with Vertical(id="theme-container"):
            yield Static(f"[bold {theme['host_color']}]SELECT THEME[/]", id="theme-title")
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

    def __init__(self, target: str, ts: float, proto: str = "ssh", env_name: str = "", *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.target = target
        self.ts = ts
        self.proto = proto
        self.env_name = env_name

    def _label_text(self, highlighted: bool = False) -> str:
        theme = _get_theme(self.app)
        rel = _relative_time(self.ts)
        proto_tag = f" [dim {theme['accent']}][{self.proto}][/]" if self.proto != "ssh" else ""
        if highlighted:
            return f"[bold {theme['host_color']}]>[/] {self.target}{proto_tag}  [dim {theme['accent']}]{rel}[/]"
        return f"  {self.target}{proto_tag}  [dim {theme['accent']}]{rel}[/]"

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
        background: $surface;
        border: heavy $accent;
        padding: 1 2;
    }

    #history-title {
        text-align: center;
        text-style: bold;
        color: $accent;
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
        background: $accent-darken-3;
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
        theme = _get_theme(self.app)
        with Vertical(id="history-container"):
            yield Static(f"[bold {theme['accent']}]RECENT CONNECTIONS[/]", id="history-title")
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

        theme = _get_theme(self.app)
        if ssh_entries:
            history_list.append(HistorySectionItem("SSH", theme["env_color"]))
            for entry in ssh_entries:
                history_list.append(HistoryListItem(entry["target"], entry["ts"], "ssh", entry.get("env", "")))

        if sftp_entries:
            history_list.append(HistorySectionItem("SFTP", theme["accent"]))
            for entry in sftp_entries:
                history_list.append(HistoryListItem(entry["target"], entry["ts"], "sftp", entry.get("env", "")))

        history_list.focus()
        # Skip the section header at index 0 to focus the first selectable item
        self.call_later(lambda: setattr(history_list, "index", 1))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, HistoryListItem):
            self.dismiss(ConnectionRequest(event.item.target, event.item.proto, event.item.env_name or None))

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
        theme = _get_theme(self.app)
        if self.has_password:
            marker = f"[bold {theme['env_color']}]●[/]"
            tag = f" [dim {theme['env_color']}]saved[/]"
        else:
            marker = f"[dim {theme['host_color']}]○[/]"
            tag = f" [dim {theme['host_color']}]no pw[/]"
        name = self.env_name.replace("_", " ")
        if highlighted:
            return f"[bold {theme['host_color']}]>[/] {marker} [bold]{name}[/]{tag}"
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
        Binding("escape", "cancel_or_close", "Close"),
        Binding("v", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("e", "toggle_vault", "Toggle"),
        Binding("m", "set_master", "Master"),
        Binding("p", "toggle_remember", "Remember"),
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
        background: $surface;
        border: heavy $accent;
        padding: 1 2;
    }

    #vault-title {
        text-align: center;
        text-style: bold;
        color: $accent;
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
        background: $accent-darken-3;
    }

    #vault-hint {
        text-align: center;
        color: #666666;
        padding-top: 1;
    }

    #vault-password-input {
        margin: 1 0;
        border: solid $accent 50%;
        background: $background;
        padding: 0 1;
    }

    #vault-input-label {
        text-align: center;
        color: $accent;
        padding-top: 1;
    }
    """

    def __init__(self, vault: Vault, config_envs: list[str], *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.vault = vault
        self.config_envs = config_envs
        self._editing_env: Optional[str] = None
        # Input-mode state machine: None | env | unlock | create |
        # create_confirm | change | change_confirm
        self._input_mode: Optional[str] = None
        self._pending_master: Optional[str] = None
        self._confirm_remember: bool = False

    def compose(self) -> ComposeResult:
        theme = _get_theme(self.app)
        with Vertical(id="vault-container"):
            yield Static(f"[bold {theme['accent']}]PASSWORD VAULT[/]", id="vault-title")
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
        self._maybe_prompt_unlock_or_create()

    def _maybe_prompt_unlock_or_create(self) -> None:
        """If the vault is enabled but locked, prompt to unlock or create it."""
        if not (self.vault.is_enabled() and not self.vault.is_unlocked()):
            return
        accent = _get_theme(self.app)["accent"]
        if self.vault.vault_exists():
            self._prompt_input("unlock", f"[bold {accent}]Master password to unlock[/]")
        else:
            self._prompt_input("create", f"[bold {accent}]Set master password[/]")

    def _prompt_input(self, mode: str, label_markup: str) -> None:
        """Show the password input in the given mode with the given label."""
        self._input_mode = mode
        input_label = self.query_one("#vault-input-label", Static)
        input_label.display = True
        input_label.update(label_markup)
        pw_input = self.query_one("#vault-password-input", Input)
        pw_input.display = True
        pw_input.value = ""
        pw_input.focus()
        self._update_status()

    def _hide_input(self) -> None:
        """Hide the password input and return focus to the environment list."""
        self._input_mode = None
        self._editing_env = None
        self._pending_master = None
        pw_input = self.query_one("#vault-password-input", Input)
        pw_input.display = False
        pw_input.value = ""
        input_label = self.query_one("#vault-input-label", Static)
        input_label.display = False
        vault_list = self.query_one("#vault-env-list", ListView)
        vault_list.focus()
        if vault_list.children:
            self.call_later(lambda: setattr(vault_list, "index", 0))
        self._update_status()

    def _update_status(self) -> None:
        theme = _get_theme(self.app)
        status = self.query_one("#vault-status", Static)
        enabled = self.vault.is_enabled()
        unlocked = self.vault.is_unlocked()
        if enabled:
            state = f"[bold {theme['env_color']}]ENABLED[/]"
            lock = f" [dim]|[/] [{theme['env_color']}]unlocked[/]" if unlocked else f" [dim]|[/] [{theme['host_color']}]locked[/]"
            if unlocked:
                remember = self.vault.has_master_file()
                rem_color = theme["env_color"] if remember else theme["host_color"]
                lock += f" [dim]|[/] [{rem_color}]remember {'on' if remember else 'off'}[/]"
        else:
            state = f"[bold {theme['host_color']}]DISABLED[/]"
            lock = ""
        status.update(f"  Status: {state}{lock}")

        hint = self.query_one("#vault-hint", Static)
        if self._confirm_remember:
            hint.update(
                f"[{theme['host_color']}]Store master password in PLAINTEXT?[/] "
                "[dim]p[/] confirm  [dim]Esc[/] cancel"
            )
        elif self._input_mode == "env":
            hint.update("[dim]Enter[/] save  [dim]Esc[/] cancel")
        elif self._input_mode is not None:
            hint.update("[dim]Enter[/] submit  [dim]Esc[/] cancel")
        elif not enabled:
            hint.update("[dim]e[/] enable  [dim]Esc[/] close")
        elif not unlocked:
            hint.update("[dim]Enter[/] unlock  [dim]e[/] disable  [dim]Esc[/] close")
        else:
            hint.update(
                "[dim]m[/] master  [dim]p[/] remember  [dim]e[/] disable  "
                "[dim]d[/] delete  [dim]Esc[/] close"
            )

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
        if not enabled:
            # Just enabled — guide the user straight into unlock/create.
            self._maybe_prompt_unlock_or_create()

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
            accent = _get_theme(self.app)["accent"]
            name = event.item.env_name.replace("_", " ")
            self._prompt_input("env", f"[bold {accent}]Password for[/] [bold]{name}[/]")

    def action_set_master(self) -> None:
        """'m' — set/change the master password (or unlock if locked)."""
        if not self.vault.is_enabled():
            return
        if not self.vault.is_unlocked():
            self._maybe_prompt_unlock_or_create()
            return
        accent = _get_theme(self.app)["accent"]
        self._prompt_input("change", f"[bold {accent}]New master password[/]")

    def action_toggle_remember(self) -> None:
        """'p' — create/remove var/vault/master (auto-unlock at startup)."""
        if not self.vault.is_unlocked():
            return
        if self.vault.has_master_file():
            self.vault.clear_master_file()
            self._confirm_remember = False
            self.app.notify("Remember password: off", timeout=2)
            self._update_status()
            return
        if not self._confirm_remember:
            # First press: show the plaintext warning, require a second press.
            self._confirm_remember = True
            self._update_status()
            return
        self._confirm_remember = False
        if self.vault.write_master_file():
            self.app.notify("Remember password: on", timeout=2)
        self._update_status()

    def action_cancel_or_close(self) -> None:
        """Esc — back out of an active input or pending confirm, else close."""
        pw_input = self.query_one("#vault-password-input", Input)
        if pw_input.display:
            self._hide_input()
        elif self._confirm_remember:
            self._confirm_remember = False
            self._update_status()
        else:
            self.dismiss()

    @on(Input.Submitted, "#vault-password-input")
    def on_password_submitted(self, event: Input.Submitted) -> None:
        mode = self._input_mode
        value = event.value
        accent = _get_theme(self.app)["accent"]

        if mode == "env":
            if self._editing_env and value:
                self.vault.set_password(self._editing_env, value)
            self._populate_list()
            self._hide_input()

        elif mode == "unlock":
            if self.vault.unlock(value):
                self._populate_list()
                self.app.notify("Vault unlocked", timeout=2)
                self._hide_input()
            else:
                self.app.notify("Wrong master password", severity="error", timeout=3)
                pw_input = self.query_one("#vault-password-input", Input)
                pw_input.value = ""
                pw_input.focus()

        elif mode == "create":
            if not value:
                self._hide_input()
                return
            self._pending_master = value
            self._prompt_input("create_confirm", f"[bold {accent}]Confirm master password[/]")

        elif mode == "create_confirm":
            if value == self._pending_master:
                self.vault.create(value)
                self._populate_list()
                self.app.notify("Vault created", timeout=2)
                self._hide_input()
            else:
                self.app.notify("Passwords don't match", severity="error", timeout=3)
                self._pending_master = None
                self._prompt_input("create", f"[bold {accent}]Set master password[/]")

        elif mode == "change":
            if not value:
                self._hide_input()
                return
            self._pending_master = value
            self._prompt_input("change_confirm", f"[bold {accent}]Confirm new master password[/]")

        elif mode == "change_confirm":
            if value == self._pending_master:
                self.vault.change_master_password(value)
                if self.vault.has_master_file():
                    self.vault.write_master_file()
                self.app.notify("Master password changed", timeout=2)
                self._hide_input()
            else:
                self.app.notify("Passwords don't match", severity="error", timeout=3)
                self._pending_master = None
                self._prompt_input("change", f"[bold {accent}]New master password[/]")

        else:
            self._hide_input()

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
        theme = _get_theme(self.app)
        if highlighted:
            label.update(f"[bold {theme['host_color']}]> {self.display_name}[/]")
        else:
            label.update(f"  {self.display_name}")


class FavSectionItem(ListItem):
    """A non-interactive section header in the favorites list."""

    def __init__(self, env_display: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.env_display = env_display
        self.disabled = True

    def compose(self) -> ComposeResult:
        theme = _get_theme(self.app)
        yield Label(
            f"[dim]──[/] [bold {theme['env_color']}]{self.env_display}[/] [dim]{'─' * max(1, 32 - len(self.env_display))}[/]",
            classes="section-label",
        )

    def watch_highlighted(self, highlighted: bool) -> None:
        pass


class FavHostListItem(HostListItem):
    """A host list item from the favorites pseudo-environment."""

    def __init__(self, host_info: HostInfo, env_name: str, *args, **kwargs) -> None:
        super().__init__(host_info, *args, **kwargs)
        self.env_name = env_name

    def compose(self) -> ComposeResult:
        yield Label(f"    {self.display_name}", classes="item-label")

    def watch_highlighted(self, highlighted: bool) -> None:
        try:
            label = self.query_one(".item-label")
        except Exception:
            return
        theme = _get_theme(self.app)
        if highlighted:
            label.update(f"  [bold {theme['host_color']}]> {self.display_name}[/]")
        else:
            label.update(f"    {self.display_name}")


class EnvListItem(ListItem):
    """A list item representing an environment."""

    def __init__(self, env_name: str, display_name: str, host_count: int, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.env_name = env_name
        self.display_name = display_name
        self.host_count = host_count

    def compose(self) -> ComposeResult:
        theme = _get_theme(self.app)
        yield Label(f"  {self.display_name:<20} [dim {theme['host_color']}]({self.host_count})[/]", classes="item-label")

    def watch_highlighted(self, highlighted: bool) -> None:
        try:
            label = self.query_one(".item-label")
        except Exception:
            return
        theme = _get_theme(self.app)
        if highlighted:
            label.update(f"[bold {theme['env_color']}]> {self.display_name:<20}[/] [{theme['host_color']}]({self.host_count})[/]")
        else:
            label.update(f"  {self.display_name:<20} [dim {theme['host_color']}]({self.host_count})[/]")


class ViperApp(App):
    """Main Viper TUI application."""

    COMMANDS = set()

    CSS = """
    Screen {
        layout: vertical;
        background: $background;
    }

    #header {
        dock: top;
        height: auto;
        width: 100%;
        padding: 1 0;
    }

    #main-container {
        layout: horizontal;
        height: 1fr;
        margin: 0 0 0 2;
    }

    #env-panel {
        border: heavy $success;
        background: $surface;
        padding: 0 1;
        width: 1fr;
        border-title-color: $success;
        border-title-style: bold;
    }

    #host-panel {
        border: heavy $error;
        background: $surface;
        padding: 0 1;
        width: 2fr;
        border-title-color: $error;
        border-title-style: bold;
    }

    #env-list {
        height: 1fr;
        background: transparent;
        scrollbar-color: $success;
        scrollbar-color-hover: $success;
        scrollbar-color-active: $success;
    }

    #env-filter-box {
        dock: top;
        margin: 1 0;
        border: solid $success 50%;
        background: $background;
        padding: 0 1;
        height: 3;
    }

    #search-box {
        dock: top;
        margin: 1 0;
        border: solid $error 50%;
        background: $background;
        padding: 0 1;
    }

    #search-box:focus {
        border: solid $error;
    }

    #search-box > .input--placeholder {
        color: #444444;
    }

    #status-bar {
        dock: bottom;
        height: 3;
        padding: 1;
        background: $surface;
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
        background: $surface;
    }

    #env-list > ListItem.--highlight {
        background: $success-darken-3;
    }

    /* Host columns layout */
    #host-columns {
        height: 1fr;
    }

    #host-list-left, #host-list-right {
        width: 1fr;
        height: 1fr;
        background: transparent;
        scrollbar-color: $error;
    }

    #host-list-left > ListItem.--highlight,
    #host-list-right > ListItem.--highlight {
        background: $error-darken-3;
    }

    #target-display {
        text-style: bold;
        color: $accent;
    }

    Footer {
        background: $surface;
        color: $success;
    }

    Footer > .footer--key {
        background: $success-darken-3;
        color: $success;
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
        background: $surface;
        border: heavy $error;
        padding: 1 2;
    }

    #help-title {
        text-align: center;
        text-style: bold;
        color: $error;
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
        Binding("a", "toggle_animation", "Anim", show=False),
        Binding("A", "toggle_snake", "Snake", show=False),
        Binding("q", "quit", "Quit"),
        Binding("tab", "switch_panel", "Switch", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    TITLE = "VIPERSSH"

    def __init__(self, config_dir: Optional[Path] = None, vault: Optional[Vault] = None) -> None:
        self._active_theme = self._load_theme()
        super().__init__()
        self.config = Config(config_dir)
        self.vault = vault or Vault()
        self.favorites = Favorites()
        self._fav_env_map: dict[str, str] = {}  # target -> env_name for favorites
        self.selected_env: Optional[str] = None
        self.current_hosts: list[HostInfo] = []
        self.filtered_hosts: list[HostInfo] = []
        self._saved_env_index: int = 0  # Track env position for search restore
        self._launch_anim: bool = self._load_launch_anim()
        self._snake_on: bool = self._load_snake_anim()

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
            THEME_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            THEME_CONFIG_FILE.write_text(theme_id)
        except OSError:
            pass

    def _load_launch_anim(self) -> bool:
        """Whether to play the connect animation (default on)."""
        try:
            return paths.LAUNCH_ANIM_FILE.read_text().strip() != "off"
        except OSError:
            return True

    def _save_launch_anim(self, on: bool) -> None:
        try:
            paths.LAUNCH_ANIM_FILE.parent.mkdir(parents=True, exist_ok=True)
            paths.LAUNCH_ANIM_FILE.write_text("on" if on else "off")
        except OSError:
            pass

    def action_toggle_animation(self) -> None:
        """Toggle the connect launch animation on/off (persisted)."""
        self._launch_anim = not self._launch_anim
        self._save_launch_anim(self._launch_anim)
        self.notify(
            f"Connect animation: {'on' if self._launch_anim else 'off'}", timeout=2
        )

    def _load_snake_anim(self) -> bool:
        """Whether the ambient snake plays along the rule (default on)."""
        try:
            return paths.SNAKE_ANIM_FILE.read_text().strip() != "off"
        except OSError:
            return True

    def _save_snake_anim(self, on: bool) -> None:
        try:
            paths.SNAKE_ANIM_FILE.parent.mkdir(parents=True, exist_ok=True)
            paths.SNAKE_ANIM_FILE.write_text("on" if on else "off")
        except OSError:
            pass

    def action_toggle_snake(self) -> None:
        """Toggle the ambient snake on/off (persisted)."""
        self._snake_on = not self._snake_on
        self._save_snake_anim(self._snake_on)
        try:
            self.query_one("#snake-box", SnakeBox).set_running(self._snake_on)
        except Exception:
            pass
        self.notify(f"Snake: {'on' if self._snake_on else 'off'}", timeout=2)

    def get_css_variables(self) -> dict[str, str]:
        """Map theme colors to Textual CSS variables."""
        variables = super().get_css_variables()
        theme = THEMES.get(self._active_theme, THEMES["viper"])
        variables["background"] = theme["bg"]
        variables["surface"] = theme["panel_bg"]
        variables["success"] = theme["env_color"]
        variables["error"] = theme["host_color"]
        variables["accent"] = theme["accent"]
        return variables

    def action_set_theme(self, theme_id: str, notify: bool = True) -> None:
        """Switch to a different theme."""
        if theme_id not in THEMES:
            return

        theme = THEMES[theme_id]
        self._active_theme = theme_id
        self._save_theme(theme_id)

        # Re-apply CSS variables and refresh all styles
        self.call_later(self.refresh_css)

        # Re-render the banner/snake frame with the new theme colors
        try:
            self.query_one("#snake-box", SnakeBox).refresh_box()
        except Exception:
            pass

        if notify:
            self.notify(f"Theme: {theme['name']}", timeout=2)

    def compose(self) -> ComposeResult:
        theme = THEMES.get(self._active_theme, THEMES["viper"])
        with Center(id="header"):
            yield SnakeBox(id="snake-box")
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
            hc = theme["host_color"]
            yield Static(f">> Select environment  [bold {hc}]↑↓[/] [dim]navigate[/]  [bold {hc}]Enter[/] [dim]select[/]  [bold {hc}]?[/] [dim]help[/]  [bold {hc}]q[/] [dim]quit[/]", id="target-display")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the app after mounting."""
        try:
            self.config.load()
        except FileNotFoundError as e:
            self.notify(str(e), severity="error")
            return

        self.action_set_theme(self._active_theme, notify=False)

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
            env_order = {e: i for i, e in enumerate(self.config.environments)}
            fav_entries = sorted(self.favorites.load(), key=lambda e: env_order.get(e.get("env_name", ""), len(env_order)))
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

    @property
    def _hc(self) -> str:
        """Shortcut for host_color from active theme."""
        return THEMES.get(self._active_theme, THEMES["viper"])["host_color"]

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
                env_order = {e: i for i, e in enumerate(self.config.environments)}
                fav_entries = sorted(self.favorites.load(), key=lambda e: env_order.get(e.get("env_name", ""), len(env_order)))
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
            self._update_status(f"{event.item.display_name}: {len(hosts)} hosts  [bold {self._hc}]Enter[/] [dim]select[/]  [bold {self._hc}]↑↓[/] [dim]browse[/]")

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
        self._update_status(f"Filter: {len(self.filtered_hosts)} matches  [bold {self._hc}]Enter[/] [dim]jump[/]  [bold {self._hc}]Esc[/] [dim]exit search[/]")

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
        self._update_status(f"Select environment  [bold {self._hc}]↑↓[/] [dim]navigate[/]  [bold {self._hc}]Enter[/] [dim]select[/]  [bold {self._hc}]?[/] [dim]help[/]  [bold {self._hc}]q[/] [dim]quit[/]")
        self.query_one("#host-panel").border_title = "HOSTS"
        self.call_later(env_list.focus)

    def _show_host_nav_status(self) -> None:
        """Show status bar for host navigation."""
        env = self._get_current_env() or "?"
        display_env = "\u2605 Favorites" if env == "__favorites__" else env
        self._update_status(
            f"[bold]{display_env}[/]  "
            f"[bold {self._hc}]↑↓[/] [dim]navigate[/]  "
            f"[bold {self._hc}]Enter[/] [dim]ssh[/]  "
            f"[bold {self._hc}]s[/] [dim]sftp[/]  "
            f"[bold {self._hc}]f[/] [dim]fav[/]  "
            f"[bold {self._hc}]/[/] [dim]search[/]  "
            f"[bold {self._hc}]Esc[/] [dim]back[/]"
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
        self._update_status(f"Search mode  [dim]type to filter[/]  [bold {self._hc}]Enter[/] [dim]jump[/]  [bold {self._hc}]Esc[/] [dim]exit[/]")

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
                self._connect(req.target, proto=req.proto, env_name_override=req.env_name)
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
                if isinstance(item, FavHostListItem):
                    try:
                        label = item.query_one(".item-label")
                        label.update(f"    {item.display_name}")
                    except Exception:
                        pass
                elif isinstance(item, HostListItem):
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
        # Never pass the pseudo-environment to vault/history
        if env_name == "__favorites__":
            env_name = None
        History().add(target, proto=proto, env_name=env_name or "")
        request = ConnectionRequest(target=target, proto=proto, env_name=env_name)
        if self._launch_anim:
            self.push_screen(LaunchScreen(request))
        else:
            self.exit(result=request)


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
    paths.ensure_dirs()
    paths.migrate_legacy()
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

    expect_script = paths.EXPECT_SCRIPT
    use_expect = expect_script.exists()

    mode_label = " via \033[1;33mSFTP\033[0m" if proto == "sftp" else ""
    sys.stdout.write(f"\033]0;{target}\007")
    sys.stdout.flush()
    print(f"\n\033[1;32m[VIPERSSH]\033[0m Connecting to \033[1;36m{target}\033[0m{mode_label}\n")

    run_env = os.environ.copy()
    returned_pw = ""
    pw_read_fd = pw_write_fd = -1

    # The vault can only store a password back if it's enabled, unlocked, and
    # we know which environment to key it under. Only then do we wire up the
    # pipe that lets expect.sh prompt to save — otherwise expect.sh would offer
    # to "save" a password that _handle_post_connection silently discards.
    vault_active = vault.is_enabled() and vault.is_unlocked() and bool(env_name)

    if use_expect:
        # Set vault password in environment if available
        if vault_active:
            pw = vault.get_password(env_name)
            if pw:
                run_env["VIPER_PASSWORD"] = pw

        # Create pipe for expect.sh to send back the working password
        if vault_active:
            pw_read_fd, pw_write_fd = os.pipe()
            run_env["VIPER_PW_FD"] = str(pw_write_fd)

    prev_sigint = signal.signal(signal.SIGINT, signal.SIG_IGN)

    if use_expect:
        pass_fds = (pw_write_fd,) if pw_write_fd != -1 else ()
        ret = subprocess.call(
            [str(expect_script), target, proto],
            env=run_env, pass_fds=pass_fds,
        )
        # Close write end and read the password back from the pipe
        if pw_write_fd != -1:
            os.close(pw_write_fd)
            with os.fdopen(pw_read_fd, "r") as f:
                returned_pw = f.read()
    elif proto == "sftp":
        ret = subprocess.call(["sftp", target])
    else:
        ret = subprocess.call(["ssh", target])

    signal.signal(signal.SIGINT, prev_sigint)
    sys.stdout.write("\033]0;\007")
    sys.stdout.flush()

    if use_expect:
        subprocess.call(["stty", "sane"], stderr=subprocess.DEVNULL)

    _handle_post_connection(vault, env_name, returned_pw)


if __name__ == "__main__":
    main()
