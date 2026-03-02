"""Update Hetzner DNS A records with the host public IP.

The script supports two execution modes:
- one-shot mode (run once and exit), useful for Linux cron
- loop mode (run forever with interval), useful for long-running containers

Configuration is read from environment variables:
- HETZNER_API_TOKEN (required)
- HETZNER_ZONE_RECORDS (recommended, zone-to-record mapping)
- HETZNER_ZONE_NAME + HETZNER_RECORD_NAMES (legacy fallback)
- HETZNER_INTERVAL (optional, default: 60)
- HETZNER_BASE_URL (optional, default: https://api.hetzner.cloud/v1)

HETZNER_ZONE_RECORDS format:
    zone-a.com:www,api;zone-b.net:home,cloud
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
    zone_records: dict[str, list[str]]
    interval: int
    base_url: str


def parse_zone_records(raw: str) -> dict[str, list[str]]:
    """Parse zone-record mapping text into a validated dictionary.

    Example input:
        zone-a.com:www,api;zone-b.net:home,cloud
    """
    zone_records: dict[str, list[str]] = {}

    for zone_entry in [entry.strip() for entry in raw.split(";") if entry.strip()]:
        if ":" not in zone_entry:
            raise ValueError(
                "Invalid HETZNER_ZONE_RECORDS entry. "
                "Expected 'zone:record1,record2' separated by ';'"
            )

        zone_name, records_raw = zone_entry.split(":", 1)
        zone_name = zone_name.strip()
        records = [record.strip() for record in records_raw.split(",") if record.strip()]

        if not zone_name or not records:
            raise ValueError(
                "Invalid HETZNER_ZONE_RECORDS entry. "
                "Zone and at least one record are required"
            )

        zone_records[zone_name] = records

    return zone_records


def load_config() -> Config:
    """Load and validate configuration from environment variables."""
    token = os.getenv("HETZNER_API_TOKEN", "").strip()
    raw_zone_records = os.getenv("HETZNER_ZONE_RECORDS", "").strip()
    zone_name = os.getenv("HETZNER_ZONE_NAME", "").strip()
    raw_record_names = os.getenv("HETZNER_RECORD_NAMES", "").strip()
    interval = int(os.getenv("HETZNER_INTERVAL", "60"))
    base_url = os.getenv("HETZNER_BASE_URL", "https://api.hetzner.cloud/v1").strip()

    missing = []
    if not token:
        missing.append("HETZNER_API_TOKEN")

    zone_records: dict[str, list[str]]
    if raw_zone_records:
        zone_records = parse_zone_records(raw_zone_records)
    else:
        record_names = [name.strip() for name in raw_record_names.split(",") if name.strip()]
        if not zone_name:
            missing.append("HETZNER_ZONE_NAME")
        if not record_names:
            missing.append("HETZNER_RECORD_NAMES")
        zone_records = {zone_name: record_names} if zone_name and record_names else {}

    if missing:
        raise ValueError(f"Missing required environment variable(s): {', '.join(missing)}")
    if interval <= 0:
        raise ValueError("HETZNER_INTERVAL must be a positive integer")

    return Config(
        token=token,
        zone_records=zone_records,
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


def get_zone_id(config: Config, zone_name: str) -> str:
    """Resolve and return the zone ID for a given zone name."""
    response = requests.get(
        f"{config.base_url}/zones",
        headers=get_headers(config.token),
        params={"name": zone_name},
        timeout=20,
    )
    response.raise_for_status()

    zones = response.json().get("zones", [])
    if not zones:
        raise RuntimeError(f"Zone not found: {zone_name}")

    return zones[0]["id"]


def update_record(config: Config, zone_id: str, name: str, ip: str) -> None:
    """Set the A record value of one subdomain to the provided IP."""
    url = f"{config.base_url}/zones/{zone_id}/rrsets/{name}/A/actions/set_records"
    payload = {"records": [{"value": ip}]}

    response = requests.post(url, headers=get_headers(config.token), json=payload, timeout=20)
    response.raise_for_status()


def run_once(config: Config, zone_ids: dict[str, str], previous_ip: str | None) -> str:
    """Run one update cycle and return the latest observed public IP."""
    ip = get_public_ip()

    if ip != previous_ip:
        print(f"🌍 New IP detected: {ip}")
        for zone_name, record_names in config.zone_records.items():
            zone_id = zone_ids[zone_name]
            for name in record_names:
                print(f"Updating {name}.{zone_name} → {ip}")
                update_record(config, zone_id, name, ip)
    else:
        print("No IP change")

    return ip


def run(config: Config, once: bool = False) -> None:
    """Run DDNS synchronization in one-shot mode or continuous mode."""
    zone_ids = {zone_name: get_zone_id(config, zone_name) for zone_name in config.zone_records}
    last_ip: str | None = None

    while True:
        try:
            last_ip = run_once(config, zone_ids, last_ip)
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
