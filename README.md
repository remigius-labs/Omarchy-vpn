# omarchy-vpn

A WireGuard VPN tray icon built for [Omarchy](https://omarchy.org).

Drop your WireGuard configs into the `configs/` folder and manage connections from the system tray. Tested with ProtonVPN — should work with any WireGuard provider (Mullvad, self-hosted, etc.).

Click a server to connect, switch between them on the fly. Turn on auto-connect to automatically reconnect to your pinned server on startup. The tray icon updates in real time — full shield when connected, empty when not — with desktop notifications on state changes.

## Features

- **Click to connect** — pick a server from the menu, switch anytime
- **Auto-connect** — pin a server and reconnect to it automatically on startup
- **Live status** — icon and tooltip update every 3 seconds without flickering
- **Desktop notifications** — get notified on connect, disconnect, and connection drops
- **Smart detection** — distinguishes between connected, stale, no-network, and disconnected states
- **Hot-reload configs** — drop in or remove `.conf` files and the menu updates automatically
- **Clean server names** — `wg-us-42.conf` shows up as "US", not the raw filename

## Requirements

- [Omarchy](https://omarchy.org) (or any Linux desktop with a system tray)
- Python 3
- `python-gobject`
- `libayatana-appindicator3`
- `wireguard-tools`

```bash
sudo pacman -S python-gobject libayatana-appindicator wireguard-tools
```

## Setup

**1. Clone the repo**

```bash
git clone https://github.com/remigius-labs/Omarchy-vpn.git
cd Omarchy-vpn
```

**2. Add your WireGuard configs**

Drop `.conf` files into the `configs/` folder:

```
configs/
  wg-us-42.conf    → shows as "US"
  wg-de-15.conf    → shows as "DE"
  wg-jp-03.conf    → shows as "JP"
```

The `wg` prefix and trailing numbers are stripped automatically. You can add or remove configs at any time — the menu picks up changes within a few seconds.

**3. Allow passwordless sudo for WireGuard commands**

```bash
sudo visudo
```

Add (replace `yourusername`):

```
yourusername ALL=(ALL) NOPASSWD: /usr/bin/wg, /usr/bin/wg-quick, /usr/bin/ip
```

**4. Run it**

```bash
python3 omarchy-vpn.py &
```

To start it with Omarchy, add it to your Hyprland autostart.

## Usage

Click the tray icon to open the menu:

- **Server list** — click any server to connect. The active server is marked with ✓ (or ⚠ if stale)
- **Auto-connect** — toggle on while connected to pin the current server. On next startup, it reconnects automatically
- **Disconnect** — tears down the active tunnel
- **Open configs folder** — opens `configs/` so you can add or remove servers

## Connection status

The app polls `sudo wg show` every 3 seconds:

| Status | Meaning | Icon |
|---|---|---|
| Connected | Tunnel up, recent handshake (< 3 min) | Full shield |
| Stale | Tunnel up, no recent handshake | Empty shield |
| No network | Tunnel up, server unreachable | Empty shield |
| Disconnected | No active tunnel | Empty shield |

## Waybar

Make sure your Waybar config includes the tray module:

```json
"modules-right": ["tray", "clock"],

"tray": {
    "spacing": 8
}
```

## License

MIT
