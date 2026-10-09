# /// script
# requires-python = ">=3.11"
# dependencies = ["bleak"]
# ///
"""Scan for BLE devices; if a Haylou/LS05 is found, dump its GATT table."""
import asyncio
import sys

from bleak import BleakClient, BleakScanner


async def main():
    found = await BleakScanner.discover(timeout=10, return_adv=True)
    target = None
    for dev, adv in sorted(found.values(), key=lambda x: -x[1].rssi):
        name = adv.local_name or dev.name or "?"
        print(f"{adv.rssi:4} {dev.address} {name} svc={adv.service_uuids} mfr={ {k: v.hex() for k, v in adv.manufacturer_data.items()} }")
        if target is None and any(s in name.lower() for s in ("haylou", "ls05", "solar")):
            target = dev
    if len(sys.argv) > 1:
        target = next((d for d, _ in found.values() if d.address == sys.argv[1]), target)
    if not target:
        print("\nNo Haylou found. Pass address as argument to force.")
        return
    print(f"\n== GATT {target.address} {target.name} ==")
    async with BleakClient(target) as c:
        for s in c.services:
            print(f"[S] {s.uuid} {s.description}")
            for ch in s.characteristics:
                val = ""
                if "read" in ch.properties:
                    try:
                        raw = await c.read_gatt_char(ch)
                        val = f" = {raw.hex()} {raw!r}"
                    except Exception as e:
                        val = f" (read err: {e})"
                print(f"   [C] {ch.uuid} {ch.properties}{val}")


asyncio.run(main())
