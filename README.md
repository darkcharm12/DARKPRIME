# DARKPRIME

Consent-based Android security monitoring and auditing platform operated from Kali Linux.

DARKPRIME is a defensive audit tool. It only monitors Android devices whose owner installed the
companion app and **explicitly enrolled** by entering a one-time token and ticking a consent
checkbox. Monitoring is always visible (persistent notification), and the owner can stop it at
any time from the app notification or the main screen.

## What it does

- Collects Android version / security patch level, device model, battery level, storage figures,
  installed application inventory with *declared* permissions, enabled accessibility services,
  device-admin status, screen-lock status, ADB/debugging flags and network type.
- Stores encrypted-transport snapshots and alerts in SQLite for historical reports.
- Generates deterministic security alerts (outdated Android, unknown accessibility services,
  extra device admins, no screen lock, USB debugging, new apps, changed permissions, and more).
- Provides an operator dashboard built with Flask and a REST API consumed by the Kotlin app.
- Supports optional owner-approved screen sharing: explicit in-app approval, Android capture
  consent, visible capture indicator, one foreground notification, and instant stop controls.
- Works across Wi-Fi and mobile data because communication goes through an HTTPS server you
  control (local HTTPS for labs, or a cloud VPS with a real domain and trusted certificate).

## What it deliberately does NOT do

- No hidden installation, no stealth, no background concealment. Screen sharing never starts
  without a separate owner approval and the Android system capture-consent dialog.
- No camera, microphone, SMS, contacts, call logs, browsing history, file or credential access.
- No bypass of Android permissions or user consent.
- No ADB exposure to the public internet. ADB is never used by DARKPRIME at all.

## Repository layout

```
DARKPRIME/
├── android/                 Kotlin companion app (Gradle)
│   └── app/src/main/
│       ├── AndroidManifest.xml
│       ├── java/com/darkprime/app/
│       └── res/             layouts, strings, icons, network security config
├── data/                    SQLite database + secrets (git-ignored)
├── deploy/                  systemd unit and service installer
├── docs/                    installation, security, API and architecture guides
├── nginx/                   HTTPS reverse-proxy configuration
├── scripts/                 Kali setup, certificates, server and simulator scripts
└── server/                  Flask application, REST API, dashboard, templates, tests
```

## Quick start (lab, Kali Linux)

```bash
cd ~/Desktop/DARKPRIME
bash scripts/setup_kali.sh
bash scripts/run_server.sh --tls --host 0.0.0.0
# Open https://<kali-ip>:8443/ and accept the self-signed certificate warning
```

Then follow `docs/ANDROID_SETUP.md` to install the app and enroll a device. For owner-approved
screen sharing and cross-network setup, see `docs/SCREEN_MONITORING.md`.

For production / remote monitoring over mobile data, follow `docs/INSTALL_KALI.md` section 5
(cloud VPS + real domain + Let's Encrypt + nginx + gunicorn).

## Verification

```bash
cd ~/Desktop/DARKPRIME
.venv/bin/python -m pytest server/tests -q
```

## License and responsibility

Use only with the informed, explicit consent of the device owner and in compliance with local
law and your organization's policy. This project is a transparency and auditing tool, not a
surveillance tool.
