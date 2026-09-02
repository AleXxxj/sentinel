"""
Fake-phone simulator.

Stands in for the real Android app until we build it. It enrolls using a
one-time enroll token (exactly like a real phone would), then sends location
beacons in a loop, drifting a little each time so you can watch it "move" on
the dashboard map.

Usage:
    python simulator.py <ENROLL_TOKEN>
    python simulator.py <ENROLL_TOKEN> --lat 6.5244 --lng 3.3792 --interval 3

Get an ENROLL_TOKEN by creating a device (POST /devices) in the API docs, or
let demo.py do the whole thing for you.
"""
import argparse
import random
import struct
import sys
import time
import zlib

import httpx


def make_png(width: int = 64, height: int = 64, rgb=(200, 60, 60)) -> bytes:
    """Build a valid solid-colour PNG using only the standard library.

    Stands in for a real camera photo, so the evidence-upload pipeline can be
    demonstrated without a camera.
    """
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    row = b"\x00" + bytes(rgb) * width          # filter byte + pixels
    raw = row * height
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def main() -> None:
    parser = argparse.ArgumentParser(description="Sentinel fake-phone simulator")
    parser.add_argument("enroll_token", help="one-time enroll token from POST /devices")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--lat", type=float, default=6.5244, help="starting latitude")
    parser.add_argument("--lng", type=float, default=3.3792, help="starting longitude")
    parser.add_argument("--interval", type=float, default=3.0, help="seconds between beacons")
    parser.add_argument("--imei", default="350000000000001")
    args = parser.parse_args()

    client = httpx.Client(base_url=args.base_url, timeout=10.0)

    # 1) Enroll, exactly like a real phone: trade the one-time token for a
    #    long-lived device token.
    r = client.post(
        "/devices/enroll",
        json={"enroll_token": args.enroll_token, "imei": args.imei},
    )
    if r.status_code != 200:
        print(f"Enrollment failed ({r.status_code}): {r.text}", file=sys.stderr)
        sys.exit(1)

    data = r.json()
    device_id = data["device_id"]
    device_token = data["device_token"]
    headers = {"Authorization": f"Bearer {device_token}"}
    print(f"Enrolled as device #{device_id}. Sending beacons every {args.interval}s.")
    print("Press Ctrl+C to stop.\n")

    # 2) Beacon loop: report location, drifting slightly each time to mimic a
    #    phone moving through a city. Occasionally raise theft alerts so you can
    #    see the alert feed light up too.
    lat, lng = args.lat, args.lng
    battery = 100
    count = 0
    try:
        while True:
            count += 1
            # Drift ~a few hundred metres in a random direction.
            lat += random.uniform(-0.0009, 0.0009)
            lng += random.uniform(-0.0009, 0.0009)
            battery = max(1, battery - random.randint(0, 2))

            r = client.post(
                "/beacons",
                headers=headers,
                json={
                    "latitude": round(lat, 6),
                    "longitude": round(lng, 6),
                    "accuracy_m": round(random.uniform(5, 25), 1),
                    "battery_pct": battery,
                    "is_charging": False,
                },
            )
            if r.status_code == 201:
                print(f"  beacon sent -> {lat:.5f}, {lng:.5f}  (battery {battery}%)")
            else:
                print(f"  beacon rejected ({r.status_code}): {r.text}", file=sys.stderr)

            _maybe_raise_alert(client, headers, count, lat, lng, battery)

            # Check for commands from the owner (ring/lock/remove) and obey them,
            # exactly as the real Android agent will.
            if _handle_commands(client, headers):
                break  # a 'remove' command was executed; stop the agent

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nSimulator stopped.")


def _handle_commands(client, headers) -> bool:
    """Poll for and execute pending commands. Returns True if removed."""
    try:
        commands = client.get("/device/commands", headers=headers).json()
    except Exception:
        return False

    for cmd in commands:
        ctype = cmd["type"]
        print(f"  << COMMAND received: {ctype}")

        if ctype == "remove":
            # The real agent would release Device-Owner and uninstall here.
            _report(client, headers, cmd["id"], "completed", "agent uninstalled")
            print("  Agent removed by owner. Stopping.")
            return True
        elif ctype == "ring":
            _report(client, headers, cmd["id"], "completed", "played alarm 30s")
        elif ctype == "lock":
            _report(client, headers, cmd["id"], "completed", "screen locked")
        elif ctype == "wipe":
            _report(client, headers, cmd["id"], "completed", "device wiped")
        else:
            _report(client, headers, cmd["id"], "failed", "unknown command")
    return False


def _report(client, headers, command_id, status, result) -> None:
    client.post(
        f"/device/commands/{command_id}/result",
        headers=headers,
        json={"status": status, "result": result},
    )


def _maybe_raise_alert(client, headers, count, lat, lng, battery) -> None:
    """Simulate the theft events a real phone would detect."""
    alert = None
    if count == 4:
        # A thief swaps the SIM early on.
        alert = {
            "type": "sim_swap",
            "message": "New SIM detected",
            "new_sim_number": "+234803" + str(random.randint(1000000, 9999999)),
            "latitude": round(lat, 6),
            "longitude": round(lng, 6),
        }
    elif random.random() < 0.15:
        # Someone keeps typing the wrong PIN.
        alert = {
            "type": "failed_unlock",
            "message": f"{random.randint(3, 6)} failed unlock attempts",
            "latitude": round(lat, 6),
            "longitude": round(lng, 6),
        }
    elif battery <= 15:
        alert = {"type": "low_battery", "message": f"Battery at {battery}%"}

    if alert:
        r = client.post("/alerts", headers=headers, json=alert)
        if r.status_code == 201:
            print(f"  !! ALERT: {alert['type']} - {alert['message']}")
            # On a failed unlock, a real phone snaps the front camera. We upload
            # a generated placeholder image through the same pipeline.
            if alert["type"] == "failed_unlock":
                alert_id = r.json()["id"]
                photo = make_png(rgb=(random.randint(40, 220),) * 3)
                pr = client.post(
                    f"/device/alerts/{alert_id}/photo",
                    headers=headers,
                    files={"file": ("evidence.png", photo, "image/png")},
                )
                if pr.status_code == 200:
                    print("     + evidence photo uploaded")


if __name__ == "__main__":
    main()
