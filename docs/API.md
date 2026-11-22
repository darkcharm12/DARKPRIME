# REST API reference

Base URL: the HTTPS origin you configured, e.g. `https://darkprime.example.com`.
All request and response bodies are JSON. Device endpoints require
`Authorization: Bearer <device-token>`; operator endpoints require a bearer operator token from
`POST /api/auth/login` (or an authenticated dashboard session).

## Health

`GET /api/health` → `{"ok": true, "service": "DARKPRIME", "time": "..."}`

## Operator authentication

`POST /api/auth/login` with `{"username": "...", "password": "..."}` → `{"token": "...", "operator": {...}}`

`POST /api/auth/logout` with `Authorization: Bearer <operator-token>` → `{"ok": true}`

Failed logins are rate limited (10 per 5 minutes per IP).

## Enrollment tokens

`POST /api/enrollment-tokens` (operator) with `{"label": "..."}` → `{"token": "...", "expires_in_hours": 72}`

`GET /api/enrollment-tokens` (operator) → recent token metadata (never the raw token).

`POST /api/devices/enroll` (no auth, token in body):

```json
{
  "enrollment_token": "one-time-token",
  "device_uuid": "stable-random-uuid",
  "name": "Owner's phone",
  "model": "SM-S918B",
  "android_version": "14",
  "client_version": "1.0.0",
  "consent": {"accepted": true, "at": "2026-01-01T12:00:00Z"}
}
```

Response: `{"device_id": 1, "token": "device-bearer-token", "poll_interval_seconds": 900, ...}`.
Rejections: `403 explicit_consent_required`, `401 invalid_enrollment_token`,
`409 already used / already enrolled`, `410 expired`.

## Operator device endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/devices` | Enrolled devices with open alert counts. |
| GET | `/api/devices/<id>` | Device metadata plus latest payload. |
| GET | `/api/devices/<id>/history?limit=50` | Stored snapshots, newest first (max 500). |
| GET | `/api/devices/<id>/alerts` | Alerts for a device. |
| POST | `/api/devices/<id>/unenroll` | Request unenrollment; the app confirms and revokes its token. |
| POST | `/api/devices/<id>/screen-sessions` | Request an owner-approved screen session; previous live sessions are expired. |
| GET | `/api/devices/<id>/screen-sessions` | List recent screen sessions for the device. |
| GET | `/api/screen-sessions/<session_id>` | Get one screen session. |
| GET | `/api/screen-sessions/<session_id>/frame` | Latest approved JPEG frame (404 before the first upload). |
| POST | `/api/screen-sessions/<session_id>/stop` | Request stop (`stopping` for active sessions, immediate `stopped` for pending). |

## Device endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/devices/me` | Own status, pending actions and poll interval. |
| POST | `/api/devices/me/telemetry` | Submit a snapshot; returns alerts created and pending actions. Enforced minimum interval (15s default). |
| POST | `/api/devices/me/unenroll/request` | Owner requests unenrollment. |
| POST | `/api/devices/me/unenroll/confirm` | Owner revokes the token; device becomes `unenrolled`. |
| GET | `/api/devices/me/screen-sessions` | Pending/active session plus recent history. Also surfaced as `screen_session` in `pending_actions`. |
| POST | `/api/devices/me/screen-sessions/<id>/approve` | Owner approval; requires `{"consent":{"accepted":true,"at":"..."}}`. |
| POST | `/api/devices/me/screen-sessions/<id>/decline` | Owner declines a pending request. |
| POST | `/api/devices/me/screen-sessions/<id>/heartbeat` | Status poll; reports `stop_requested`. |
| POST | `/api/devices/me/screen-sessions/<id>/frame` | Upload one `image/jpeg` body (single frame, <1 MB by default). |
| POST | `/api/devices/me/screen-sessions/<id>/stop` | Owner ends the session and removes the stored frame. |

## Screen session lifecycle

`pending → active → stopping → stopped`; the owner may also return `pending → declined`, and a new
request expires any previous `pending`/`active`/`stopping` session. The frame is written to
`DARKPRIME_SCREEN_FRAME_DIR` (default `data/screen_frames/`) and served only to the owning operator.

Telemetry shape (abbreviated):

```json
{
  "captured_at": "2026-01-01T12:00:00Z",
  "client_version": "1.0.0",
  "device": {"model": "SM-S918B", "brand": "samsung", "android_version": "14", "sdk": 34, "security_patch": "2026-01-01"},
  "battery": {"level": 87, "charging": false, "health": 2},
  "storage": {"total_bytes": 128000000000, "free_bytes": 18000000000, "free_percent": 14},
  "apps": [{"package": "com.example", "label": "Example", "version_name": "1.0", "system": false,
            "requested_permissions": ["android.permission.INTERNET"]}],
  "security": {"accessibility_services": [], "device_admins": [], "darkprime_admin_active": false,
               "device_owner": false, "screen_lock_secure": true, "usb_debugging": false,
               "developer_options": false, "unknown_sources": false, "encryption_status": 2},
  "network": {"type": "wifi"},
  "scope": {"collected": ["device_info", "..."], "excluded": ["camera", "microphone", "..."]}
}
```

## Error format

`{"error": "machine_readable_code", ...}` with an appropriate HTTP status code.
