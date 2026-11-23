# Security model and limitations

## Consent and transparency

- Enrollment is impossible without a one-time operator token **and** an explicit consent flag sent
  by the app after the owner ticks a checkbox. The consent text is displayed in the app at all
  times and in the `scope` field of every report.
- A persistent foreground notification with **Review** and **Stop** actions is mandatory. The app
  has no hidden/stealth mode.
- Screen sharing is a separate, per-session approval: the dashboard request appears as a visible
  notification and an in-app explanation dialog, then Android's own MediaProjection consent dialog
  must be accepted. The system capture indicator and the same DARKPRIME foreground notification
  remain visible; there is no second notification for the screen session.
- The owner can stop screen sharing instantly from the app button, the notification action, or by
  declining/ending via the server; stopping releases MediaProjection immediately and deletes the
  stored frame.
- Unenrollment is available to the owner (notification action, app button) and to the operator
  (dashboard request). Confirmation revokes the device token server-side; the local token and
  scheduled work are cleared.

## Data collected

Device model/brand/manufacturer, Android version/SDK/security patch, battery level and charging
state, storage totals and free space, installed package names/labels/versions and their
**declared** permissions, enabled accessibility service names, device-admin status, screen-lock
status, USB-debugging/developer-options/unknown-sources flags, encryption status and network type.

Optional, owner-approved screen sharing sends low-resolution JPEG frames over the same HTTPS
channel only while a session is active. No keystroke injection, tap capture, file access or
credential harvesting is implemented.

Explicitly excluded: camera, microphone, SMS/messages, contacts, call logs, credentials,
browsing history, files, photos and location. The app declares no permissions for these.

## Authentication

- Operators: username + password hashed with Werkzeug PBKDF2; dashboard uses an HttpOnly, SameSite
  cookie; API clients use opaque bearer session tokens. Failed logins are throttled per IP and
  recorded in the audit log.
- Devices: a unique high-entropy bearer token issued at enrollment. Only a SHA-256 hash with a
  server-side pepper is stored (`TOKEN_PEPPER`), so a database dump is not enough to impersonate a
  device. Tokens are revoked on unenrollment.
- One-time enrollment tokens are single-use, expire (72h default), and are stored only as hashes.
- CSRF tokens protect all dashboard POST forms.

## Transport

- The Android client refuses non-HTTPS URLs (`ApiClient` validates the scheme) and the network
  security config sets `cleartextTrafficPermitted="false"`.
- Production should use a publicly trusted certificate (Let's Encrypt), TLS 1.2+, HSTS and nginx
  as the TLS terminator. With `DARKPRIME_REQUIRE_HTTPS=1` the Flask app rejects plain HTTP.
- Remote/cross-network access must use a public HTTPS origin (Cloudflare tunnel or VPS domain);
  private LAN IPs are not reachable from other networks.
- Debug builds trust user-installed CAs for local lab certificates; release builds trust only
  system CAs. Self-signed certificates are for testing only.

## Storage and auditability

- SQLite stores snapshots, deduplicated alerts, screen-session metadata, enrollment tokens and an
  append-only audit log. Screen frames are stored under `data/screen_frames/` (git-ignored) and are
  deleted when the owner stops the session; use filesystem permissions (600) and regular encrypted
  backups.
- Every alert rule is deterministic and explained in the dashboard, so findings can be reviewed
  with the device owner.

## Known limitations

- This is an auditing tool, not an anti-malware engine. Alerts are observations, not proof of
  compromise.
- Package enumeration may be restricted by Android's package visibility rules; the companion app
  requests `QUERY_ALL_PACKAGES` for owner-approved audits.
- OEM battery optimization can delay WorkManager check-ins; `last_seen_at` makes delays visible.
- A rooted device or a compromised OS can falsify any app-reported value. Correlate with owner
  observation.
- The operator dashboard does not implement multi-tenancy beyond per-operator device ownership.
  Run separate accounts for separate operators.
- ADB is never used. Do not expose ADB or the raw Flask port to any untrusted network.
