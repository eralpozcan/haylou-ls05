# Haylou Solar LS05-1 BLE protocol

Reverse-engineered for interoperability from the official Haylou Fun app (V4.0.7, `com.yingsheng.hayloufun`) and verified against a real watch (firmware `RH192IBV003006`).

The LS05-1 does **not** use the protobuf protocol of the original LS05. Haylou Fun drives it through its "Youcy" (UTE-style) controller, which uses a plain byte protocol.

## Discovery

- Advertised name: `Haylou Solar`.
- Manufacturer data, company id `0x534C`: `3c 02 05 31 00 00 <MAC 6 bytes>`. Byte 1 `02` means watch, byte 2 `05` means LS05.
- The watch advertises **only while it has no active connection**. While the phone app holds it, scanners cannot see it.
- No BLE pairing or bonding is needed. Authorization happens at the application layer (see Bind below).

## GATT

| Service | Characteristic | Props | Use |
|---|---|---|---|
| `000060ff-…` | `00006001-…` | write-without-response | **command channel** |
| `000060ff-…` | `00006002-…` | notify | **responses** |
| `000061ff-…` | `00006101-…` / `00006102-…` | wwr / notify | secondary channel (MTU sync) |
| `000055ff-…` | `000033f1-…` | read/write | watch config blob |
| `000056ff-…` | `000034f1-…` | read/wwr | watch config blob 2 |
| `0000180f-…` | `00002a19-…` | read/notify | standard battery level |
| `0000d0ff-3c17-d293-8e48-14fe2e4da212` | `ffd1…fff2` | | Realtek RTL876x OTA/DFU |

`…` = `-0000-1000-8000-00805f9b34fb`. Writes with response to `6001` fail with "Write Not Permitted".

On subscribe, the watch sends `1c` on `6002`.

## Bind (required first, every connection)

```
-> 20 02 <userId: uint32 big-endian>
<- 20 04 <code>
```

| code | meaning |
|---|---|
| 1 | succeed (already bound to this userId) |
| 2 | confirmed by the user on the watch |
| 3 | wait |
| 4 | confirmation started: the watch shows a prompt for about 35 s |
| 5 | cancelled |

A watch bound to a different userId (for example the official app's account) never reaches 1. To take it over, factory-reset the watch from its settings, keep the phone's Bluetooth off, then bind with your own id.

## Commands

All commands go to `6001`. Replies come on `6002` and echo the command byte first.

| Cmd | Request | Reply |
|---|---|---|
| Version | `02` | `02 <ASCII firmware id>` |
| Battery | `03` | `03 <percent>` |
| Set time | `04 YY YY MM DD hh mm ss 00` (year big-endian) | echo |
| Real-time steps | `09` | `09 YY YY MM DD hh ...` 18 bytes. Walk steps = u16 BE at [16..17], run steps = u16 BE at [11..12], total = walk + run; [10]+[15] = activity value (likely minutes). Sample (40 steps, watch showed 0.03 km / 1 kcal): `09 07 ea 0a 0a 02 00 28 00 00 00 00 00 29 2a 00 00 28`. Distance and kcal are not in this frame; the app derives them from steps and the user profile. [6..7], [13], [14] unknown |
| Step history | `0a YY YY MM DD 00 00` | multi-frame (not yet decoded) |
| Real-time heart rate | `16` | `16 11 00 <bpm>` every ~1 s while measuring (watch must be worn) |
| (pushed during HR) | | `18 04 YY YY MM DD hh mm <max> <min> <avg>` daily HR summary; `18 03 YY YY MM DD hh mm <bpm>` per-minute sample; `e5 00 00 <bpm>` (unknown) |
| Sleep history | | frames `1d` (header) and `1e` (6-byte records: 4 time bytes and a 16-bit minutes field) |

### Notification

The text is UTF-16BE, truncated to 255 bytes. Frames:

```
first:  0f 00 <type> <totalLen> <up to 16 bytes>
next:   0f <seq> <up to 18 bytes>          (seq = 1, 2, ...)
end:    0f fd
```

The watch acks each frame with `0f <seq>`. Known `type` values: 1 incoming call, 3 SMS, 4 generic/other, 5 WeChat, 10 Facebook, 11 Twitter, 13 Instagram, 15 WhatsApp, 16 Line, 18 Skype, 19 Messenger, 20 Viber, 21 VK.

### Weather (`0x11`, 3 frames, all acked as `11 0n`)

```
11 01 <code u16 LE> <cur> <high> <low> <pm25 u16 BE> <air u16 BE> <city: 8 bytes UTF-16BE, max 4 chars>
11 02 4 x (<code u16 LE> <high> <low>)      days 2-5
11 03 2 x (<code u16 LE> <high> <low>)      days 6-7
```

Temperatures are sign-magnitude bytes (bit 7 = negative). Icon codes (observed on the watch): 1 sun, 2 partly cloudy, 3 cloudy, 4 showers, 5 thunderstorm, 6 sleet, 7 rain, 8 rain (heavier?); no snow icon found in 1-8, snow is sent as sleet. 0 shows "?". `haylou.py` maps Open-Meteo WMO codes onto these.

### Alarm (`0x06`, acked as `06 01`)

```
06 <repeat> <hh> <mm> 02 08 06 00 <slot 1..3>     set
06 60 00 00 00 00 00 00 <slot>                     disable
```

`repeat` is a weekday bitmask; `0x7f` is assumed to mean every day.

### Watch face (`0x1a`)

`1a 01` returns `1a 01 <plateId u32> <width u16> <height u16> <sType> <maxSize u32>`. The test watch returned 240x240, no custom face, and a 1 MiB limit. Upload: `1a 02`, then data on `6101` with a 3-byte header, then `1a 03 00`. The face file format is not decoded yet.

### Language

`25 ab <id>`. Ids: 1 zh, 2 en, 3 ko, 4 ja, 5 de, 7 fr, 8 it, 9 pt, 10 ar, 12 hi, 13 pl, 14 ru, 15 nl, 16 tr, 17 bn, 18 ur, 19 id/jv, 20 pa, 21 th, 22 cs, 28 be, 88 uk. Languages are built into the firmware; no language-pack upload exists.

### Events sent by the watch (no request)

| Frame | Meaning |
|---|---|
| `12 07` / `12 08` / `12 09` | music screen: play-pause / next / previous (verified driving macOS media keys). `12 0a` was also seen, probably volume |
| `16 11 00 <bpm>`, `18 03 …`, `18 04 …` | heart rate during a measurement or a Breath session (Breath sends no data of its own) |

### Dangerous commands (documented, not exposed in `haylou.py`)

| Cmd | Effect |
|---|---|
| `07 00` | factory reset |
| `17 11` | power off |

Binding with a different userId while the watch is bound to another account (bind code 3, then forced) can also factory-reset the watch.
