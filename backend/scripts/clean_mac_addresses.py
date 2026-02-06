#!/usr/bin/env python3
"""
MAC Address Cleaning Migration Script

Cleans MAC addresses in the network database:
1. Removes [ether] and other [...] suffixes
2. Normalizes to lowercase colon-separated format (00:0e:c6:c7:10:90)
3. Detects gateway/router by finding MACs appearing as .1 in 2+ subnets
4. Updates device_type and vendor accordingly
5. Performs vendor lookups for hosts with cleaned MACs
"""

import sqlite3
import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Optional, Dict, Set, Tuple

# Import the MAC vendor lookup service directly
services_path = Path(__file__).parent.parent / "services"
sys.path.insert(0, str(services_path))
from mac_vendor import MacVendorLookup


class MACAddressCleaningMigration:
    """Migration for cleaning MAC addresses in the network database."""

    def __init__(self, db_path: Path):
        """Initialize the migration with database path."""
        self.db_path = db_path
        self.conn = None
        self.vendor_lookup = MacVendorLookup()

        # Track changes for summary
        self.stats = {
            'hosts_mac_cleaned': 0,
            'arp_entries_mac_cleaned': 0,
            'routers_detected': 0,
            'vendor_lookups_performed': 0,
            'vendor_lookups_found': 0,
        }

    def connect(self) -> None:
        """Connect to SQLite database."""
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found at {self.db_path}")

        try:
            self.conn = sqlite3.connect(str(self.db_path), timeout=30)
            self.conn.row_factory = sqlite3.Row
            # Test connection
            self.conn.execute("SELECT 1")
        except sqlite3.OperationalError as e:
            raise RuntimeError(f"Failed to connect to database: {e}")

    def disconnect(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def clean_mac_address(self, mac: Optional[str]) -> Optional[str]:
        """
        Clean and normalize MAC address.

        Removes [ether] and other [...] suffixes, converts to lowercase
        colon-separated format (00:0e:c6:c7:10:90).

        Args:
            mac: Raw MAC address string

        Returns:
            Cleaned MAC address or None if invalid
        """
        if not mac:
            return None

        # Remove [ether] and other [...] suffixes
        mac_clean = re.sub(r'\s*\[.*?\]\s*$', '', mac.strip())

        # Remove common separators and validate
        mac_hex = re.sub(r'[:\-\.\s]', '', mac_clean.upper())

        # Validate: must be 12 hex characters
        if len(mac_hex) != 12 or not re.match(r'^[0-9A-F]{12}$', mac_hex):
            return None

        # Convert to lowercase colon-separated format
        return ':'.join(mac_hex[i:i+2].lower() for i in range(0, 12, 2))

    def extract_subnet(self, ip: str) -> Optional[str]:
        """
        Extract /24 subnet from IP address.

        Args:
            ip: IP address string

        Returns:
            Subnet in x.x.x format or None if invalid
        """
        try:
            parts = ip.split('.')
            if len(parts) == 4 and all(p.isdigit() for p in parts):
                return f"{parts[0]}.{parts[1]}.{parts[2]}"
        except Exception:
            pass
        return None

    def detect_routers(self) -> Dict[str, str]:
        """
        Detect gateway/router by finding MAC that appears as .1 in 2+ subnets.

        Returns:
            Dictionary mapping MAC addresses to 'router'
        """
        cursor = self.conn.cursor()

        # Get all ARP entries
        cursor.execute("SELECT ip_address, mac_address FROM arp_entries WHERE mac_address IS NOT NULL")
        rows = cursor.fetchall()

        # Map subnets to MACs of .1 addresses
        gateway_macs: Dict[str, Set[str]] = defaultdict(set)

        for ip, mac in rows:
            try:
                parts = ip.split('.')
                if len(parts) == 4 and parts[-1] == '1':  # x.x.x.1
                    subnet = self.extract_subnet(ip)
                    if subnet:
                        gateway_macs[mac].add(subnet)
            except Exception:
                pass

        # Find MACs that appear as .1 in 2+ subnets
        routers = {}
        for mac, subnets in gateway_macs.items():
            if len(subnets) >= 2 and mac:
                routers[mac] = 'router'
                print(f"  Router detected: {mac} appears as .1 in subnets: {', '.join(sorted(subnets))}")

        return routers

    def clean_hosts_table(self) -> None:
        """Clean MAC addresses in hosts table."""
        print("Cleaning MAC addresses in hosts table...")
        cursor = self.conn.cursor()

        # Get all hosts with MAC addresses
        cursor.execute("SELECT id, mac_address FROM hosts WHERE mac_address IS NOT NULL")
        rows = cursor.fetchall()

        updates = []
        for row in rows:
            host_id = row[0]
            old_mac = row[1]
            new_mac = self.clean_mac_address(old_mac)

            if new_mac and new_mac != old_mac:
                updates.append((new_mac, host_id))
                self.stats['hosts_mac_cleaned'] += 1

        # Apply updates
        for new_mac, host_id in updates:
            cursor.execute("UPDATE hosts SET mac_address = ? WHERE id = ?", (new_mac, host_id))

        self.conn.commit()
        print(f"  Cleaned {self.stats['hosts_mac_cleaned']} MAC addresses in hosts table")

    def clean_arp_entries_table(self) -> None:
        """Clean MAC addresses in arp_entries table."""
        print("Cleaning MAC addresses in arp_entries table...")
        cursor = self.conn.cursor()

        # Get all ARP entries with MAC addresses
        cursor.execute("SELECT id, mac_address FROM arp_entries WHERE mac_address IS NOT NULL")
        rows = cursor.fetchall()

        updates = []
        for row in rows:
            entry_id = row[0]
            old_mac = row[1]
            new_mac = self.clean_mac_address(old_mac)

            if new_mac and new_mac != old_mac:
                updates.append((new_mac, entry_id))
                self.stats['arp_entries_mac_cleaned'] += 1

        # Apply updates
        for new_mac, entry_id in updates:
            cursor.execute("UPDATE arp_entries SET mac_address = ? WHERE id = ?", (new_mac, entry_id))

        self.conn.commit()
        print(f"  Cleaned {self.stats['arp_entries_mac_cleaned']} MAC addresses in arp_entries table")

    def update_routers(self) -> None:
        """Detect routers and update device_type and vendor."""
        print("Detecting routers...")
        routers = self.detect_routers()

        if not routers:
            print("  No routers detected")
            return

        cursor = self.conn.cursor()

        for mac, device_type in routers.items():
            # Look up vendor for this MAC
            vendor = self.vendor_lookup.lookup(mac)

            # If no vendor found, try to guess from OUI
            if not vendor:
                # Check if it matches Ubiquiti prefix (78:45:58)
                if mac.startswith('78:45:58'):
                    vendor = 'Ubiquiti'

            # Update all hosts with this MAC
            if vendor:
                cursor.execute(
                    "UPDATE hosts SET device_type = ?, vendor = ? WHERE mac_address = ?",
                    (device_type, vendor, mac)
                )
            else:
                cursor.execute(
                    "UPDATE hosts SET device_type = ? WHERE mac_address = ?",
                    (device_type, mac)
                )

            self.stats['routers_detected'] += 1

        self.conn.commit()
        print(f"  Updated {self.stats['routers_detected']} router(s)")

    def perform_vendor_lookups(self) -> None:
        """Perform vendor lookups for hosts with cleaned MACs and no vendor."""
        print("Performing vendor lookups...")
        cursor = self.conn.cursor()

        # Get all hosts with MAC but no vendor
        cursor.execute(
            "SELECT id, mac_address FROM hosts WHERE mac_address IS NOT NULL AND (vendor IS NULL OR vendor = '')"
        )
        rows = cursor.fetchall()

        updates = []
        for row in rows:
            host_id = row[0]
            mac = row[1]

            # Perform lookup
            vendor = self.vendor_lookup.lookup(mac)
            self.stats['vendor_lookups_performed'] += 1

            if vendor:
                updates.append((vendor, host_id))
                self.stats['vendor_lookups_found'] += 1

        # Apply updates
        for vendor, host_id in updates:
            cursor.execute("UPDATE hosts SET vendor = ? WHERE id = ?", (vendor, host_id))

        self.conn.commit()
        print(f"  Performed {self.stats['vendor_lookups_performed']} vendor lookups ({self.stats['vendor_lookups_found']} found)")

    def print_summary(self) -> None:
        """Print migration summary."""
        print("\n" + "="*60)
        print("MIGRATION SUMMARY")
        print("="*60)
        print(f"Hosts MAC addresses cleaned:     {self.stats['hosts_mac_cleaned']}")
        print(f"ARP entries MAC addresses cleaned: {self.stats['arp_entries_mac_cleaned']}")
        print(f"Routers detected:                 {self.stats['routers_detected']}")
        print(f"Vendor lookups performed:         {self.stats['vendor_lookups_performed']}")
        print(f"Vendor lookups found:             {self.stats['vendor_lookups_found']}")
        print("="*60)

    def run(self) -> None:
        """Execute the migration."""
        try:
            print(f"Connecting to database: {self.db_path}")
            self.connect()

            print("\nStarting MAC address cleaning migration...")
            self.clean_hosts_table()
            self.clean_arp_entries_table()
            self.update_routers()
            self.perform_vendor_lookups()

            self.print_summary()
            print("\nMigration completed successfully!")

        except Exception as e:
            print(f"\nERROR: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            self.disconnect()


def main():
    """Main entry point."""
    # Determine database path
    script_dir = Path(__file__).parent
    backend_dir = script_dir.parent
    db_path = backend_dir / "data" / "network.db"

    # Allow override via environment variable or argument
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])

    migration = MACAddressCleaningMigration(db_path)
    migration.run()


if __name__ == "__main__":
    main()
