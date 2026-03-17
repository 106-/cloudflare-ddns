#!/usr/bin/env python3
"""Cloudflare DNS updater - syncs A and/or AAAA records to current global IPs."""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import cloudflare
import requests
from cloudflare import Cloudflare

CONFIG_FILE = Path(__file__).parent / "config.json"

IPV4_SERVICES = [
    "https://api.ipify.org",
    "https://checkip.amazonaws.com",
    "https://ipv4.icanhazip.com",
]

IPV6_SERVICES = [
    "https://api6.ipify.org",
    "https://ipv6.icanhazip.com",
    "https://ipv6.seeip.org",
]


@dataclass
class Record:
    zone_id: str
    name: str
    cname_target: str | None = None


@dataclass
class Config:
    api_token: str
    ttl: int
    proxied: bool
    enable_ipv4: bool
    enable_ipv6: bool
    records: list[Record]


def load_config() -> Config:
    if not CONFIG_FILE.exists():
        print(f"Error: Config file not found: {CONFIG_FILE}")
        print("Copy config.example.json to config.json and fill in the values.")
        sys.exit(1)

    with CONFIG_FILE.open() as f:
        data = json.load(f)

    missing = [k for k in ("api_token", "records") if not data.get(k)]
    if missing:
        print(f"Error: Missing required config keys: {', '.join(missing)}")
        sys.exit(1)

    if not data["records"]:
        print("Error: 'records' must contain at least one entry.")
        sys.exit(1)

    enable_ipv4 = data.get("enable_ipv4", True)
    enable_ipv6 = data.get("enable_ipv6", False)
    if not enable_ipv4 and not enable_ipv6:
        print("Error: At least one of enable_ipv4 or enable_ipv6 must be true.")
        sys.exit(1)

    records = []
    for i, r in enumerate(data["records"]):
        missing_keys = [k for k in ("zone_id", "name") if not r.get(k)]
        if missing_keys:
            print(f"Error: records[{i}] is missing keys: {', '.join(missing_keys)}")
            sys.exit(1)
        records.append(Record(zone_id=r["zone_id"], name=r["name"], cname_target=r.get("cname_target")))

    return Config(
        api_token=data["api_token"],
        ttl=data.get("ttl", 1),
        proxied=data.get("proxied", False),
        enable_ipv4=enable_ipv4,
        enable_ipv6=enable_ipv6,
        records=records,
    )


def get_ip(services: list[str], label: str) -> str | None:
    for url in services:
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            ip = resp.text.strip()
            print(f"Current global {label}: {ip} (via {url})")
            return ip
        except requests.RequestException as e:
            print(f"Warning: Failed to get {label} from {url}: {e}")
    return None


def sync_record(cf: Cloudflare, config: Config, record: Record, record_type: str, ip: str) -> None:
    existing_list = cf.dns.records.list(
        zone_id=record.zone_id,
        type=record_type,
        name=record.name,
    )
    existing = existing_list.result[0] if existing_list.result else None

    params = dict(
        zone_id=record.zone_id,
        name=record.name,
        type=record_type,
        content=ip,
        ttl=config.ttl,
        proxied=config.proxied,
    )

    if existing is None:
        cf.dns.records.create(**params)
        print(f"  Created {record_type}: {record.name} -> {ip}")
    elif existing.content == ip:
        print(f"  {record_type} up to date: {record.name} -> {ip}")
    else:
        print(f"  Updating {record_type}: {record.name}  {existing.content} -> {ip}")
        cf.dns.records.update(existing.id, **params)


def sync_cname(cf: Cloudflare, config: Config, record: Record) -> None:
    existing_list = cf.dns.records.list(
        zone_id=record.zone_id,
        type="CNAME",
        name=record.name,
    )
    existing = existing_list.result[0] if existing_list.result else None

    params = dict(
        zone_id=record.zone_id,
        name=record.name,
        type="CNAME",
        content=record.cname_target,
        ttl=config.ttl,
        proxied=config.proxied,
    )

    if existing is None:
        cf.dns.records.create(**params)
        print(f"  Created CNAME: {record.name} -> {record.cname_target}")
    elif existing.content == record.cname_target:
        print(f"  CNAME up to date: {record.name} -> {record.cname_target}")
    else:
        print(f"  Updating CNAME: {record.name}  {existing.content} -> {record.cname_target}")
        cf.dns.records.update(existing.id, **params)


def main() -> None:
    config = load_config()
    cf = Cloudflare(api_token=config.api_token)

    ipv4 = get_ip(IPV4_SERVICES, "IPv4") if config.enable_ipv4 else None
    ipv6 = get_ip(IPV6_SERVICES, "IPv6") if config.enable_ipv6 else None

    if config.enable_ipv4 and not ipv4:
        print("Warning: Could not retrieve IPv4 address, skipping A records.")
    if config.enable_ipv6 and not ipv6:
        print("Warning: Could not retrieve IPv6 address, skipping AAAA records.")

    try:
        for record in config.records:
            print(f"[{record.name}]")
            if record.cname_target:
                sync_cname(cf, config, record)
            else:
                if ipv4:
                    sync_record(cf, config, record, "A", ipv4)
                if ipv6:
                    sync_record(cf, config, record, "AAAA", ipv6)

    except cloudflare.APIConnectionError as e:
        print(f"Error: Failed to connect to Cloudflare API: {e}")
        sys.exit(1)
    except cloudflare.AuthenticationError as e:
        print(f"Error: Cloudflare authentication failed (check api_token): {e}")
        sys.exit(1)
    except cloudflare.APIStatusError as e:
        print(f"Error: Cloudflare API returned {e.status_code}: {e.message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
