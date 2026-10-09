# /// script
# requires-python = ">=3.11"
# dependencies = ["bleak", "pyobjc-framework-Quartz; sys_platform == 'darwin'"]
# ///
"""Minimal Haylou Solar LS05-1 client (UTE/Youcy byte protocol, from Haylou Fun V4.0.7).

Usage: uv run haylou.py [battery|time|notify "text"]
"""
import asyncio
import plistlib
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

from bleak import BleakClient, BleakScanner

WRITE = "00006001-0000-1000-8000-00805f9b34fb"   # service 60ff, channel 0
USER_ID = 0x45464E4D  # "EFNM"; any fixed 32-bit id, the watch binds to it
NOTIFY = ["00006002-0000-1000-8000-00805f9b34fb", "00006102-0000-1000-8000-00805f9b34fb"]


def set_time_cmd(now: datetime) -> bytes:
    # 0x04 yearHi yearLo month day hour min sec <lang/format byte, app sends a locale flag>
    return bytes([4, now.year >> 8, now.year & 0xFF, now.month, now.day, now.hour, now.minute, now.second, 0])


def notify_cmds(text: str, msg_type: int = 4) -> list[bytes]:
    """0x0F frames, UTF-16BE, max 255 bytes; first frame carries type+total length, ends with 0F FD."""
    data = text.encode("utf-16-be")[:255]
    frames = [bytes([0x0F, 0, msg_type, len(data)]) + data[:16]]
    rest, i = data[16:], 1
    while rest:
        frames.append(bytes([0x0F, i]) + rest[:18])
        rest, i = rest[18:], i + 1
    return frames + [bytes([0x0F, 0xFD])]


def temp(t: float) -> int:
    """Sign-magnitude byte: bit 7 = negative."""
    t = round(t)
    return abs(t) | (0x80 if t < 0 else 0)


def weather_cmds(city: str, days: list[tuple[int, float, float, float]]) -> list[bytes]:
    """days: 7 x (code, current, high, low). Code = watch icon id (u16 little-endian)."""
    code, cur, hi, lo = days[0]
    f1 = bytearray([0x11, 1, code & 0xFF, code >> 8, temp(cur), temp(hi), temp(lo), 0, 0, 0, 0] + [0] * 8)
    name = city.encode("utf-16-be")[:8]
    f1[11:11 + len(name)] = name  # city: max 4 chars
    f2, f3 = bytearray([0x11, 2] + [0] * 16), bytearray([0x11, 3] + [0] * 8)
    for frame, chunk in ((f2, days[1:5]), (f3, days[5:7])):
        for i, (c, _, h, l) in enumerate(chunk):
            frame[2 + i * 4:6 + i * 4] = bytes([c & 0xFF, c >> 8, temp(h), temp(l)])
    return [bytes(f1), bytes(f2), bytes(f3)]


# Watch icon ids (observed): 1 sun, 2 partly cloudy, 3 cloudy, 4 showers, 5 thunderstorm, 6 sleet, 7 rain, 8 rain (heavy?); snow id unknown -> sleet
def wmo_to_icon(c: int) -> int:
    for codes, icon in (((0, 1), 1), ((2,), 2), ((3, 45, 48), 3), ((80, 81, 82), 4), ((95, 96, 99), 5),
                        ((56, 57, 66, 67, 71, 73, 75, 77, 85, 86), 6)):
        if c in codes:
            return icon
    return 7  # drizzle / rain (51-65)


def fetch_weather(lat=41.01, lon=28.98) -> list[tuple[int, float, float, float]]:
    """Open-Meteo (no API key). Default: Istanbul."""
    import json, urllib.request
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m"
           "&daily=weather_code,temperature_2m_max,temperature_2m_min&forecast_days=7&timezone=auto")
    j = json.load(urllib.request.urlopen(url, timeout=10))
    d = j["daily"]
    return [(wmo_to_icon(d["weather_code"][i]), j["current"]["temperature_2m"] if i == 0 else 0,
             d["temperature_2m_max"][i], d["temperature_2m_min"][i]) for i in range(7)]


# watch music screen key -> macOS NX media key (play 16, next 17, previous 18); 0x0a seen too, probably volume
MEDIA_KEYS = {0x07: 16, 0x08: 17, 0x09: 18}


def media(key: int):
    """Press a system media key, so it works for YouTube in the browser, Spotify, Music, ..."""
    if not MACOS:
        return print(f"   media key {key} (only implemented on macOS)")
    from AppKit import NSEvent
    from Quartz import CGEventPost, kCGHIDEventTap
    print(f"   media key: {({16: 'play/pause', 17: 'next', 18: 'previous'})[key]}")
    for down in (True, False):
        ev = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
            14, (0, 0), 0xA00 if down else 0xB00, 0, 0, None, 8, (key << 16) | ((0xA if down else 0xB) << 8), -1)
        CGEventPost(kCGHIDEventTap, ev.CGEvent())


def params_cmd(lang=16, height=170, weight=70, age=30, male=True, step_goal=8000) -> bytes:
    """User profile + settings (0x05). Language lives here (byte 16), not in 25 ab. Affects kcal/distance."""
    return (bytes([5]) + height.to_bytes(2, "big") + weight.to_bytes(2, "big") + bytes([5])  # screen-on 5 s
            + step_goal.to_bytes(4, "big") + bytes([1, 255, 0, age, int(male), 0, lang, 0, 0]))
    # raise-to-wake on, HR high alert off, -, age, sex, lost-warning off, lang, metric, HR low alert off


def alarm_cmd(slot: int, hhmm: str | None, repeat: int = 0x7F) -> bytes:
    """slot 1..3. hhmm=None disables. repeat = weekday bitmask (0x7F assumed = every day)."""
    if hhmm is None:
        return bytes([6, 0x60, 0, 0, 0, 0, 0, 0, slot])
    h, m = map(int, hhmm.split(":"))
    return bytes([6, repeat, h, m, 2, 8, 6, 0, slot])


CITY = "IST"  # max 4 chars on the watch
MACOS = sys.platform == "darwin"
NC_DB = Path.home() / "Library/Group Containers/group.com.apple.usernoted/db2/db"
NOTIFY_TYPES = {"net.whatsapp.WhatsApp": 15, "com.apple.MobileSMS": 3, "com.facebook.Messenger": 19}  # else 4


def mac_notifications(after: int) -> list[tuple[int, str, str]]:
    """New macOS Notification Center entries: (rec_id, bundle id, text). Needs Full Disk Access."""
    if not MACOS:
        return []  # ponytail: Linux (D-Bus) / Windows (UserNotificationListener) sources not written yet
    con = sqlite3.connect(f"file:{NC_DB}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT rec_id, data FROM record WHERE rec_id > ? ORDER BY rec_id", (after,)).fetchall()
    finally:
        con.close()
    out = []
    for rid, data in rows:
        p = plistlib.loads(data)
        req = p.get("req", {})
        text = ": ".join(s for s in (req.get("titl"), req.get("body")) if s)
        out.append((rid, p.get("app", ""), text))
    return out


async def serve(c: BleakClient):
    """Runs while connected: clock + weather on connect, weather every 3 h, Mac notifications -> watch."""
    async def send(frames):
        for p in frames:
            await c.write_gatt_char(WRITE, p, response=False)
            await asyncio.sleep(0.1)

    await send([set_time_cmd(datetime.now())])
    last_weather = 0.0
    last_id = max([r[0] for r in mac_notifications(0)], default=0)
    while c.is_connected:
        if time.time() - last_weather > 3 * 3600:
            try:
                await send(weather_cmds(CITY, fetch_weather()))
                last_weather = time.time()
            except OSError as e:
                print(f"weather fetch failed: {e}")
        for rid, app, text in mac_notifications(last_id):
            last_id = rid
            if text:
                print(f"notify [{app}] {text}")
                await send(notify_cmds(text, NOTIFY_TYPES.get(app, 4)))
        await asyncio.sleep(3)


async def main(cmd: str, arg: str):
    dev = await BleakScanner.find_device_by_name("Haylou Solar", timeout=15)
    if not dev:
        sys.exit("Haylou Solar not found (is it connected to the phone? Turn phone Bluetooth off).")
    async with BleakClient(dev) as c:
        verify = asyncio.Queue()

        def on_data(ch, d: bytearray):
            print(f"<- {ch.uuid[4:8]} {d.hex(' ')}")
            if d[:2] == b"\x20\x04" and len(d) > 2:
                verify.put_nowait(d[2])
            elif d[0] == 0x16 and len(d) >= 4 and d[2] == 0:
                print(f"   heart rate: {d[3]} bpm")
            elif d[0] == 0x12 and len(d) >= 2 and d[1] in MEDIA_KEYS:
                media(MEDIA_KEYS[d[1]])
            elif d[0] == 0x09 and len(d) >= 18:  # layout from Haylou Fun GetRealStepDataTask
                walk, run = int.from_bytes(d[16:18], "big"), int.from_bytes(d[11:13], "big")
                print(f"   steps: {walk + run} (walk {walk}, run {run}), active: {d[10] + d[15]}")
            elif d[0] == 0x03 and len(d) >= 2:
                print(f"   battery: {d[1]} %")

        for u in NOTIFY:
            await c.start_notify(u, on_data)
        # Bind/verify: 0x20 0x02 <userId BE32> -> 20 04 <code>
        # codes (BindDeviceTask): 1 succeed, 2 confirmed, 3 wait, 4 confirm started on watch (35 s), 5 cancel
        await c.write_gatt_char(WRITE, bytes([0x20, 2]) + USER_ID.to_bytes(4, "big"), response=False)
        code = await asyncio.wait_for(verify.get(), 5)
        if code == 3 and not FORCE_BIND:
            # "wait": watch is not on its QR/bind screen. If it is bound to another userId (e.g. the
            # official app), forcing an owner switch can factory-reset the watch.
            sys.exit("Watch not ready to bind (code 3). Open its QR screen, or rerun with --force-bind (may WIPE it).")
        while code in (3, 4):
            if code == 4:
                print("Confirm on the watch screen...")
            code = await asyncio.wait_for(verify.get(), 35)
        if code not in (1, 2):
            sys.exit(f"Bind failed (code {code}). Factory-reset the watch, keep phone Bluetooth off, retry.")
        if cmd == "serve":
            return await serve(c)
        cmds = {
            "battery": [b"\x03"],
            "version": [b"\x02"],
            "steps": [b"\x09"],
            "heart": [b"\x16"],  # real-time HR; reply 16 xx 00 <bpm>
            "time": lambda: [set_time_cmd(datetime.now())],
            "notify": lambda: notify_cmds(arg),
            "raw": lambda: [bytes.fromhex(arg)],
            "weather": lambda: weather_cmds(arg if arg != "Efenim" else "IST", fetch_weather()),
            "alarm": lambda: [alarm_cmd(1, arg if ":" in arg else None)],  # alarm 07:30 | alarm off
            "listen": [],  # print whatever the watch sends (music keys, camera, find phone, ...)
            "language": lambda: [params_cmd(lang=int(arg))],  # 16 = Turkish, 2 = English
            # icon sweep: today=n, next 6 days n+1..n+6, temps = code so each day shows its id
            "weathertest": lambda: weather_cmds("T", [(c, c, c, 0) for c in range(int(arg), int(arg) + 7)]),
        }[cmd]
        cmds = cmds() if callable(cmds) else cmds
        for p in cmds:
            print(f"-> {p.hex(' ')}")
            await c.write_gatt_char(WRITE, p, response=False)
            await asyncio.sleep(0.1)
        await asyncio.sleep({"heart": 40, "listen": 90}.get(cmd, 2))  # HR measurement takes ~30 s


FORCE_BIND = "--force-bind" in sys.argv
if FORCE_BIND:
    sys.argv.remove("--force-bind")

if __name__ == "__main__":
    assert notify_cmds("A") == [bytes([15, 0, 4, 2, 0, 0x41]), bytes([15, 0xFD])]
    cmd, arg = (sys.argv[1] if len(sys.argv) > 1 else "battery"), (" ".join(sys.argv[2:]) or "Efenim")
    if cmd != "serve":
        asyncio.run(main(cmd, arg))
    else:
        mac_notifications(0)  # fail fast if Full Disk Access is missing
        while True:  # reconnect forever; never force-binds, so it cannot wipe the watch
            try:
                asyncio.run(main(cmd, arg))
            except (Exception, SystemExit) as e:
                print(f"disconnected: {e!r}; retrying in 15 s", flush=True)
            time.sleep(15)
