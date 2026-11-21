# Android companion app setup

## What the owner will see

The app is called **DARKPRIME**. It never installs silently. After installation it shows a plain
status (`NOT ENROLLED` or `MONITORING ACTIVE`), the full disclosure text, the server URL, and a
large **STOP MONITORING AND UNENROLL** button. While enrolled, a persistent notification is
displayed with **Review** and **Stop** actions. There is no hidden mode.

## 1. Build the APK

On the Kali machine (Android Studio SDK installed, `ANDROID_HOME`/`ANDROID_SDK_ROOT` set):

```bash
cd ~/Desktop/DARKPRIME/android
chmod +x gradlew
./gradlew assembleDebug
```

The APK is written to `android/app/build/outputs/apk/debug/app-debug.apk`.

For a release build, sign it with your own key using Android Studio or `apksigner`; do not commit
keystores to this repository.

## 2. Install on the device

```bash
adb devices
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

Or copy the APK to the phone and open it in the file manager. On Samsung devices you may need to
allow **Install unknown apps** for the file manager or your browser; this is a one-time Android
setting and is reported by the audit as `unknown_sources`.

USB debugging/ADB is only used by the owner to install the APK. DARKPRIME does not use ADB and
does not need it afterwards. Never enable ADB over network (`adb tcpip 5555`) or expose it.

## 3. Enroll (owner consent is mandatory)

1. Operator creates a one-time token in the web dashboard: **Enroll → Generate token**.
2. Give the token and the HTTPS server URL to the device owner.
3. Owner opens DARKPRIME, types the HTTPS URL (e.g. `https://darkprime.example.com`) and token.
4. Owner reads the disclosure and ticks **I have read the disclosure and explicitly consent**.
5. Owner taps **Enroll and start visible monitoring**.

The server rejects enrollment without `consent.accepted = true`. A token is single-use and
expires after 72 hours by default.

## 4. Permissions explained

| Permission | Why it is requested |
| --- | --- |
| `INTERNET`, `ACCESS_NETWORK_STATE` | HTTPS communication with your server; report network type. |
| `POST_NOTIFICATIONS` | Show the mandatory visible monitoring notification (Android 13+). |
| `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_DATA_SYNC` | Keep the visible status notification and periodic audit alive. |
| `RECEIVE_BOOT_COMPLETED` | Re-show the visible status after reboot while still enrolled. |
| `QUERY_ALL_PACKAGES` | List installed packages for the owner-approved audit on Android 11+. Only package metadata is read. |
| Device admin (optional, activated only by the owner) | Allows DARKPRIME to honestly report its own device-admin status. No policies are enforced. |

The app requests **no** camera, microphone, SMS, contacts, call log, location, storage-file or
credential permissions.

## 5. Samsung-specific notes

- Samsung Galaxy devices running Android 8+ are supported; One UI does not change the APIs used.
- **Settings → Biometrics and security → Install unknown apps** may be needed to sideload the APK.
- **Settings → Notifications** — make sure DARKPRIME notifications are allowed. Some Samsung
  power modes can suppress background work; disable *Sleeping apps* / put DARKPRIME in the
  never-sleeping list if reports stop arriving.
- **Samsung Knox / MDM**: if the device is managed by an organization, a work profile or Knox
  policy may block installation or background work. Ask the IT administrator; DARKPRIME does not
  attempt to bypass any policy.
- Battery optimization: the app uses Android WorkManager with a 15-minute periodic cycle; OEM
  battery restrictions may delay reports. The dashboard shows `last_seen_at` so gaps are visible.
- Device-admin status is read through the standard `DevicePolicyManager`; activating DARKPRIME's
  optional admin receiver grants no wipe/lock/password policies (the policy list is empty).

## 6. Stop monitoring / unenroll

The owner can do any of the following:

- Tap **Stop** in the persistent notification.
- Open the app and tap **STOP MONITORING AND UNENROLL**, then confirm.
- Ask the operator to click **Request unenrollment** in the dashboard.

All paths clear the locally stored token, cancel scheduled reports, stop the foreground service,
and revoke the server-side bearer token. The dashboard marks the device `unenrolled` and records
the event in the audit log. Re-enrollment requires a new one-time token and fresh consent.

## 7. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Server URL must start with https://` | Enter the exact HTTPS URL; plain HTTP is blocked in the app. |
| Enrollment fails HTTP 401 | Token wrong, expired or already used. Ask for a new one. |
| Enrollment fails HTTP 403 | Consent checkbox was not ticked. |
| TLS error on Android | Use a publicly trusted certificate in production. For a lab, install the lab CA as a system certificate or use a debug build (debug builds trust user-installed CAs). |
| No reports after enrollment | Check internet access, notification permission, battery optimizations, and the server logs. |
