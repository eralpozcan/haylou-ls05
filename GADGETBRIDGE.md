# Gadgetbridge support request: Haylou Solar LS05-1

Draft text for a new issue at https://codeberg.org/Freeyourgadget/Gadgetbridge/issues

---

**Title:** Support request: Haylou Solar LS05-1 (UTE/"Youcy" byte protocol), protocol fully documented

**Device:** Haylou Solar LS05-1. It advertises as `Haylou Solar` with manufacturer id `0x534C` and data `3c 02 05 31 …`. Firmware `RH192IBV003006`. The chip is a Realtek RTL876x, and the watch exposes Realtek's OTA service `d0ff-3c17-d293-8e48-14fe2e4da212`.

**Vendor app:** Haylou Fun 4.0.7 (`com.yingsheng.hayloufun`).

**Important:** the LS05-1 does **not** speak the protobuf protocol of the original LS05. Haylou Fun drives it with its "Youcy" controller, which uses a plain byte protocol: write-without-response to `6001` and notifications from `6002` (service `60ff`).

**What is documented and verified on a real watch** (all commands sent from a desktop over BLE, no vendor app involved):

- Application-layer bind `20 02 <userId BE32>`, with result codes 1–5. No BLE bonding is needed.
- Battery `03`, firmware version `02`, set time `04 …`.
- Notifications `0f …`: UTF-16BE text in frames, with an app-type byte.
- Real-time heart rate `16`, plus the per-minute and daily summary frames the watch pushes during a measurement.
- Real-time steps `09`: walk and run counts.
- Alarms `06 …`.
- 7-day weather `11 01/02/03`, with icon ids mapped.
- Music-control events from the watch `12 07/08/09`.
- Watch-face info `1a 01` (240×240, 1 MiB limit) and language ids.
- Dangerous commands, documented so that nobody sends them by accident: `07 00` factory reset, `17 11` power off. Also: forcing a bind while another userId owns the watch can wipe it.

Full specification: `PROTOCOL.md` in https://github.com/eralpozcan/haylou-ls05. A working reference client in Python/bleak is in the same repo (`haylou.py`).

**Not decoded yet:** step history (`0a`), sleep history (`1d`/`1e`), SpO2, stress, and the watch-face file format.

Happy to test patches on the device.
