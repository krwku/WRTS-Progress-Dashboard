# Docker Deployment Guide

Run the WRTS Dashboard as two containers — the Streamlit UI and a background data
fetcher — on any machine with Docker installed (Windows, macOS, or Linux).

---

## Prerequisites

- **Docker Desktop** (Windows/macOS) or **Docker Engine + Compose plugin** (Linux)
  Download: https://www.docker.com/products/docker-desktop
- Verify the install:
  ```bash
  docker --version
  docker compose version
  ```

On Windows, enabling the **WSL 2 backend** is recommended. Allocate at least
2 CPU cores and 4 GB of memory in **Settings → Resources**.

---

## Quick start

From the repository root:

```bash
# 1. Create your student list from the example
cp students.txt.example students.txt
#    Windows: copy students.txt.example students.txt
#    Then edit students.txt and put in real student IDs, one per line.

# 2. Create the data files that get bind-mounted into the containers.
#    These MUST exist before the first start (see "Bind mounts" below).
touch wrts_cache.json wrts_fetch.log
#    Windows PowerShell:
#      New-Item -ItemType File wrts_cache.json, wrts_fetch.log

# 3. Build and start
docker compose up -d --build
```

Open the dashboard at **http://localhost:8501**.

The `wrts_fetcher` container runs `fetch_data.py` immediately on start, then
sleeps until the next interval (weekly by default).

---

## Bind mounts

Three host files are mounted into both containers so data survives rebuilds:

| Host file | Container path | Purpose |
|---|---|---|
| `students.txt` | `/app/students.txt` | Student ID list |
| `wrts_cache.json` | `/app/wrts_cache.json` | Fetched student data |
| `wrts_fetch.log` | `/app/wrts_fetch.log` | Fetch run log (JSON Lines) |

> **Important:** Docker bind-mounts single files, so each of these must exist on
> the host *before* `docker compose up`. If a file is missing, Docker creates a
> **directory** with that name on Linux (which then breaks the app), or fails
> outright on Windows. Step 2 of the quick start creates them.

`wrts_cache.json` and `wrts_fetch.log` are listed in `.gitignore` and
`.dockerignore` — they contain personal data and must never be committed or
baked into an image.

---

## Configuration

Both settings are read from the environment (or a `.env` file next to
`docker-compose.yml`):

| Variable | Default | Description |
|---|---|---|
| `TZ` | `Asia/Bangkok` | Container timezone |
| `FETCH_INTERVAL_SECONDS` | `604800` (7 days) | Delay between fetch runs |

Example `.env`:

```dotenv
TZ=Asia/Bangkok
FETCH_INTERVAL_SECONDS=1209600   # fetch every 14 days
```

`.env` is covered by `.gitignore`.

---

## Common commands

```bash
# View logs
docker compose logs -f
docker compose logs -f wrts_dashboard
docker compose logs -f wrts_fetcher

# Trigger a fetch immediately, without waiting for the interval
docker compose exec wrts_fetcher python fetch_data.py

# Restart / rebuild after code changes
docker compose restart wrts_dashboard
docker compose up -d --build

# Status and resource usage
docker compose ps
docker stats

# Stop (data files on the host are untouched)
docker compose stop
docker compose down
```

---

## Changing the port

Edit the `ports` mapping in `docker-compose.yml`:

```yaml
    ports:
      - "8080:8501"   # host port 8080 → container port 8501
```

Then `docker compose up -d` and open http://localhost:8080.

---

## Access from other machines on the LAN

1. Find the host machine's IP address (`ipconfig` on Windows, `ip addr` on Linux)
   — for example `192.168.1.10`.
2. Allow the port through the firewall. On Windows, in an **Administrator**
   PowerShell:
   ```powershell
   New-NetFirewallRule -DisplayName "WRTS Dashboard" -Direction Inbound -LocalPort 8501 -Protocol TCP -Action Allow
   ```
3. Browse to `http://192.168.1.10:8501` from another machine.

> Only do this on a trusted network. The dashboard has no authentication, and it
> displays personal data. See the PDPA notice in [README.md](README.md).

---

## Auto-start on boot

Both services use `restart: unless-stopped`, so Docker brings them back after a
reboot. On Windows, also enable **Settings → General → "Start Docker Desktop
when you log in"**.

---

## Health check

The `wrts_dashboard` image defines a `HEALTHCHECK` that polls Streamlit's
`/_stcore/health` endpoint using Python's standard library — no extra packages
are installed in the image for it. Check the result with:

```bash
docker compose ps          # STATUS column shows (healthy)
```

---

## Running the tests

Tests are not part of the runtime image. Run them on the host:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

---

## Troubleshooting

**Container won't start** — check `docker compose logs wrts_dashboard`. The
usual causes are a port already in use (change the mapping above) or a missing
bind-mount file (see "Bind mounts").

**`wrts_cache.json` shows up as a directory** — Docker created it because the
file didn't exist. Stop the stack, `rm -rf wrts_cache.json`, create it as an
empty file, and start again.

**Dashboard says the cache is empty** — the first fetch may still be running.
Follow it with `docker compose logs -f wrts_fetcher`, or force one with
`docker compose exec wrts_fetcher python fetch_data.py`.

**Code changes not reflected** — the image copies the source at build time.
Rebuild with `docker compose up -d --build`.

---

## Uninstall

```bash
docker compose down
docker rmi wrts-progress-dashboard-wrts_dashboard wrts-progress-dashboard-wrts_fetcher
```

Host data files (`students.txt`, `wrts_cache.json`, `wrts_fetch.log`) are not
removed by these commands — delete them manually if you want them gone.
