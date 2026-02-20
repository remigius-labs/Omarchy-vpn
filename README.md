# omarchy-vpn

A WireGuard VPN tray icon built for [Omarchy](https://omarchy.org).

Drop in your WireGuard configs, click to connect. Tested with ProtonVPN — should work with any WireGuard provider (Mullvad, self-hosted, etc.) but not verified.

> ⚠️ **100% vibe coded.** I did not write a single line of this. It works for me, but use it at your own risk — especially the sudoers setup. Read the code before running it on your machine.

---

## Features

- System tray icon — full shield when connected, empty shield when not
- Auto-detects servers from your `configs/` folder — no hardcoded lists
- Click any server to connect, switch between them on the fly
- Auto-connect on startup — set it once, forget it
- Desktop notifications on connect/disconnect
- Detects stale connections and network drops independently

## Requirements

- [Omarchy](https://omarchy.org)
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
git clone https://github.com/yourusername/omarchy-vpn
cd omarchy-vpn
```

**2. Add your WireGuard configs**

Drop `.conf` files into the `configs/` folder:
```
configs/
  proton-us-01.conf
  mullvad-us-nyc.conf
  home-server.conf
```

The filename becomes the display name — `proton-us-01.conf` shows as "Proton Us 01".

**3. Allow `wg` and `wg-quick` without a password prompt**

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

To start it with Omarchy, add it to your autostart.

## Usage

Click the tray icon to open the menu:

- **Server list** — click any server to connect. Active server is marked ✓
- **Auto-connect** — click to cycle through your servers (or Off). Saved to `prefs.json`, connects automatically on next startup
- **Disconnect** — tears down the active tunnel
- **Open configs folder** — opens your `configs/` directory to add/remove configs

## How it detects connection status

Every 3 seconds it runs `sudo wg show` to check the active tunnel:

| Status | Meaning | Icon |
|--------|---------|------|
| Connected | Tunnel up, recent handshake (< 3 min) | Full shield |
| Stale | Tunnel up but no recent handshake | Empty shield |
| No network | Tunnel up but server endpoint unreachable | Empty shield |
| Disconnected | No active tunnel | Empty shield |

## Waybar tray setup

Make sure your Waybar config includes the tray module:

```json
"modules-right": ["tray", "clock"],

"tray": {
    "spacing": 8
}
```

## License

MIT
