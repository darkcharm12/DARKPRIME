# DARKPRIME

DARKPRIME is a **consent-based Android auditing and owner-approved remote support platform**. The Android companion app runs visibly, enrolls only with a one-time operator token and explicit owner consent, and reports limited device/security telemetry to a self-hosted operator dashboard. Remote screen sharing is available only after an explicit owner approval and Android’s system MediaProjection consent, with visible indicators and immediate stop controls.

> **Legal / ethical use only.** Use DARKPRIME only on devices you own or are explicitly authorized to audit, with informed consent and in compliance with applicable law and policy. It is not spyware and must not be used for covert surveillance.

## What it does

- **Visible monitoring**: persistent foreground notification while monitoring/screen sharing is active.
- **Explicit enrollment**: one-time enrollment token + in-app consent checkbox; owner can stop and unenroll from the app.
- **Telemetry dashboard**: device model/version, battery, storage, network state, installed app inventory metadata, and audit/alert visibility.
- **Owner-approved screen sharing**: operator requests session; owner approves in app; Android capture consent is required; owner can stop from app or notification; operator can request stop.
- **Remote-capable design**: works across networks when the app points to a **public HTTPS URL** (Cloudflare tunnel/domain/VPS with trusted TLS).

## What it does not do

- No stealth/hidden operation, no silent install, no permission bypass.
- No camera, microphone, SMS/call logs, contacts, or credential/keychain collection.
- No remote shell, arbitrary command execution, or public ADB exposure.

## Repository layout

```text
android/                 Android companion app (Kotlin, WorkManager, Room, OkHttp)
docs/                    Setup, security, API, architecture, screen monitoring
nginx/                   Example HTTPS reverse-proxy config
scripts/                 Kali setup, cert generation, server/tunnel helpers
server/                  Flask API/dashboard, SQLite schema, tests
```

## Quick start (Kali Linux, local lab)

```bash
cd ~/Desktop/DARKPRIME
bash scripts/setup_kali.sh
bash scripts/run_server.sh --tls --host 0.0.0.0
```

Open `https://<kali-ip>:8443/`, accept the lab cert warning on the operator machine, log in, create a one-time enrollment token, and enroll from the Android app. For Android build/install details, see [`docs/ANDROID_SETUP.md`](docs/ANDROID_SETUP.md).

## Remote / any-network operation

**Important:** a private LAN IP like `192.168.x.x` only works on the same Wi-Fi/LAN. For a phone on mobile data or another network, the app must use a **public HTTPS URL**.

### Option A — Quick Cloudflare tunnel (fast, temporary URL)

```bash
# Terminal 1 - server
cd ~/Desktop/DARKPRIME
bash scripts/run_server.sh --tls --host 0.0.0.0

# Terminal 2 - public tunnel
cd ~/Desktop/DARKPRIME
bash scripts/install_cloudflared.sh
bash scripts/start_remote_tunnel.sh
# force a new URL if needed: bash scripts/start_remote_tunnel.sh --force

# Terminal 3 - get URL
cd ~/Desktop/DARKPRIME
bash scripts/remote_status.sh
```

Paste the printed `PUBLIC_URL` into the Android app **Server URL**. Quick tunnel URLs change when the tunnel restarts; if it changes, update the URL in the app or re-enroll with a new one-time token.

### Option B — Stable production remote (recommended)

Use a VPS/domain with trusted HTTPS (Let's Encrypt + nginx + gunicorn), or a named Cloudflare Tunnel with a stable hostname. See [`docs/INSTALL_KALI.md`](docs/INSTALL_KALI.md) for deployment guidance.

## Android app remote checklist

1. Install latest APK from GitHub Actions artifact (**Build Android debug APK**).
2. Ensure Linux server is running and tunnel/VPS is reachable.
3. In app, Server URL must be `https://...` public/stable URL.
4. Create a **new one-time enrollment token** in dashboard for enrollment/re-enrollment.
5. Grant explicit consent in app. Approve screen sharing only when requested.
6. If network changes or tunnel URL changes: keep server/tunnel running, use **Update server URL** in app or re-enroll, then restart screen sharing if needed.

## Verification

```bash
cd ~/Desktop/DARKPRIME
.venv/bin/python -m pytest server/tests -q
```

Android CI builds run via GitHub Actions workflow. Local Gradle builds require a compatible JDK (CI uses Java 17).

## Security notes

- Do not commit secrets or runtime artifacts: `data/darkprime.env`, `data/darkprime.sqlite3`, `server/certs/*.key`, `server/certs/*.crt`, `.venv/`, APKs/build outputs.
- Rotate any credentials accidentally exposed.
- Keep TLS enabled; use trusted certificates for production remote access.
- Review [`docs/SECURITY.md`](docs/SECURITY.md) before deployment.

## License

This project is licensed under the [MIT License](LICENSE).
