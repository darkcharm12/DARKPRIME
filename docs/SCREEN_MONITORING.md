# Owner-approved screen monitoring

This document describes the optional screen-sharing feature added to the existing consent-based
DARKPRIME platform. It is **not** a hidden mode: nothing is captured until the device owner
explicitly approves the session in the app **and** accepts Android's MediaProjection consent dialog.

## User-visible flow

1. Operator opens **Device detail** and clicks **Request screen sharing**.
2. Device receives `pending_actions: ["screen_session"]` on its next check-in and shows a visible
   approval notification; when the app is open, it also shows an explanation dialog.
3. Owner taps **Approve and continue**. Notification permission is requested here, only if missing,
   with the rationale that the active-session notification and Stop action must remain visible.
4. Android's system capture-consent dialog appears. Cancelling it declines the request.
5. While active:
   - the Android capture indicator remains visible;
   - the same DARKPRIME foreground notification stays visible, with title
     *DARKPRIME screen sharing active* and a **Stop screen** action;
   - the app shows `Screen sharing: ACTIVE` and a **STOP SCREEN SHARING NOW** button;
   - the dashboard polls status every 3 seconds and shows the latest JPEG frame.
6. Stopping from the app, notification, or dashboard releases MediaProjection immediately, marks the
   session `stopped`, and deletes the stored frame.

There is no second screen-session notification and no hidden capture path. Notification permission
is not requested at app startup anymore; it is requested when a screen session is approved.

## Cross-network / remote operation (required for different Wi-Fi/mobile data)

The app only accepts HTTPS server URLs. A LAN address like `https://192.168.0.140:8443` works only
on the same network.

Use a public HTTPS origin:

```bash
cd ~/Desktop/DARKPRIME
bash scripts/run_server.sh --tls --host 0.0.0.0
bash scripts/install_cloudflared.sh   # first time
bash scripts/start_remote_tunnel.sh
```

Put the printed `PUBLIC_URL` in the app **Server URL**. Verify with `bash scripts/remote_status.sh`.
Quick tunnel URLs change on restart; for a stable URL, use VPS + domain + trusted cert.

Optional server settings:

| Setting | Default | Purpose |
| --- | --- | --- |
| `DARKPRIME_SCREEN_FRAME_DIR` | `data/screen_frames/` | Directory for latest per-session JPEG frames. |
| `DARKPRIME_MAX_CONTENT_LENGTH` | 1 MB | Maximum frame upload size; app sends ~480px JPEGs. |

## Session states

`pending → active → stopping → stopped`; owners may also return `pending → declined`. A new request
expires any previous `pending`, `active`, or `stopping` session and removes its frame. Frames are
served only to the operator who owns the device. Only the latest frame per session is stored.

## Security properties

- Separate consent from enrollment consent and separate Android system consent for every session.
- MediaProjection is released on stop, decline, unenroll, service destruction, HTTP 409, or Android's
  `MediaProjection.Callback.onStop()`.
- Device bearer token and operator ownership are checked on every API path.
- Dashboard POST routes are CSRF-protected.
- No tap/key injection, no file/photo/contact/message/camera/microphone access.
- Audit log records request, owner approval/decline, operator stop request, and owner stop.

## Tests

```bash
python3 -m pytest server/tests -q
```

Added tests cover: explicit consent rejection, approval, frame upload/download, heartbeat,
operator stop, owner stop, decline, API auth separation, dashboard status/control, and CSRF.

## Modified files for this feature

Backend:

- `server/schema.sql` — `screen_sessions` table and indexes.
- `server/config.py` — `SCREEN_FRAME_DIR` setting.
- `server/api.py` — session APIs, pending action, frame storage/retrieval.
- `server/dashboard.py` — Device detail data, request/stop/status/frame routes.
- `server/templates/device_detail.html` — session card, controls, frame, 3s polling.
- `server/tests/conftest.py` — temporary frame directory fixture.
- `server/tests/test_screen_sessions.py` — new end-to-end tests.

Android:

- `android/app/src/main/AndroidManifest.xml` — media-projection foreground service permission/type.
- `android/app/src/main/java/com/darkprime/app/MainActivity.kt` — permission timing, approval dialog,
  MediaProjection intent launch, app stop control, 5s status polling.
- `android/app/src/main/java/com/darkprime/app/MonitoringService.kt` — MediaProjection capture,
  throttled JPEG frames, heartbeat, stop handling, visible notification updates.
- `android/app/src/main/java/com/darkprime/app/ApiClient.kt` — session API calls and JPEG upload.
- `android/app/src/main/java/com/darkprime/app/TelemetryWorker.kt` — background request notification
  and cancellation.
- `android/app/src/main/res/layout/activity_main.xml` — screen status line and stop button.
- `android/app/src/main/res/values/strings.xml` — disclosure, request dialog, notification rationale.

Docs:

- `README.md`, `docs/API.md`, `docs/SECURITY.md`, `docs/ANDROID_SETUP.md`, `docs/SCREEN_MONITORING.md`.
