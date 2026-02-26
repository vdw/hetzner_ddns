"""Update Hetzner DNS A records with the host public IP.

The script supports two execution modes:
- one-shot mode (run once and exit), useful for Linux cron
- loop mode (run forever with interval), useful for long-running containers

Configuration is read from environment variables:
- HETZNER_API_TOKEN (required)
- HETZNER_ZONE_NAME (required)
- HETZNER_RECORD_NAMES (required, comma-separated subdomain names)
- HETZNER_INTERVAL (optional, default: 60)
- HETZNER_BASE_URL (optional, default: https://api.hetzner.cloud/v1)
"""

import argparse
import os
import time
from dataclasses import dataclass

import requests


@dataclass
class Config:
    """Runtime configuration loaded from environment variables."""

    token: str
    zone_name: str
    record_names: list[str]
    interval: int
    base_url: str


def load_config() -> Config:
    """Load and validate configuration from environment variables."""
    token = os.getenv("HETZNER_API_TOKEN", "").strip()
    zone_name = os.getenv("HETZNER_ZONE_NAME", "").strip()
    raw_record_names = os.getenv("HETZNER_RECORD_NAMES", "").strip()
    record_names = [name.strip() for name in raw_record_names.split(",") if name.strip()]
    interval = int(os.getenv("HETZNER_INTERVAL", "60"))
    base_url = os.getenv("HETZNER_BASE_URL", "https://api.hetzner.cloud/v1").strip()

    missing = []
    if not token:
        missing.append("HETZNER_API_TOKEN")
    if not zone_name:
        missing.append("HETZNER_ZONE_NAME")
    if not record_names:
        missing.append("HETZNER_RECORD_NAMES")

    if missing:
        raise ValueError(f"Missing required environment variable(s): {', '.join(missing)}")
    if interval <= 0:
        raise ValueError("HETZNER_INTERVAL must be a positive integer")

    return Config(
        token=token,
        zone_name=zone_name,
        record_names=record_names,
        interval=interval,
        base_url=base_url.rstrip("/"),
    )


def get_headers(token: str) -> dict[str, str]:
    """Build HTTP headers for Hetzner API requests."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def get_public_ip() -> str:
    """Return the current public IPv4/IPv6 text value of the host."""
    response = requests.get("https://ipinfo.io/ip", timeout=10)
    response.raise_for_status()
    return response.text.strip()


def get_zone_id(config: Config) -> str:
    """Resolve and return the zone ID for the configured zone name."""
    response = requests.get(
        f"{config.base_url}/zones",
        headers=get_headers(config.token),
        params={"name": config.zone_name},
        timeout=20,
    )
    response.raise_for_status()

    zones = response.json().get("zones", [])
    if not zones:
        raise RuntimeError(f"Zone not found: {config.zone_name}")

    return zones[0]["id"]


def update_record(config: Config, zone_id: str, name: str, ip: str) -> None:
    """Set the A record value of one subdomain to the provided IP."""
    url = f"{config.base_url}/zones/{zone_id}/rrsets/{name}/A/actions/set_records"
    payload = {"records": [{"value": ip}]}

    response = requests.post(url, headers=get_headers(config.token), json=payload, timeout=20)
    response.raise_for_status()


def run_once(config: Config, zone_id: str, previous_ip: str | None) -> str:
    """Run one update cycle and return the latest observed public IP."""
    ip = get_public_ip()

    if ip != previous_ip:
        print(f"🌍 New IP detected: {ip}")
        for name in config.record_names:
            print(f"Updating {name}.{config.zone_name} → {ip}")
            update_record(config, zone_id, name, ip)
    else:
        print("No IP change")

    return ip


def run(config: Config, once: bool = False) -> None:
    """Run DDNS synchronization in one-shot mode or continuous mode."""
    zone_id = get_zone_id(config)
    last_ip: str | None = None

    while True:
        try:
            last_ip = run_once(config, zone_id, last_ip)
        except Exception as error:
            print("Error:", error)
            if once:
                raise

        if once:
            return
        time.sleep(config.interval)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for runtime mode selection."""
    parser = argparse.ArgumentParser(description="Hetzner DDNS updater")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run exactly one check/update cycle and exit",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run(load_config(), once=args.once)
