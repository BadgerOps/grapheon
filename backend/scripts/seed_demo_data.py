#!/usr/bin/env python3
"""
Graphēon Demo Seed Data
========================

Populates the database with a realistic example network for demos and testing.

Network topology:
  VLAN 10  - Management   (10.10.10.0/24)  — routers, switches, firewalls
  VLAN 20  - Servers       (10.20.20.0/24)  — web servers, DB servers, app servers
  VLAN 30  - Workstations  (10.30.30.0/24)  — employee machines
  VLAN 40  - IoT / OT      (10.40.40.0/24)  — cameras, sensors, printers
  VLAN 50  - DMZ           (172.16.1.0/24)  — public-facing services
  VLAN 99  - Guest         (192.168.99.0/24) — guest Wi-Fi

Usage:
    python scripts/seed_demo_data.py              # seed fresh data (clears existing)
    python scripts/seed_demo_data.py --append     # add to existing data
    python scripts/seed_demo_data.py --export     # export to JSON backup
    python scripts/seed_demo_data.py --restore backup.json  # restore from backup

Requirements:
    Run from the backend/ directory (or set PYTHONPATH).
"""

import argparse
import json
import sys
import uuid
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from random import choice, randint, sample

# ── Ensure we can import project modules ────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

# ── Default DB path ─────────────────────────────────────────────────
DEFAULT_DB = BACKEND_DIR / "data" / "network.db"


# ══════════════════════════════════════════════════════════════════════
# Demo data definitions
# ══════════════════════════════════════════════════════════════════════

VLAN_CONFIGS = [
    {
        "vlan_id": 10,
        "vlan_name": "Management",
        "description": "Network infrastructure — routers, switches, firewalls",
        "subnet_cidrs": '["10.10.10.0/24"]',
        "color": "#f97316",
        "is_management": True,
    },
    {
        "vlan_id": 20,
        "vlan_name": "Servers",
        "description": "Production server farm — web, app, database",
        "subnet_cidrs": '["10.20.20.0/24"]',
        "color": "#3b82f6",
        "is_management": False,
    },
    {
        "vlan_id": 30,
        "vlan_name": "Workstations",
        "description": "Employee desktops and laptops",
        "subnet_cidrs": '["10.30.30.0/24"]',
        "color": "#22c55e",
        "is_management": False,
    },
    {
        "vlan_id": 40,
        "vlan_name": "IoT / OT",
        "description": "Internet of Things — cameras, sensors, printers",
        "subnet_cidrs": '["10.40.40.0/24"]',
        "color": "#06b6d4",
        "is_management": False,
    },
    {
        "vlan_id": 50,
        "vlan_name": "DMZ",
        "description": "Demilitarized zone — public-facing services",
        "subnet_cidrs": '["172.16.1.0/24"]',
        "color": "#ef4444",
        "is_management": False,
    },
    {
        "vlan_id": 99,
        "vlan_name": "Guest",
        "description": "Guest wireless network — internet-only access",
        "subnet_cidrs": '["192.168.99.0/24"]',
        "color": "#8b5cf6",
        "is_management": False,
    },
]

# ── Hosts per VLAN ──────────────────────────────────────────────────
# Each tuple: (ip, hostname, mac, device_type, os_name, os_version, os_family, vendor)

HOSTS = {
    10: [  # Management
        ("10.10.10.1",   "core-rtr-01",   "00:1a:2b:3c:4d:01", "router",   "Cisco IOS",    "15.7",  "network",  "Cisco Systems"),
        ("10.10.10.2",   "core-rtr-02",   "00:1a:2b:3c:4d:02", "router",   "Cisco IOS",    "15.7",  "network",  "Cisco Systems"),
        ("10.10.10.10",  "dist-sw-01",    "00:1a:2b:3c:4d:10", "switch",   "Cisco NX-OS",  "9.3",   "network",  "Cisco Systems"),
        ("10.10.10.11",  "dist-sw-02",    "00:1a:2b:3c:4d:11", "switch",   "Arista EOS",   "4.28",  "network",  "Arista Networks"),
        ("10.10.10.12",  "access-sw-01",  "00:1a:2b:3c:4d:12", "switch",   "Cisco IOS",    "15.2",  "network",  "Cisco Systems"),
        ("10.10.10.20",  "fw-01",         "00:1a:2b:3c:4d:20", "firewall", "pfSense",      "2.7",   "linux",    "Netgate"),
        ("10.10.10.21",  "fw-02",         "00:1a:2b:3c:4d:21", "firewall", "Palo Alto PAN-OS", "11.1", "network", "Palo Alto Networks"),
    ],
    20: [  # Servers
        ("10.20.20.1",   "core-rtr",      "00:50:56:aa:00:01", "router",   "VyOS",         "1.4",   "linux",    "VMware"),
        ("10.20.20.10",  "web-01",        "00:50:56:aa:20:10", "server",   "Ubuntu",       "22.04", "linux",    "VMware"),
        ("10.20.20.11",  "web-02",        "00:50:56:aa:20:11", "server",   "Ubuntu",       "22.04", "linux",    "VMware"),
        ("10.20.20.12",  "web-03",        "00:50:56:aa:20:12", "server",   "Ubuntu",       "24.04", "linux",    "VMware"),
        ("10.20.20.20",  "app-01",        "00:50:56:aa:20:20", "server",   "RHEL",         "9.3",   "linux",    "VMware"),
        ("10.20.20.21",  "app-02",        "00:50:56:aa:20:21", "server",   "RHEL",         "9.3",   "linux",    "VMware"),
        ("10.20.20.30",  "db-01",         "00:50:56:aa:20:30", "server",   "Ubuntu",       "22.04", "linux",    "VMware"),
        ("10.20.20.31",  "db-02",         "00:50:56:aa:20:31", "server",   "Ubuntu",       "22.04", "linux",    "VMware"),
        ("10.20.20.40",  "monitor-01",    "00:50:56:aa:20:40", "server",   "Debian",       "12",    "linux",    "VMware"),
        ("10.20.20.50",  "dns-01",        "00:50:56:aa:20:50", "server",   "Windows Server", "2022", "windows", "VMware"),
        ("10.20.20.51",  "ad-dc-01",      "00:50:56:aa:20:51", "server",   "Windows Server", "2022", "windows", "VMware"),
        ("10.20.20.60",  "backup-01",     "00:50:56:aa:20:60", "server",   "TrueNAS",      "13.0",  "linux",    "iXsystems"),
    ],
    30: [  # Workstations
        ("10.30.30.1",   "core-rtr",      "00:50:56:aa:00:01", "router",   "VyOS",         "1.4",   "linux",    "VMware"),
        ("10.30.30.10",  "ws-jsmith",     "a4:83:e7:10:30:10", "workstation", "Windows",   "11",    "windows",  "Dell"),
        ("10.30.30.11",  "ws-jdoe",       "a4:83:e7:10:30:11", "workstation", "Windows",   "11",    "windows",  "Dell"),
        ("10.30.30.12",  "ws-abrown",     "a4:83:e7:10:30:12", "workstation", "Windows",   "11",    "windows",  "Lenovo"),
        ("10.30.30.13",  "ws-mjones",     "3c:22:fb:10:30:13", "workstation", "macOS",     "14.2",  "macos",    "Apple"),
        ("10.30.30.14",  "ws-kwilson",    "3c:22:fb:10:30:14", "workstation", "macOS",     "14.3",  "macos",    "Apple"),
        ("10.30.30.15",  "ws-rgarcia",    "a4:83:e7:10:30:15", "workstation", "Ubuntu",    "24.04", "linux",    "Dell"),
        ("10.30.30.20",  "ws-tlee",       "a4:83:e7:10:30:20", "workstation", "Windows",   "11",    "windows",  "HP"),
        ("10.30.30.21",  "ws-nchen",      "a4:83:e7:10:30:21", "workstation", "Windows",   "10",    "windows",  "HP"),
        ("10.30.30.22",  "ws-dpatel",     "3c:22:fb:10:30:22", "workstation", "macOS",     "15.0",  "macos",    "Apple"),
    ],
    40: [  # IoT / OT
        ("10.40.40.1",   "core-rtr",      "00:50:56:aa:00:01", "router",   "OpenWrt",      "23.05", "linux",    "TP-Link"),
        ("10.40.40.10",  "cam-lobby",     "b0:c5:54:40:00:10", "iot",      "Linux",        "4.19",  "linux",    "Hikvision"),
        ("10.40.40.11",  "cam-parking",   "b0:c5:54:40:00:11", "iot",      "Linux",        "4.19",  "linux",    "Hikvision"),
        ("10.40.40.12",  "cam-warehouse", "b0:c5:54:40:00:12", "iot",      "Linux",        "4.19",  "linux",    "Dahua"),
        ("10.40.40.20",  "sensor-hvac-1", "dc:a6:32:40:00:20", "iot",      "RTOS",         "1.0",   "unknown",  "Honeywell"),
        ("10.40.40.21",  "sensor-hvac-2", "dc:a6:32:40:00:21", "iot",      "RTOS",         "1.0",   "unknown",  "Honeywell"),
        ("10.40.40.30",  "ptr-floor2",    "00:17:c8:40:00:30", "printer",  "Embedded",     "3.12",  "unknown",  "HP"),
        ("10.40.40.31",  "ptr-floor3",    "00:17:c8:40:00:31", "printer",  "Embedded",     "4.5",   "unknown",  "Xerox"),
        ("10.40.40.32",  "ptr-exec",      "00:17:c8:40:00:32", "printer",  "Embedded",     "2.1",   "unknown",  "Canon"),
    ],
    50: [  # DMZ
        ("172.16.1.1",   "dmz-fw",        "00:1a:2b:dd:50:01", "firewall", "OPNsense",    "24.1",  "linux",    "Deciso"),
        ("172.16.1.10",  "edge-lb-01",    "00:50:56:dd:50:10", "server",   "HAProxy",      "2.9",   "linux",    "VMware"),
        ("172.16.1.11",  "edge-web-01",   "00:50:56:dd:50:11", "server",   "Nginx",        "1.25",  "linux",    "VMware"),
        ("172.16.1.12",  "edge-web-02",   "00:50:56:dd:50:12", "server",   "Nginx",        "1.25",  "linux",    "VMware"),
        ("172.16.1.20",  "vpn-01",        "00:50:56:dd:50:20", "server",   "WireGuard",    "1.0",   "linux",    "VMware"),
        ("172.16.1.30",  "mail-01",       "00:50:56:dd:50:30", "server",   "Postfix",      "3.8",   "linux",    "VMware"),
    ],
    99: [  # Guest
        ("192.168.99.1",  "guest-gw",     "00:50:56:ee:99:01", "router",   "OpenWrt",     "23.05", "linux",     "Ubiquiti"),
        ("192.168.99.10", "guest-phone1", "f0:d4:e2:99:00:10", "workstation", "iOS",      "17.2",  "unknown",   "Apple"),
        ("192.168.99.11", "guest-phone2", "a8:9c:ed:99:00:11", "workstation", "Android",  "14",    "unknown",   "Samsung"),
        ("192.168.99.12", "guest-laptop", "dc:41:a9:99:00:12", "workstation", "Windows",  "11",    "windows",   "Microsoft"),
    ],
}

# ── Port profiles by device type ────────────────────────────────────

PORT_PROFILES = {
    "router": [
        (22, "tcp", "open", "ssh", "OpenSSH", "8.9"),
        (23, "tcp", "filtered", "telnet", None, None),
        (80, "tcp", "open", "http", "lighttpd", "1.4"),
        (161, "udp", "open", "snmp", "net-snmp", "5.9"),
        (443, "tcp", "open", "https", "lighttpd", "1.4"),
    ],
    "switch": [
        (22, "tcp", "open", "ssh", "OpenSSH", "7.6"),
        (80, "tcp", "open", "http", "Apache", "2.4"),
        (161, "udp", "open", "snmp", "net-snmp", "5.8"),
        (443, "tcp", "open", "https", "Apache", "2.4"),
    ],
    "firewall": [
        (22, "tcp", "open", "ssh", "OpenSSH", "9.1"),
        (80, "tcp", "open", "http", "nginx", "1.25"),
        (443, "tcp", "open", "https", "nginx", "1.25"),
        (8443, "tcp", "open", "https-alt", "Management UI", "1.0"),
    ],
    "server": [
        (22, "tcp", "open", "ssh", "OpenSSH", "8.9"),
        (80, "tcp", "open", "http", "Apache", "2.4"),
        (443, "tcp", "open", "https", "Apache", "2.4"),
    ],
    "server_web": [
        (22, "tcp", "open", "ssh", "OpenSSH", "8.9"),
        (80, "tcp", "open", "http", "nginx", "1.25"),
        (443, "tcp", "open", "https", "nginx", "1.25"),
        (8080, "tcp", "open", "http-proxy", "Varnish", "7.4"),
    ],
    "server_db": [
        (22, "tcp", "open", "ssh", "OpenSSH", "8.9"),
        (3306, "tcp", "open", "mysql", "MySQL", "8.0"),
        (5432, "tcp", "open", "postgresql", "PostgreSQL", "16.1"),
        (6379, "tcp", "open", "redis", "Redis", "7.2"),
    ],
    "server_app": [
        (22, "tcp", "open", "ssh", "OpenSSH", "8.9"),
        (8080, "tcp", "open", "http-proxy", "Tomcat", "10.1"),
        (8443, "tcp", "open", "https-alt", "Tomcat", "10.1"),
        (9090, "tcp", "open", "zeus-admin", "Prometheus", "2.48"),
    ],
    "server_dns": [
        (22, "tcp", "open", "ssh", "OpenSSH", "8.9"),
        (53, "tcp", "open", "domain", "Microsoft DNS", "10.0"),
        (53, "udp", "open", "domain", "Microsoft DNS", "10.0"),
        (88, "tcp", "open", "kerberos-sec", "Microsoft Kerberos", "10.0"),
        (135, "tcp", "open", "msrpc", "Microsoft RPC", None),
        (389, "tcp", "open", "ldap", "Microsoft LDAP", None),
        (445, "tcp", "open", "microsoft-ds", "Samba smbd", "4.6"),
    ],
    "server_monitor": [
        (22, "tcp", "open", "ssh", "OpenSSH", "8.9"),
        (3000, "tcp", "open", "ppp", "Grafana", "10.2"),
        (9090, "tcp", "open", "zeus-admin", "Prometheus", "2.48"),
        (9100, "tcp", "open", "jetdirect", "Node Exporter", "1.7"),
    ],
    "workstation": [
        (135, "tcp", "open", "msrpc", "Microsoft RPC", None),
        (139, "tcp", "open", "netbios-ssn", None, None),
        (445, "tcp", "open", "microsoft-ds", "Samba smbd", "4.6"),
    ],
    "workstation_mac": [
        (22, "tcp", "open", "ssh", "OpenSSH", "9.0"),
        (548, "tcp", "open", "afp", "netatalk", "3.1"),
        (5900, "tcp", "open", "vnc", "Apple Remote Desktop", "3.9"),
    ],
    "printer": [
        (80, "tcp", "open", "http", "Embedded Web Server", "1.0"),
        (443, "tcp", "open", "https", "Embedded Web Server", "1.0"),
        (515, "tcp", "open", "printer", "LPD", None),
        (631, "tcp", "open", "ipp", "CUPS", "2.4"),
        (9100, "tcp", "open", "jetdirect", "HP JetDirect", None),
    ],
    "iot": [
        (80, "tcp", "open", "http", "micro_httpd", None),
        (554, "tcp", "open", "rtsp", "RTSP Server", "1.0"),
        (8000, "tcp", "open", "http-alt", "Hikvision Web", "4.0"),
    ],
    "iot_sensor": [
        (80, "tcp", "open", "http", "Embedded", "1.0"),
        (502, "tcp", "open", "modbus", "Modbus TCP", None),
    ],
}

# Mapping hostname → specific port profile override
PORT_PROFILE_OVERRIDES = {
    "web-01": "server_web", "web-02": "server_web", "web-03": "server_web",
    "edge-web-01": "server_web", "edge-web-02": "server_web",
    "app-01": "server_app", "app-02": "server_app",
    "db-01": "server_db", "db-02": "server_db",
    "dns-01": "server_dns", "ad-dc-01": "server_dns",
    "monitor-01": "server_monitor",
    "ws-mjones": "workstation_mac", "ws-kwilson": "workstation_mac", "ws-dpatel": "workstation_mac",
    "sensor-hvac-1": "iot_sensor", "sensor-hvac-2": "iot_sensor",
}

# ── Public IPs for internet connections ──────────────────────────────

PUBLIC_DESTINATIONS = [
    ("8.8.8.8",          443, "dns.google"),
    ("8.8.4.4",          443, "dns.google"),
    ("1.1.1.1",          443, "one.one.one.one"),
    ("13.107.42.14",     443, "outlook.office365.com"),
    ("20.190.151.68",    443, "login.microsoftonline.com"),
    ("52.96.166.130",    443, "smtp.office365.com"),
    ("140.82.114.4",     443, "github.com"),
    ("151.101.1.140",    443, "pypi.org"),
    ("104.18.12.33",     443, "registry.npmjs.org"),
    ("35.186.224.47",    443, "gcr.io"),
    ("52.217.163.69",    443, "s3.amazonaws.com"),
    ("104.16.132.229",   443, "api.cloudflare.com"),
    ("142.250.80.46",    443, "www.google.com"),
    ("157.240.22.35",    443, "www.facebook.com"),
    ("93.184.216.34",    80,  "www.example.com"),
    ("44.231.252.100",   443, "grafana.com"),
    ("185.199.108.133",  443, "raw.githubusercontent.com"),
    ("34.149.100.209",   443, "prometheus.io"),
    ("172.67.75.166",    443, "cve.mitre.org"),
    ("151.101.193.69",   443, "registry.terraform.io"),
]


# ══════════════════════════════════════════════════════════════════════
# Seed implementation
# ══════════════════════════════════════════════════════════════════════

def now_offset(hours=0, minutes=0):
    """Return a datetime string offset from now."""
    dt = datetime.utcnow() - timedelta(hours=hours, minutes=minutes)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def seed_database(db_path, append=False):
    """Populate the database with demo data."""
    print(f"🌱 Seeding demo data into: {db_path}")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    if not append:
        print("   Clearing existing data...")
        for table in [
            "route_hops", "conflicts", "ports", "connections",
            "arp_entries", "raw_imports", "vlan_configs", "hosts",
        ]:
            try:
                cursor.execute(f"DELETE FROM {table}")
            except sqlite3.OperationalError:
                pass  # Table may not exist yet

    # ── 1. VLAN Configs ──────────────────────────────────────────
    print("   Creating VLAN configs...")
    now = now_offset()
    for vc in VLAN_CONFIGS:
        cursor.execute("""
            INSERT INTO vlan_configs (vlan_id, vlan_name, description, subnet_cidrs, color, is_management, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (vc["vlan_id"], vc["vlan_name"], vc["description"],
              vc["subnet_cidrs"], vc["color"], vc["is_management"], now, now))
    print(f"   ✓ {len(VLAN_CONFIGS)} VLANs")

    # ── 2. Hosts ─────────────────────────────────────────────────
    print("   Creating hosts...")
    host_id_map = {}  # ip → row_id
    host_count = 0

    for vlan_id, host_list in HOSTS.items():
        vlan_name = next(v["vlan_name"] for v in VLAN_CONFIGS if v["vlan_id"] == vlan_id)
        for ip, hostname, mac, device_type, os_name, os_version, os_family, vendor in host_list:
            guid = str(uuid.uuid4())
            last_seen_h = randint(0, 48)
            first_seen_h = last_seen_h + randint(24, 720)
            criticality = "high" if device_type in ("firewall", "router") else \
                          "medium" if device_type in ("server", "switch") else "low"
            source_types = '["nmap", "arp", "netstat"]'
            cursor.execute("""
                INSERT INTO hosts (
                    guid, ip_address, hostname, mac_address, device_type, vendor,
                    os_name, os_version, os_family, os_confidence,
                    vlan_id, vlan_name, criticality,
                    is_active, is_verified, source_types,
                    first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                guid, ip, hostname, mac, device_type, vendor,
                os_name, os_version, os_family, randint(75, 100),
                vlan_id, vlan_name, criticality,
                True, True, source_types,
                now_offset(hours=first_seen_h), now_offset(hours=last_seen_h),
            ))
            host_id_map[ip] = cursor.lastrowid
            host_count += 1

    print(f"   ✓ {host_count} hosts across {len(HOSTS)} VLANs")

    # ── 3. Ports (nmap-style scan data) ──────────────────────────
    print("   Creating ports...")
    port_count = 0

    for vlan_id, host_list in HOSTS.items():
        for ip, hostname, mac, device_type, *_ in host_list:
            host_id = host_id_map.get(ip)
            if not host_id:
                continue

            # Determine port profile
            profile_key = PORT_PROFILE_OVERRIDES.get(hostname, device_type)
            ports = PORT_PROFILES.get(profile_key, PORT_PROFILES.get(device_type, []))

            for port_num, protocol, state, svc_name, svc_product, svc_version in ports:
                cursor.execute("""
                    INSERT INTO ports (
                        host_id, port_number, protocol, state,
                        service_name, product, version, confidence,
                        source_types, first_seen, last_seen
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    host_id, port_num, protocol, state,
                    svc_name, svc_product, svc_version, randint(80, 100),
                    '["nmap"]', now_offset(hours=randint(1, 72)), now_offset(hours=randint(0, 2)),
                ))
                port_count += 1

    print(f"   ✓ {port_count} ports")

    # ── 4. ARP Entries ───────────────────────────────────────────
    print("   Creating ARP entries...")
    arp_count = 0

    for vlan_id, host_list in HOSTS.items():
        # Determine the interface name based on VLAN
        iface = f"vlan{vlan_id}"
        for ip, hostname, mac, device_type, *rest in host_list:
            vendor = rest[4] if len(rest) > 4 else None
            cursor.execute("""
                INSERT INTO arp_entries (
                    ip_address, mac_address, interface, entry_type,
                    vendor, is_resolved, source_type,
                    first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ip, mac, iface, "dynamic",
                vendor, "complete", "arp_table",
                now_offset(hours=randint(2, 120)), now_offset(hours=randint(0, 4)),
            ))
            arp_count += 1

    print(f"   ✓ {arp_count} ARP entries")

    # ── 5. Connections (netstat-style) ───────────────────────────
    print("   Creating connections...")
    conn_count = 0

    # 5a. Internal same-subnet connections (within each VLAN)
    for vlan_id, host_list in HOSTS.items():
        for i, (src_ip, *_) in enumerate(host_list):
            # Each host connects to 1-3 other hosts in same VLAN
            targets = [h[0] for j, h in enumerate(host_list) if j != i]
            for tgt_ip in sample(targets, min(len(targets), randint(1, 3))):
                local_port = randint(32768, 65535)
                remote_port = choice([22, 80, 443, 445, 3306, 5432, 8080])
                cursor.execute("""
                    INSERT INTO connections (
                        local_ip, local_port, remote_ip, remote_port,
                        protocol, state, process_name, source_type,
                        first_seen, last_seen
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    src_ip, local_port, tgt_ip, remote_port,
                    "tcp", "ESTABLISHED", choice(["sshd", "nginx", "httpd", "java", "python3"]),
                    "netstat", now_offset(hours=randint(0, 24)), now_offset(hours=randint(0, 2)),
                ))
                conn_count += 1

    # 5b. Cross-subnet connections (workstations → servers, servers → servers)
    cross_subnet_pairs = [
        # Workstations → Servers (file shares, web apps, DB)
        ("10.30.30.10", "10.20.20.10", 443,  "chrome"),
        ("10.30.30.10", "10.20.20.51", 445,  "explorer"),
        ("10.30.30.11", "10.20.20.10", 443,  "firefox"),
        ("10.30.30.11", "10.20.20.20", 8080, "java"),
        ("10.30.30.12", "10.20.20.11", 443,  "chrome"),
        ("10.30.30.12", "10.20.20.30", 3306, "mysql-client"),
        ("10.30.30.13", "10.20.20.12", 443,  "Safari"),
        ("10.30.30.14", "10.20.20.20", 8080, "curl"),
        ("10.30.30.15", "10.20.20.30", 5432, "psql"),
        ("10.30.30.20", "10.20.20.11", 80,   "chrome"),
        ("10.30.30.21", "10.20.20.51", 389,  "ldapsearch"),
        ("10.30.30.22", "10.20.20.40", 3000, "Safari"),
        # Workstations → Printers
        ("10.30.30.10", "10.40.40.30", 9100, "spoolsv"),
        ("10.30.30.11", "10.40.40.30", 9100, "spoolsv"),
        ("10.30.30.13", "10.40.40.31", 631,  "cupsd"),
        # Servers → Servers (app → db, monitor → everything)
        ("10.20.20.20", "10.20.20.30", 5432, "java"),
        ("10.20.20.20", "10.20.20.31", 5432, "java"),
        ("10.20.20.21", "10.20.20.30", 3306, "java"),
        ("10.20.20.10", "10.20.20.20", 8080, "nginx"),
        ("10.20.20.11", "10.20.20.21", 8080, "nginx"),
        ("10.20.20.40", "10.20.20.10", 9100, "prometheus"),
        ("10.20.20.40", "10.20.20.20", 9090, "prometheus"),
        ("10.20.20.40", "10.20.20.30", 9100, "prometheus"),
        # DMZ → Servers
        ("172.16.1.10", "10.20.20.10", 80,   "haproxy"),
        ("172.16.1.10", "10.20.20.11", 80,   "haproxy"),
        ("172.16.1.10", "10.20.20.12", 80,   "haproxy"),
        ("172.16.1.11", "10.20.20.20", 8080, "nginx"),
        ("172.16.1.12", "10.20.20.21", 8080, "nginx"),
        # Management → everything (monitoring/SNMP)
        ("10.10.10.20", "10.20.20.10", 22,   "sshd"),
        ("10.10.10.20", "10.10.10.10", 161,  "snmpd"),
        ("10.10.10.20", "10.10.10.11", 161,  "snmpd"),
    ]

    for src_ip, dst_ip, remote_port, proc in cross_subnet_pairs:
        cursor.execute("""
            INSERT INTO connections (
                local_ip, local_port, remote_ip, remote_port,
                protocol, state, process_name, source_type,
                first_seen, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            src_ip, randint(32768, 65535), dst_ip, remote_port,
            "tcp", "ESTABLISHED", proc, "netstat",
            now_offset(hours=randint(0, 48)), now_offset(hours=randint(0, 4)),
        ))
        conn_count += 1

    # 5c. Internet-bound connections (public IPs)
    internet_sources = [
        # Servers doing updates/external API calls
        "10.20.20.10", "10.20.20.11", "10.20.20.12",
        "10.20.20.20", "10.20.20.40", "10.20.20.50",
        # Workstations browsing
        "10.30.30.10", "10.30.30.11", "10.30.30.13",
        "10.30.30.14", "10.30.30.15", "10.30.30.20",
        # DMZ outbound
        "172.16.1.11", "172.16.1.30",
        # Guest
        "192.168.99.10", "192.168.99.11", "192.168.99.12",
    ]

    for src_ip in internet_sources:
        # Each host connects to 2-6 random public destinations
        for pub_ip, pub_port, pub_host in sample(PUBLIC_DESTINATIONS, randint(2, 6)):
            cursor.execute("""
                INSERT INTO connections (
                    local_ip, local_port, remote_ip, remote_port,
                    protocol, state, process_name, source_type,
                    first_seen, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                src_ip, randint(32768, 65535), pub_ip, pub_port,
                "tcp", "ESTABLISHED",
                choice(["chrome", "firefox", "curl", "python3", "apt", "yum", "wget"]),
                "netstat",
                now_offset(hours=randint(0, 12)), now_offset(hours=randint(0, 1)),
            ))
            conn_count += 1

    print(f"   ✓ {conn_count} connections (internal + cross-subnet + internet)")

    # ── 6. Route Hops (traceroute data) ──────────────────────────
    print("   Creating traceroute data...")
    route_count = 0

    traceroutes = [
        # Workstation → Google DNS (via gateway, firewall, internet)
        {
            "trace_id": str(uuid.uuid4())[:8],
            "source_host": "10.30.30.10",
            "dest_ip": "8.8.8.8",
            "hops": [
                ("10.30.30.1",  "ws-gw",       1.2, 1.1, 1.3),
                ("10.10.10.1",  "core-rtr-01",  2.5, 2.3, 2.8),
                ("10.10.10.20", "fw-01",        3.1, 3.0, 3.4),
                ("203.0.113.1", "isp-gw-01",   10.5, 10.2, 11.1),
                ("203.0.113.5", "isp-core",    15.3, 14.8, 15.9),
                ("8.8.8.8",     "dns.google",  22.1, 21.5, 23.0),
            ],
        },
        # Server → GitHub (via server gateway, core router, firewall)
        {
            "trace_id": str(uuid.uuid4())[:8],
            "source_host": "10.20.20.10",
            "dest_ip": "140.82.114.4",
            "hops": [
                ("10.20.20.1",   "srv-gw",        0.8, 0.7, 0.9),
                ("10.10.10.1",   "core-rtr-01",   1.5, 1.3, 1.8),
                ("10.10.10.20",  "fw-01",         2.1, 2.0, 2.4),
                ("203.0.113.1",  "isp-gw-01",    12.5, 11.8, 13.2),
                ("140.82.114.4", "github.com",   35.2, 34.1, 36.5),
            ],
        },
        # DMZ → S3 (via DMZ firewall, core router, internet)
        {
            "trace_id": str(uuid.uuid4())[:8],
            "source_host": "172.16.1.11",
            "dest_ip": "52.217.163.69",
            "hops": [
                ("172.16.1.1",   "dmz-fw",       0.5, 0.4, 0.6),
                ("10.10.10.1",   "core-rtr-01",  1.2, 1.1, 1.4),
                ("10.10.10.20",  "fw-01",        1.8, 1.7, 2.0),
                ("203.0.113.1",  "isp-gw-01",    8.5, 8.2, 9.1),
                ("52.217.163.69","s3.amazonaws.com", 28.3, 27.5, 29.1),
            ],
        },
        # IoT camera → Hikvision cloud (suspicious outbound)
        {
            "trace_id": str(uuid.uuid4())[:8],
            "source_host": "10.40.40.10",
            "dest_ip": "44.231.252.100",
            "hops": [
                ("10.40.40.1",    "iot-gw",      1.0, 0.9, 1.2),
                ("10.10.10.1",    "core-rtr-01", 2.0, 1.8, 2.3),
                ("10.10.10.20",   "fw-01",       2.8, 2.5, 3.1),
                ("203.0.113.1",   "isp-gw-01",  15.2, 14.5, 16.0),
                ("44.231.252.100","grafana.com", 45.5, 44.0, 47.2),
            ],
        },
    ]

    for trace in traceroutes:
        for i, (hop_ip, hostname, rtt1, rtt2, rtt3) in enumerate(trace["hops"]):
            host_id = host_id_map.get(hop_ip)
            cursor.execute("""
                INSERT INTO route_hops (
                    trace_id, hop_number, hop_ip, hostname,
                    rtt_ms_1, rtt_ms_2, rtt_ms_3,
                    source_host, dest_ip, host_id,
                    source_type, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace["trace_id"], i + 1, hop_ip, hostname,
                rtt1, rtt2, rtt3,
                trace["source_host"], trace["dest_ip"], host_id,
                "traceroute", now_offset(hours=randint(0, 6)),
            ))
            route_count += 1

    print(f"   ✓ {route_count} route hops across {len(traceroutes)} traces")

    # ── 7. Raw Imports (provenance records) ──────────────────────
    print("   Creating import records...")
    imports = [
        ("nmap", "paste", "nmap-full-scan.xml", "ws-jsmith",
         "Nmap 7.94 scan of 10.0.0.0/8 — 48 hosts up"),
        ("netstat", "paste", None, "web-01",
         "Active Internet connections on web-01 (56 entries)"),
        ("netstat", "paste", None, "app-01",
         "Active Internet connections on app-01 (34 entries)"),
        ("arp", "paste", None, "core-rtr-01",
         "ARP table dump from core-rtr-01 (52 entries)"),
        ("traceroute", "paste", None, "ws-jsmith",
         "Traceroute to 8.8.8.8 from 10.30.30.10"),
    ]

    for src_type, imp_type, filename, src_host, raw_data in imports:
        cursor.execute("""
            INSERT INTO raw_imports (
                source_type, import_type, filename, source_host,
                raw_data, parse_status, parsed_count,
                created_at, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            src_type, imp_type, filename, src_host,
            raw_data, "success", randint(10, 60),
            now_offset(hours=randint(2, 72)), now_offset(hours=randint(1, 71)),
        ))

    print(f"   ✓ {len(imports)} import records")

    # ── 8. DeviceIdentity for shared core router ────────────────────
    print("   Creating DeviceIdentity for shared core router...")
    core_router_data = {
        "name": "Core Router 01",
        "device_type": "router",
        "mac_addresses": ["00:50:56:aa:00:01"],
        "ip_addresses": ["10.20.20.1", "10.30.30.1", "10.40.40.1"],
        "source": "seed_data",
        "is_active": True,
    }

    # Determine column names for device_identities table
    cursor.execute("""
        INSERT INTO device_identities (name, device_type, mac_addresses, ip_addresses, source, is_active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        core_router_data["name"],
        core_router_data["device_type"],
        '["00:50:56:aa:00:01"]',  # JSON array format
        '["10.20.20.1", "10.30.30.1", "10.40.40.1"]',  # JSON array format
        core_router_data["source"],
        1,  # True
        now, now,
    ))
    device_identity_id = cursor.lastrowid

    # Link the three gateway hosts to this device identity
    for ip in ["10.20.20.1", "10.30.30.1", "10.40.40.1"]:
        host_id = host_id_map.get(ip)
        if host_id:
            cursor.execute("""
                UPDATE hosts SET device_id = ? WHERE id = ?
            """, (device_identity_id, host_id))

    print(f"   ✓ DeviceIdentity created with ID {device_identity_id}, linked to 3 gateway hosts")

    conn.commit()
    conn.close()

    print()
    print("✅ Demo data seeded successfully!")
    print(f"   Database: {db_path}")
    print(f"   VLANs: {len(VLAN_CONFIGS)}")
    print(f"   Hosts: {host_count}")
    print(f"   Ports: {port_count}")
    print(f"   Connections: {conn_count}")
    print(f"   ARP Entries: {arp_count}")
    print(f"   Route Hops: {route_count}")
    print()
    print("   Start the app and navigate to /map to see the topology!")


def export_backup(db_path, output_file):
    """Export the current database to a JSON backup file."""
    print(f"📦 Exporting database to: {output_file}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    backup = {"exported_at": datetime.utcnow().isoformat(), "tables": {}}

    tables = [
        "vlan_configs", "hosts", "ports", "connections",
        "arp_entries", "route_hops", "raw_imports",
    ]

    for table in tables:
        try:
            cursor.execute(f"SELECT * FROM {table}")
            rows = [dict(row) for row in cursor.fetchall()]
            backup["tables"][table] = rows
            print(f"   ✓ {table}: {len(rows)} rows")
        except sqlite3.OperationalError:
            print(f"   ⚠ {table}: table not found, skipping")

    conn.close()

    with open(output_file, "w") as f:
        json.dump(backup, f, indent=2, default=str)

    print(f"\n✅ Exported to {output_file}")


def restore_backup(db_path, input_file):
    """Restore database from a JSON backup file."""
    print(f"♻️  Restoring from: {input_file}")

    with open(input_file, "r") as f:
        backup = json.load(f)

    print(f"   Backup created at: {backup.get('exported_at', 'unknown')}")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    for table, rows in backup.get("tables", {}).items():
        if not rows:
            continue

        # Clear existing data
        try:
            cursor.execute(f"DELETE FROM {table}")
        except sqlite3.OperationalError:
            print(f"   ⚠ {table}: table not found, skipping")
            continue

        # Insert rows
        columns = list(rows[0].keys())
        placeholders = ", ".join(["?"] * len(columns))
        col_names = ", ".join(columns)

        for row in rows:
            values = [row.get(col) for col in columns]
            cursor.execute(f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})", values)

        print(f"   ✓ {table}: {len(rows)} rows restored")

    conn.commit()
    conn.close()
    print("\n✅ Restored successfully!")


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Graphēon Demo Seed Data — populate the database with example network data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/seed_demo_data.py                         # Seed fresh demo data
  python scripts/seed_demo_data.py --append                # Add demo data to existing
  python scripts/seed_demo_data.py --export                # Export DB to demo_backup.json
  python scripts/seed_demo_data.py --restore backup.json   # Restore from backup
  python scripts/seed_demo_data.py --db /path/to/network.db  # Use specific DB file
        """,
    )
    parser.add_argument(
        "--db", type=str, default=str(DEFAULT_DB),
        help=f"Path to SQLite database (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--append", action="store_true",
        help="Add data without clearing existing records",
    )
    parser.add_argument(
        "--export", action="store_true",
        help="Export current DB to JSON backup instead of seeding",
    )
    parser.add_argument(
        "--restore", type=str, metavar="FILE",
        help="Restore database from a JSON backup file",
    )
    parser.add_argument(
        "--output", type=str, default="demo_backup.json",
        help="Output filename for --export (default: demo_backup.json)",
    )

    args = parser.parse_args()
    db_path = Path(args.db)

    if args.restore:
        restore_backup(db_path, args.restore)
    elif args.export:
        export_backup(db_path, args.output)
    else:
        # Ensure DB directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        seed_database(db_path, append=args.append)


if __name__ == "__main__":
    main()
