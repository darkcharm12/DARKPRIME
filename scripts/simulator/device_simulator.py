#!/usr/bin/env python3
"""Device simulator for testing the API without an Android device.

Usage:
  BASE_URL=https://127.0.0.1:8443 OP_USER=operator OP_PASS=... \
    python3 scripts/simulator/device_simulator.py [--insecure] [--uuid test-123]
"""
from __future__ import annotations

import argparse
import os
import uuid
from datetime import datetime, timezone

import requests


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sample_payload() -> dict:
    return {
        "captured_at": now(),
        "client_version": "simulator-1.0",
        "device": {"model": "SM-S918B", "brand": "samsung", "android_version": "14",
                   "sdk": 34, "security_patch": "2026-01-01"},
        "battery": {"level": 87, "charging": False},
        "storage": {"total_bytes": 128_000_000_000, "free_bytes": 18_000_000_000, "free_percent": 14},
        "apps": [
            {"package": "com.samsung.android.app", "label": "Samsung App", "version_name": "2.1",
             "requested_permissions": ["android.permission.INTERNET"], "system": False},
        ],
        "security": {"accessibility_services": [], "device_admins": ["com.darkprime.app/.DeviceAdminReceiver"],
                     "screen_lock_secure": True, "usb_debugging": False, "unknown_sources": False,
                     "developer_options": False, "encryption_status": 2},
        "network": {"type": "wifi"},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--insecure", action="store_true", help="disable TLS verification (self-signed dev only)")
    parser.add_argument("--uuid", default=str(uuid.uuid4()))
    args = parser.parse_args()

    base = os.environ.get("BASE_URL", "https://127.0.0.1:8443").rstrip("/")
    session = requests.Session()
    session.verify = False if args.insecure else os.environ.get("CA_BUNDLE", True)
    if args.insecure:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def call(method: str, path: str, **kwargs):
        response = session.request(method, base + path, timeout=15, **kwargs)
        if response.status_code >= 400:
            raise SystemExit(f"{method} {path} -> {response.status_code}: {response.text}")
        return response.json()

    login = call("POST", "/api/auth/login", json={
        "username": os.environ.get("OP_USER", "operator"),
        "password": os.environ.get("OP_PASS", ""),
    })
    op_headers = {"Authorization": f"Bearer {login['token']}"}

    token = call("POST", "/api/enrollment-tokens", headers=op_headers,
                 json={"label": f"simulator-{args.uuid[:8]}"})["token"]
    device = call("POST", "/api/devices/enroll", json={
        "enrollment_token": token,
        "device_uuid": args.uuid,
        "name": "Simulated Samsung",
        "model": "SM-S918B",
        "android_version": "14",
        "client_version": "simulator-1.0",
        "consent": {"accepted": True, "at": now()},
    })
    device_headers = {"Authorization": f"Bearer {device['token']}"}

    result = call("POST", "/api/devices/me/telemetry", headers=device_headers, json=sample_payload())
    listing = call("GET", "/api/devices", headers=op_headers)
    print(f"Enrolled device id={device['device_id']}")
    print(f"Telemetry accepted; alerts created: {result['alerts_created']}")
    print(f"Devices now visible: {len(listing['items'])}")
    print(f"Open dashboard at {base}/devices")


if __name__ == "__main__":
    main()
