# Architecture

```
Kotlin app (Android, Wi-Fi or mobile data)
   |  HTTPS + bearer device token, JSON telemetry every ~15 min (WorkManager)
   v
nginx (TLS termination, HSTS, HTTP -> HTTPS redirect)
   |  http://127.0.0.1:8000
   v
gunicorn -> Flask app (Python)
   |-- REST API: enrollment, telemetry, unenrollment, alerts
   |-- Dashboard: devices, history, alerts, audit log, enrollment
   |-- Alert rules and SQLite persistence
   v
SQLite (data/darkprime.sqlite3): devices, telemetry, alerts, tokens, audit_log
```

## Components

- `android/`: Kotlin companion app. `EnrollmentManager` stores the device token in
  `EncryptedSharedPreferences`; `DeviceInventory` collects only the documented metadata;
  `TelemetryWorker` schedules HTTPS uploads; `MonitoringService` maintains the mandatory visible
  notification; `EnrollmentController` performs one-tap unenrollment.
- `server/`: Flask factory, blueprints for API and dashboard, SQLite layer, alert engine,
  authentication and templates.
- `scripts/`: Bash setup, certificate generation, local/production launchers and a device
  simulator.
- `nginx/`, `deploy/`: reverse proxy and systemd service for a cloud-hosted server.

## Consent lifecycle

1. Operator creates a single-use enrollment token.
2. Owner reads disclosure, enters token and ticks consent.
3. Server records consent time, issues a device bearer token (only its hash is stored).
4. App shows persistent notification and uploads snapshots.
5. Owner or operator requests unenrollment; app confirms and clears local state; server revokes
   the token and marks the device `unenrolled` with an audit entry.

## Alert rules (all deterministic)

`OLD_ANDROID`, `ACCESSIBILITY_SERVICE`, `DEVICE_ADMIN`, `NO_SCREEN_LOCK`, `USB_DEBUGGING`,
`UNKNOWN_SOURCES`, `NO_ENCRYPTION`, `DEVELOPER_OPTIONS`, `LOW_BATTERY`, `LOW_STORAGE`,
`APP_INSTALLED`, `APP_REMOVED`, `PERMISSIONS_CHANGED`.

Alerts are deduplicated per device by fingerprint and can be acknowledged from the dashboard.
