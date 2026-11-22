PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS operators (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS operator_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS enrollment_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    operator_id INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    label      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at    TEXT,
    device_id  INTEGER REFERENCES devices(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS devices (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    operator_id          INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
    device_uuid          TEXT NOT NULL UNIQUE,
    name                 TEXT NOT NULL,
    model                TEXT NOT NULL DEFAULT '',
    android_version      TEXT NOT NULL DEFAULT '',
    token_hash           TEXT UNIQUE,
    consent_at           TEXT NOT NULL,
    enrolled_at          TEXT NOT NULL,
    last_seen_at         TEXT,
    last_captured_at     TEXT,
    status               TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'unenrolled')),
    unenroll_requested_at TEXT,
    unenrolled_at        TEXT
);

CREATE TABLE IF NOT EXISTS screen_sessions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id         INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    operator_id       INTEGER NOT NULL REFERENCES operators(id) ON DELETE CASCADE,
    status            TEXT NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'active', 'stopping', 'stopped', 'declined', 'expired')),
    requested_at      TEXT NOT NULL,
    approved_at       TEXT,
    connected_at      TEXT,
    last_seen_at      TEXT,
    last_frame_at     TEXT,
    stop_requested_at TEXT,
    stopped_at        TEXT,
    consent_at        TEXT,
    frame_path        TEXT
);

CREATE TABLE IF NOT EXISTS telemetry (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    captured_at TEXT,
    received_at TEXT NOT NULL,
    payload     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id     INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    fingerprint   TEXT NOT NULL,
    severity      TEXT NOT NULL CHECK (severity IN ('info', 'low', 'medium', 'high')),
    code          TEXT NOT NULL,
    title         TEXT NOT NULL,
    detail        TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    acknowledged_at TEXT,
    UNIQUE (device_id, fingerprint)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    operator_id INTEGER REFERENCES operators(id) ON DELETE SET NULL,
    device_id  INTEGER REFERENCES devices(id) ON DELETE SET NULL,
    action     TEXT NOT NULL,
    detail     TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_screen_sessions_device_status ON screen_sessions(device_id, status, id DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_device_received ON telemetry(device_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_device_created ON alerts(device_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_devices_operator_status ON devices(operator_id, status);
