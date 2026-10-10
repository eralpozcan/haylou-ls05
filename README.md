# haylou-ls05

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![Platforms](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey)

An open Bluetooth LE client and protocol documentation for the **Haylou Solar LS05-1** smartwatch. It lets you use the watch from your computer **without the official Haylou Fun app**.

- One Python file, one dependency ([bleak](https://github.com/hbldh/bleak)).
- Every command listed here was tested on a real watch (firmware `RH192IBV003006`).
- The full byte-level protocol is in [PROTOCOL.md](PROTOCOL.md), so you can port it to Gadgetbridge, ESP32, Home Assistant, and similar projects.

> [!WARNING]
> The LS05-1 is a different device from the original LS05: it uses a plain byte protocol, not protobuf. Nothing here applies to other Haylou models unless someone verifies it.

## Features

| Feature | Command | Status |
|---|---|---|
| Bind to the watch (no phone needed) | automatic | ✅ |
| Battery level / firmware version | `battery`, `version` | ✅ |
| Sync the watch clock | `time` | ✅ |
| Send a notification | `notify "text"` | ✅ |
| Live heart rate | `heart` | ✅ |
| Live step count (walk + run) | `steps` | ✅ |
| Set or clear an alarm | `alarm 07:30`, `alarm off` | ✅ |
| 7-day weather with icons ([Open-Meteo](https://open-meteo.com), no API key) | `weather IST` | ✅ |
| Watch music keys act as computer media keys | `listen`, `serve` | ✅ macOS |
| Forward desktop notifications to the watch | `serve` | ✅ macOS |
| Watch language | `language 16` | ⚠️ sent, no visible effect yet |
| Step / sleep / SpO2 history, custom watch faces | — | 🔍 partly documented |

## Requirements

- A Haylou Solar LS05-1.
- A computer with Bluetooth LE.
- [uv](https://docs.astral.sh/uv/). It installs Python and `bleak` on first run. Plain `pip install bleak` with Python 3.11+ works too.

## Quick start

```sh
git clone https://github.com/eralpozcan/haylou-ls05.git
cd haylou-ls05
uv run haylou.py battery
```

The first time you connect:

1. Factory-reset the watch: **Settings → Reset**. The watch shows a QR code.
2. Turn **off** Bluetooth on any phone that has Haylou Fun installed. Otherwise the app grabs the watch.
3. Run any command and **confirm the prompt on the watch**.

After that, the watch stays bound to this tool. The official app and this tool cannot both own the watch at the same time.

## Usage

```sh
uv run haylou.py battery            # battery: 56 %
uv run haylou.py version            # firmware id
uv run haylou.py time               # set the watch clock from this computer
uv run haylou.py notify "Hello!"    # notification on the watch
uv run haylou.py heart              # live heart rate, ~40 s (wear the watch)
uv run haylou.py steps              # steps: 40 (walk 40, run 0)
uv run haylou.py alarm 07:30        # alarm slot 1, every day
uv run haylou.py alarm off
uv run haylou.py weather IST        # forecast; city label is max 4 chars (default location: Istanbul)
uv run haylou.py listen             # 90 s of watch events; music keys press media keys
uv run haylou.py raw 03             # send any command as hex (see PROTOCOL.md)
uv run scan.py                      # list BLE devices and dump the watch's GATT table
```

To change the weather location, edit `fetch_weather(lat, lon)` in `haylou.py`.

## Background service

```sh
uv run haylou.py serve
```

`serve` keeps the watch connected and reconnects when the link drops. On every connection it syncs the clock and sends the weather, and it refreshes the weather every 3 hours. On macOS it also forwards desktop notifications to the watch and turns the watch's music keys into system media keys (works with YouTube, Spotify and Music).

| | macOS | Linux / Windows |
|---|---|---|
| BLE features (clock, weather, notify, heart rate, steps, alarm) | ✅ | ✅ |
| Forward desktop notifications | ✅ needs **Full Disk Access** for the app that runs it | not yet |
| Music keys as media keys | ✅ | not yet |

To start it at login, run `serve` from launchd (macOS) or a systemd user unit (Linux).

## Safety

- `haylou.py` never sends the factory-reset (`07 00`) or power-off (`17 11`) commands.
- Taking over a watch that is bound to another account can **wipe it**. The tool refuses unless you pass `--force-bind`.
- `raw` sends whatever you type. Check [PROTOCOL.md](PROTOCOL.md) first.

## How this was made

The protocol was reverse-engineered for interoperability. The method was to decompile the official Haylou Fun 4.0.7 Android app and then check every finding against a real watch over BLE. The repository contains no vendor code, only the protocol facts. [GADGETBRIDGE.md](GADGETBRIDGE.md) is a ready-to-post support request for [Gadgetbridge](https://gadgetbridge.org).

## Contributing

Issues and pull requests are welcome, especially for:

- Decoding the step, sleep and SpO2 history frames.
- The watch-face file format.
- Notification sources for Linux (D-Bus) and Windows.
- Confirming whether other Haylou models use the same protocol.
- Getting [Gadgetbridge](https://gadgetbridge.org) support added — see [GADGETBRIDGE.md](GADGETBRIDGE.md).

## License

[MIT](LICENSE). This is an independent project, not affiliated with or endorsed by Haylou.
