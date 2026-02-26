# Hetzner DDNS Updater

Small Python script that updates one or more Hetzner DNS `A` records with your current public IP.

## Features

- Updates multiple subdomains in one run
- Supports one-shot mode (`--once`) for Linux cron
- Supports continuous mode (internal sleep loop) for long-running Docker/container use
- Configuration via environment variables (no token in source code)

## Environment Variables

Required:

- `HETZNER_API_TOKEN`: Hetzner API token
- `HETZNER_ZONE_NAME`: DNS zone name (example: `example.com`)
- `HETZNER_RECORD_NAMES`: comma-separated subdomain labels (example: `www,nextcloud`)

Optional:

- `HETZNER_INTERVAL`: loop interval in seconds (default: `60`)
- `HETZNER_BASE_URL`: API base URL (default: `https://api.hetzner.cloud/v1`)

## Run Locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Run once (good for cron):

```bash
HETZNER_API_TOKEN="..." \
HETZNER_ZONE_NAME="example.com" \
HETZNER_RECORD_NAMES="www" \
python3 hetzner_ddns.py --once
```

Run continuously (every 60 seconds by default):

```bash
HETZNER_API_TOKEN="..." \
HETZNER_ZONE_NAME="example.com" \
HETZNER_RECORD_NAMES="www" \
HETZNER_INTERVAL="60" \
python3 hetzner_ddns.py
```

## Linux Cron (every minute)

Edit crontab:

```bash
crontab -e
```

Add:

```cron
* * * * * cd /home/dkrestos/Projects/hetzner_ddns && HETZNER_API_TOKEN="..." HETZNER_ZONE_NAME="example.com" HETZNER_RECORD_NAMES="www" /usr/bin/python3 /home/dkrestos/Projects/hetzner_ddns/hetzner_ddns.py --once >> /tmp/hetzner_ddns.log 2>&1
```

## Docker

Build image:

```bash
docker build -t hetzner-ddns .
```

One-shot container run:

```bash
docker run --rm \
  -e HETZNER_API_TOKEN="..." \
  -e HETZNER_ZONE_NAME="example.com" \
  -e HETZNER_RECORD_NAMES="www" \
  hetzner-ddns --once
```

Long-running container:

```bash
docker run --name hetzner-ddns --restart unless-stopped -d \
  -e HETZNER_API_TOKEN="..." \
  -e HETZNER_ZONE_NAME="example.com" \
  -e HETZNER_RECORD_NAMES="www" \
  -e HETZNER_INTERVAL="60" \
  hetzner-ddns
```

Host cron calling one-shot container every minute:

```cron
* * * * * docker run --rm -e HETZNER_API_TOKEN="..." -e HETZNER_ZONE_NAME="example.com" -e HETZNER_RECORD_NAMES="www" hetzner-ddns --once >> /tmp/hetzner_ddns_docker.log 2>&1
```

## Docker Compose

Create your runtime env file:

```bash
cp .env.example .env
```

Start long-running service:

```bash
docker compose up -d --build
```

Stop service:

```bash
docker compose down
```

The compose service includes Docker log rotation using:

- `max-size: 10m`
- `max-file: 3`
