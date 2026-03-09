#!/usr/bin/env python3
"""omarchy-vpn — WireGuard VPN tray icon for Omarchy"""

import json
import re
import socket
import subprocess
import threading
from pathlib import Path

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk, AppIndicator3, GLib

CONFIG_DIR = Path(__file__).parent / "configs"
PREFS_FILE = Path(__file__).parent / "prefs.json"


# ── helpers ──────────────────────────────────────────────────────────────────

def load_prefs():
    if PREFS_FILE.exists():
        try:
            return json.loads(PREFS_FILE.read_text())
        except Exception:
            pass
    return {}


def save_prefs(prefs):
    PREFS_FILE.write_text(json.dumps(prefs))


def get_configs():
    return sorted(CONFIG_DIR.glob("*.conf"))


def display_name(stem):
    """Turn a config filename stem into a readable label.
    Strips 'wg' prefix and trailing numbers, e.g. 'wg-nl-93' -> 'NL'
    """
    s = re.sub(r'^[Ww][Gg][-_]?', '', stem)
    s = re.sub(r'[-_]\d+$', '', s)
    return s.upper().replace("-", " ").replace("_", " ")


def run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout, r.stderr
    except Exception as e:
        return False, "", str(e)


def parse_handshake_age(s):
    total = 0
    for match in re.finditer(r'(\d+)\s+(second|minute|hour|day)', s):
        value, unit = int(match.group(1)), match.group(2)
        total += value * {"second": 1, "minute": 60, "hour": 3600, "day": 86400}[unit]
    return total


def can_reach_endpoint(endpoint):
    if not endpoint:
        return False
    try:
        host = endpoint[1:endpoint.rindex(']')] if endpoint.startswith('[') else endpoint.rsplit(':', 1)[0]
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1)
        sock.connect((host, 1))
        sock.close()
        return True
    except Exception:
        return False


def get_endpoint(conf):
    """Extract endpoint IP from a WireGuard config file."""
    for line in conf.read_text().splitlines():
        line = line.strip()
        if line.lower().startswith("endpoint"):
            addr = line.split("=", 1)[1].strip()
            return addr.rsplit(":", 1)[0]  # strip port
    return None


def ping_latency(host, timeout=2):
    """Return latency in ms to host, or None on failure."""
    try:
        r = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout), host],
            capture_output=True, text=True, timeout=timeout + 1
        )
        if r.returncode == 0:
            m = re.search(r'time[=<]([\d.]+)', r.stdout)
            if m:
                return float(m.group(1))
    except Exception:
        pass
    return None


def find_fastest(configs):
    """Ping all config endpoints, return the config with lowest latency."""
    results = []
    for conf in configs:
        host = get_endpoint(conf)
        if host:
            ms = ping_latency(host)
            if ms is not None:
                results.append((ms, conf))
    if results:
        results.sort(key=lambda x: x[0])
        return results[0][1]
    return None


def get_status():
    """
    Returns (status, iface):
      status: 'connected' | 'stale' | 'no-network' | 'disconnected'
      iface:  WireGuard interface name (matches config file stem), or None
    """
    ok, out, _ = run(["sudo", "wg", "show"], 5)
    if not ok or not out.strip():
        return 'disconnected', None

    iface = endpoint = None
    last_handshake_age = None

    for line in out.split("\n"):
        line = line.strip()
        if line.startswith("interface:"):
            iface = line.split(":", 1)[1].strip()
        elif line.startswith("endpoint:"):
            endpoint = line.split(":", 1)[1].strip()
        elif line.startswith("latest handshake:"):
            last_handshake_age = parse_handshake_age(line.split(":", 1)[1].strip())

    if not iface:
        return 'disconnected', None
    if not can_reach_endpoint(endpoint):
        return 'no-network', iface
    if last_handshake_age is None or last_handshake_age > 180:
        return 'stale', iface
    return 'connected', iface


# ── tray ─────────────────────────────────────────────────────────────────────

class OmarchyVPN:
    def __init__(self):
        self.indicator = AppIndicator3.Indicator.new(
            "omarchy-vpn",
            "security-low-symbolic",
            AppIndicator3.IndicatorCategory.SYSTEM_SERVICES
        )
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.last_state = None
        self.state = 'disconnected'
        self.iface = None
        self._config_stems = set()
        self._disconnect_timer = None
        self.prefs = load_prefs()

        self._update_status()
        self.build_menu()
        GLib.timeout_add_seconds(3, self.refresh)

        if self.prefs.get("auto_connect_enabled"):
            pinned = self.prefs.get("auto_connect")
            if pinned:
                conf = CONFIG_DIR / f"{pinned}.conf"
                if conf.exists():
                    threading.Thread(target=self._connect, args=(conf,), daemon=True).start()

    def notify(self, title, body):
        try:
            subprocess.Popen(
                ["notify-send", "-a", "omarchy-vpn", title, body],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception:
            pass

    def _update_status(self):
        state, iface = get_status()
        config_stems = {c.stem for c in get_configs()}
        changed = (state != self.state or iface != self.iface
                   or config_stems != self._config_stems)
        self.state = state
        self.iface = iface
        self._config_stems = config_stems

        # Notifications on state change
        if self.last_state is not None and state != self.last_state:
            if state == 'connected':
                if self._disconnect_timer:
                    GLib.source_remove(self._disconnect_timer)
                    self._disconnect_timer = None
                self.notify("VPN Connected", display_name(iface))
            elif state in ('no-network', 'stale'):
                if self._disconnect_timer:
                    GLib.source_remove(self._disconnect_timer)
                    self._disconnect_timer = None
                self.notify("VPN Down", "Connection lost")
            elif state == 'disconnected':
                if not self._disconnect_timer:
                    self._disconnect_timer = GLib.timeout_add_seconds(
                        10, self._fire_disconnect_notify)
        self.last_state = state

        # Icon
        if state == 'connected':
            self.indicator.set_icon_full("security-high-symbolic", "Connected")
            self.indicator.set_title(f"VPN: {display_name(iface)}")
        elif state == 'no-network':
            self.indicator.set_icon_full("security-low-symbolic", "No Network")
            self.indicator.set_title("VPN: No Network")
        elif state == 'stale':
            self.indicator.set_icon_full("security-low-symbolic", "Stale")
            self.indicator.set_title(f"VPN: Stale — {display_name(iface)}")
        else:
            self.indicator.set_icon_full("security-low-symbolic", "Disconnected")
            self.indicator.set_title("VPN: Off")

        return changed

    def _connect(self, conf):
        for c in get_configs():
            run(["sudo", "wg-quick", "down", str(c)], 5)
        run(["sudo", "ip", "link", "delete", conf.stem], 5)
        run(["sudo", "wg-quick", "up", str(conf)], 30)
        self.prefs["last_server"] = conf.stem
        save_prefs(self.prefs)
        GLib.idle_add(self._update_and_rebuild)

    def build_menu(self):
        menu = Gtk.Menu()
        state, iface = self.state, self.iface

        configs = get_configs()
        is_up = state in ('connected', 'stale')

        # Auto-connect toggle (top)
        auto_on = self.prefs.get("auto_connect_enabled", False)
        auto_item = Gtk.CheckMenuItem(label="Auto-connect")
        auto_item.set_active(auto_on)
        if not is_up and not auto_on:
            auto_item.set_sensitive(False)
        auto_item.connect("toggled", self.on_toggle_auto)
        menu.append(auto_item)

        # Disconnect
        disc = Gtk.MenuItem(label="Disconnect")
        disc.connect("activate", self.on_disconnect)
        disc.set_sensitive(is_up)
        menu.append(disc)
        menu.append(Gtk.SeparatorMenuItem())

        # Config list — clicking active server disconnects
        pinned = self.prefs.get("auto_connect")
        for conf in configs:
            active = is_up and iface == conf.stem
            mark = ("✓ " if state == 'connected' else "⚠ ") if active else ""
            suffix = " - Autoconnect" if auto_on and pinned == conf.stem else ""
            item = Gtk.MenuItem(label=f"{mark}{display_name(conf.stem)}{suffix}")
            item.connect("activate", lambda _, c=conf: self.on_connect(c))
            menu.append(item)

        if not configs:
            empty = Gtk.MenuItem(label="No configs found")
            empty.set_sensitive(False)
            menu.append(empty)

        menu.append(Gtk.SeparatorMenuItem())

        # Open configs folder (bottom)
        add = Gtk.MenuItem(label="Open configs folder")
        add.connect("activate", lambda _: subprocess.Popen(["xdg-open", str(CONFIG_DIR)], start_new_session=True))
        menu.append(add)

        menu.show_all()
        self.indicator.set_menu(menu)

    def _fire_disconnect_notify(self):
        self._disconnect_timer = None
        if self.last_state == 'disconnected':
            self.notify("VPN Disconnected", "")
        return False  # don't repeat

    def _update_and_rebuild(self):
        self._update_status()
        self.build_menu()

    def refresh(self):
        if self._update_status():
            self.build_menu()
        return True

    def on_connect(self, conf):
        threading.Thread(target=self._connect, args=(conf,), daemon=True).start()

    def on_connect_fastest(self):
        def do():
            self.notify("VPN", "Finding fastest server...")
            conf = find_fastest(get_configs())
            if conf:
                self._connect(conf)
                self.notify("VPN Connected", f"Fastest: {display_name(conf.stem)}")
            else:
                self.notify("VPN", "Could not reach any server")
                GLib.idle_add(self._update_and_rebuild)
        threading.Thread(target=do, daemon=True).start()

    def on_disconnect(self, _):
        def do():
            for c in get_configs():
                run(["sudo", "wg-quick", "down", str(c)], 5)
            GLib.idle_add(self._update_and_rebuild)
        threading.Thread(target=do, daemon=True).start()

    def on_toggle_auto(self, item):
        self.prefs["auto_connect_enabled"] = item.get_active()
        if item.get_active() and self.iface:
            self.prefs["auto_connect"] = self.iface
        save_prefs(self.prefs)
        self.build_menu()


if __name__ == "__main__":
    OmarchyVPN()
    Gtk.main()
