# Kali Linux installation guide (beginner friendly)

This guide assumes a fresh Kali Linux install and no prior Flask experience. Commands are run in
a terminal. All files live in `~/Desktop/DARKPRIME`.

## 1. Install dependencies

```bash
cd ~/Desktop/DARKPRIME
bash scripts/setup_kali.sh
```

The script:

1. installs `python3`, `python3-venv`, `python3-pip`, `openssl`, `curl`, `ca-certificates`, `nginx`;
2. creates a virtual environment in `.venv` and installs `server/requirements.txt`;
3. generates `data/darkprime.env` with two random secrets (file mode 600) — **never share it**;
4. generates a self-signed development certificate in `server/certs/`;
5. creates the SQLite database `data/darkprime.sqlite3`;
6. prompts you to create the first operator account (username + 12+ character password).

You can pre-fill the account non-interactively:

```bash
export DARKPRIME_ADMIN_USER=operator
export DARKPRIME_ADMIN_PASS='a-long-random-password'
bash scripts/setup_kali.sh
```

## 2. Start the local HTTPS dashboard

```bash
./scripts/run_server.sh --tls --host 0.0.0.0
```

Open `https://<your-kali-ip>:8443/` in a browser. Your browser will warn about the self-signed
certificate; this is expected for a lab. Sign in with the operator account.

To find your IP: `hostname -I`.

## 3. Create an enrollment token

In the dashboard: **Enroll → Generate token**. Copy the one-time value and give it to the device
owner. It expires after 72 hours by default and can only be used once. Only a salted/peppered
hash of the token is stored.

## 4. Test without an Android device (optional)

```bash
export BASE_URL=https://127.0.0.1:8443
export OP_USER=operator OP_PASS='a-long-random-password'
.venv/bin/python scripts/simulator/device_simulator.py --insecure
```

The simulator enrolls a fake Samsung device, sends one telemetry snapshot, and prints the
created alerts. `--insecure` disables certificate verification; use it only with the local
self-signed certificate.

## 5. Production: cloud VPS, real domain and trusted HTTPS

Remote monitoring over mobile data requires a server reachable from the internet. Use a VPS with
a public IP and a DNS name you control.

1. Copy the project to `/opt/darkprime` and run `bash scripts/setup_kali.sh` there.
2. Obtain a trusted certificate (example with certbot):

   ```bash
   sudo apt-get install -y certbot python3-certbot-nginx
   sudo certbot certonly --standalone -d darkprime.example.com
   ```

3. Point `nginx/darkprime.conf` at the Let's Encrypt certificate and key:

   ```
   ssl_certificate     /etc/letsencrypt/live/darkprime.example.com/fullchain.pem;
   ssl_certificate_key /etc/letsencrypt/live/darkprime.example.com/privkey.pem;
   ```

4. Install and test the reverse proxy:

   ```bash
   bash scripts/deploy_nginx.sh darkprime.example.com
   sudo nginx -t && sudo systemctl restart nginx
   ```

5. Harden the application by uncommenting in `/opt/darkprime/data/darkprime.env`:

   ```
   export DARKPRIME_REQUIRE_HTTPS=1
   export DARKPRIME_COOKIE_SECURE=1
   ```

6. Install the gunicorn service:

   ```bash
   bash deploy/install_service.sh /opt/darkprime
   sudo systemctl status darkprime
   ```

7. Open `https://darkprime.example.com/`, sign in and create an enrollment token.

Firewall example (only HTTPS and SSH):

```bash
sudo ufw allow 22/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

**Never expose ADB, port 5555, or the raw Flask port (8000) to the internet.** ADB is not used by
DARKPRIME and must remain disabled on monitored devices unless the owner temporarily needs it.

## 6. Backups and upgrades

The database is `data/darkprime.sqlite3`. Stop the service, copy the database and
`data/darkprime.env` to a secure location, then restart. Export historical reports as JSON:

```bash
.venv/bin/python -m server.scripts.export_history \
  --database data/darkprime.sqlite3 --device-id 1 --output data/export-device-1.json
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Virtual environment missing` | Run `scripts/setup_kali.sh` first. |
| `TLS files missing` | Run `scripts/generate_cert.sh server/certs darkprime.local <ip>`. |
| Login fails | Check `data/darkprime.env` is sourced by `run_server.sh`, or recreate the operator. |
| Device never checks in | Confirm the phone can reach the HTTPS URL; check nginx logs in `/etc/darkprime/logs/`. |
| Android rejects certificate | Use a trusted certificate in production or a debug build with the lab certificate installed. |
