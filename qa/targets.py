#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Target:
    name: str
    port: int
    load_protocol: str
    load_path: str = "/"
    description: str = ""


TARGETS: dict[str, Target] = {
    "machineH1A": Target("machineH1A", 10001, "http", "/", "WordPress + Reflex Gallery"),
    "machineH1B": Target("machineH1B", 10002, "redis", "", "Redis unauth"),
    "machineH1C": Target("machineH1C", 10004, "http", "/", "PHP diagnostics"),
    "machineH2A": Target("machineH2A", 10010, "http", "/login", "Jenkins"),
    "machineH2B": Target("machineH2B", 10011, "http", "/", "PHP admin panel"),
    "machineH2C": Target("machineH2C", 10012, "http", "/", "Tomcat manager"),
    "machineH3A": Target("machineH3A", 10020, "tcp", "", "SMB"),
    "machineH3B": Target("machineH3B", 10022, "http", "/", "Drupal"),
    "machineH3C": Target("machineH3C", 10023, "http", "/", "Git-exposed webapp"),
    "machineH4A": Target("machineH4A", 10030, "http", "/", "Node serialize"),
    "machineH4B": Target("machineH4B", 10031, "http", "/", "Spring4Shell stub"),
    "machineH4C": Target("machineH4C", 10032, "http", "/", "SSRF fetcher"),
    "machineH5A": Target("machineH5A", 10040, "http", "/", "Webmin stub"),
    "machineH5B": Target("machineH5B", 10041, "http", "/", "Elasticsearch stub"),
    "machineH5C": Target("machineH5C", 10042, "http", "/", "Struts stub"),
    "machineH6A": Target("machineH6A", 10050, "tcp", "", "distccd"),
    "machineH6B": Target("machineH6B", 10052, "tcp", "", "MongoDB"),
    "machineH6C": Target("machineH6C", 10053, "https", "/", "Heartbleed stub"),
    "machineH7A": Target("machineH7A", 10060, "udp_snmp", "", "SNMP"),
    "machineH7B": Target("machineH7B", 10062, "http", "/", "Grafana stub"),
    "machineH7C": Target("machineH7C", 10063, "rsync", "", "rsyncd"),
    "machineH8A": Target("machineH8A", 10070, "http", "/", "phpMyAdmin stub"),
    "machineH8B": Target("machineH8B", 10071, "http", "/", "Flask/Jinja2"),
    "machineH8C": Target("machineH8C", 10072, "http", "/", "Laravel debug"),
}


def selected_targets(raw: str | None) -> list[Target]:
    if not raw:
        return list(TARGETS.values())

    requested = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = [item for item in requested if item not in TARGETS]
    if unknown:
        valid = ", ".join(sorted(TARGETS))
        raise SystemExit(f"Unknown targets: {', '.join(unknown)}\nValid targets: {valid}")
    return [TARGETS[item] for item in requested]
