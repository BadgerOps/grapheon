"""
MAC Vendor lookup service.

Uses the IEEE OUI database to lookup vendor information from MAC addresses.
"""

import re
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# Common MAC vendor prefixes (OUI - first 3 bytes)
# This is a subset of the IEEE OUI database for common vendors
# In production, you'd want to download the full OUI database from IEEE
MAC_VENDOR_DB: Dict[str, str] = {
    # Apple
    "00:03:93": "Apple",
    "00:05:02": "Apple",
    "00:0A:27": "Apple",
    "00:0A:95": "Apple",
    "00:0D:93": "Apple",
    "00:10:FA": "Apple",
    "00:11:24": "Apple",
    "00:14:51": "Apple",
    "00:16:CB": "Apple",
    "00:17:F2": "Apple",
    "00:19:E3": "Apple",
    "00:1B:63": "Apple",
    "00:1C:B3": "Apple",
    "00:1D:4F": "Apple",
    "00:1E:52": "Apple",
    "00:1E:C2": "Apple",
    "00:1F:5B": "Apple",
    "00:1F:F3": "Apple",
    "00:21:E9": "Apple",
    "00:22:41": "Apple",
    "00:23:12": "Apple",
    "00:23:32": "Apple",
    "00:23:6C": "Apple",
    "00:23:DF": "Apple",
    "00:24:36": "Apple",
    "00:25:00": "Apple",
    "00:25:4B": "Apple",
    "00:25:BC": "Apple",
    "00:26:08": "Apple",
    "00:26:4A": "Apple",
    "00:26:B0": "Apple",
    "00:26:BB": "Apple",
    "3C:15:C2": "Apple",
    "A4:D1:8C": "Apple",

    # Microsoft / Xbox
    "00:03:FF": "Microsoft",
    "00:0D:3A": "Microsoft",
    "00:12:5A": "Microsoft",
    "00:15:5D": "Microsoft",
    "00:17:FA": "Microsoft",
    "00:1D:D8": "Microsoft",
    "00:22:48": "Microsoft",
    "00:25:AE": "Microsoft",
    "00:50:F2": "Microsoft",
    "28:18:78": "Microsoft",
    "60:45:BD": "Microsoft",

    # Dell
    "00:06:5B": "Dell",
    "00:08:74": "Dell",
    "00:0B:DB": "Dell",
    "00:0D:56": "Dell",
    "00:0F:1F": "Dell",
    "00:11:43": "Dell",
    "00:12:3F": "Dell",
    "00:13:72": "Dell",
    "00:14:22": "Dell",
    "00:15:C5": "Dell",
    "00:16:F0": "Dell",
    "00:18:8B": "Dell",
    "00:19:B9": "Dell",
    "00:1A:A0": "Dell",
    "00:1C:23": "Dell",
    "00:1D:09": "Dell",
    "00:1E:4F": "Dell",
    "00:1E:C9": "Dell",
    "00:21:70": "Dell",
    "00:21:9B": "Dell",
    "00:22:19": "Dell",
    "00:23:AE": "Dell",
    "00:24:E8": "Dell",
    "00:25:64": "Dell",
    "00:26:B9": "Dell",
    "14:FE:B5": "Dell",
    "18:03:73": "Dell",
    "18:A9:9B": "Dell",
    "24:B6:FD": "Dell",

    # HP / Hewlett Packard
    "00:01:E6": "HP",
    "00:01:E7": "HP",
    "00:02:A5": "HP",
    "00:04:EA": "HP",
    "00:08:02": "HP",
    "00:08:83": "HP",
    "00:0A:57": "HP",
    "00:0B:CD": "HP",
    "00:0D:9D": "HP",
    "00:0E:7F": "HP",
    "00:0F:20": "HP",
    "00:0F:61": "HP",
    "00:10:83": "HP",
    "00:10:E3": "HP",
    "00:11:0A": "HP",
    "00:11:85": "HP",
    "00:12:79": "HP",
    "00:13:21": "HP",
    "00:14:38": "HP",
    "00:14:C2": "HP",
    "00:15:60": "HP",
    "00:16:35": "HP",
    "00:17:08": "HP",
    "00:17:A4": "HP",
    "00:18:71": "HP",
    "00:18:FE": "HP",
    "00:19:BB": "HP",
    "00:1A:4B": "HP",
    "00:1B:78": "HP",
    "00:1C:C4": "HP",
    "00:1E:0B": "HP",
    "00:1F:29": "HP",
    "00:21:5A": "HP",
    "00:22:64": "HP",
    "00:23:7D": "HP",
    "00:24:81": "HP",
    "00:25:B3": "HP",
    "00:26:55": "HP",
    "00:30:6E": "HP",
    "00:30:C1": "HP",
    "08:00:09": "HP",
    "10:1F:74": "HP",
    "14:02:EC": "HP",

    # Cisco
    "00:00:0C": "Cisco",
    "00:01:42": "Cisco",
    "00:01:43": "Cisco",
    "00:01:63": "Cisco",
    "00:01:64": "Cisco",
    "00:01:96": "Cisco",
    "00:01:97": "Cisco",
    "00:01:C7": "Cisco",
    "00:01:C9": "Cisco",
    "00:02:16": "Cisco",
    "00:02:17": "Cisco",
    "00:02:3D": "Cisco",
    "00:02:4A": "Cisco",
    "00:02:4B": "Cisco",
    "00:02:7D": "Cisco",
    "00:02:7E": "Cisco",
    "00:02:B9": "Cisco",
    "00:02:BA": "Cisco",
    "00:02:FC": "Cisco",
    "00:02:FD": "Cisco",
    "00:03:31": "Cisco",
    "00:03:32": "Cisco",
    "00:03:6B": "Cisco",
    "00:03:6C": "Cisco",
    "00:03:9F": "Cisco",
    "00:03:A0": "Cisco",
    "00:03:E3": "Cisco",
    "00:03:E4": "Cisco",
    "00:03:FD": "Cisco",
    "00:03:FE": "Cisco",
    "00:04:27": "Cisco",
    "00:04:28": "Cisco",
    "00:04:4D": "Cisco",
    "00:04:4E": "Cisco",
    "00:04:6D": "Cisco",
    "00:04:6E": "Cisco",
    "00:04:9A": "Cisco",
    "00:04:9B": "Cisco",
    "00:04:C0": "Cisco",
    "00:04:C1": "Cisco",
    "00:04:DD": "Cisco",
    "00:04:DE": "Cisco",

    # Intel
    "00:02:B3": "Intel",
    "00:03:47": "Intel",
    "00:04:23": "Intel",
    "00:07:E9": "Intel",
    "00:0C:F1": "Intel",
    "00:0E:0C": "Intel",
    "00:0E:35": "Intel",
    "00:11:11": "Intel",
    "00:12:F0": "Intel",
    "00:13:02": "Intel",
    "00:13:20": "Intel",
    "00:13:CE": "Intel",
    "00:13:E8": "Intel",
    "00:15:00": "Intel",
    "00:15:17": "Intel",
    "00:16:6F": "Intel",
    "00:16:76": "Intel",
    "00:16:EA": "Intel",
    "00:16:EB": "Intel",
    "00:17:35": "Intel",
    "00:17:36": "Intel",
    "00:18:DE": "Intel",
    "00:19:D1": "Intel",
    "00:19:D2": "Intel",
    "00:1B:21": "Intel",
    "00:1B:77": "Intel",
    "00:1C:BF": "Intel",
    "00:1C:C0": "Intel",
    "00:1D:E0": "Intel",
    "00:1D:E1": "Intel",
    "00:1E:64": "Intel",
    "00:1E:65": "Intel",
    "00:1E:67": "Intel",
    "00:1F:3B": "Intel",
    "00:1F:3C": "Intel",
    "00:20:E0": "Intel",
    "00:21:5C": "Intel",
    "00:21:5D": "Intel",
    "00:21:6A": "Intel",
    "00:21:6B": "Intel",
    "00:22:FA": "Intel",
    "00:22:FB": "Intel",
    "00:24:D6": "Intel",
    "00:24:D7": "Intel",
    "00:26:C6": "Intel",
    "00:26:C7": "Intel",
    "00:27:10": "Intel",

    # Samsung
    "00:00:F0": "Samsung",
    "00:02:78": "Samsung",
    "00:07:AB": "Samsung",
    "00:09:18": "Samsung",
    "00:0D:AE": "Samsung",
    "00:0D:E5": "Samsung",
    "00:12:47": "Samsung",
    "00:12:FB": "Samsung",
    "00:13:77": "Samsung",
    "00:15:99": "Samsung",
    "00:15:B9": "Samsung",
    "00:16:32": "Samsung",
    "00:16:6B": "Samsung",
    "00:16:6C": "Samsung",
    "00:16:DB": "Samsung",
    "00:17:C9": "Samsung",
    "00:17:D5": "Samsung",
    "00:18:AF": "Samsung",
    "00:1A:8A": "Samsung",
    "00:1B:98": "Samsung",
    "00:1C:43": "Samsung",
    "00:1D:25": "Samsung",
    "00:1D:F6": "Samsung",
    "00:1E:7D": "Samsung",
    "00:1E:E1": "Samsung",
    "00:1E:E2": "Samsung",
    "00:1F:CC": "Samsung",
    "00:1F:CD": "Samsung",
    "00:21:19": "Samsung",
    "00:21:4C": "Samsung",
    "00:21:D1": "Samsung",
    "00:21:D2": "Samsung",
    "00:23:39": "Samsung",
    "00:23:3A": "Samsung",
    "00:23:99": "Samsung",
    "00:23:D6": "Samsung",
    "00:23:D7": "Samsung",
    "00:24:54": "Samsung",
    "00:24:90": "Samsung",
    "00:24:91": "Samsung",
    "00:24:E9": "Samsung",
    "00:25:66": "Samsung",
    "00:25:67": "Samsung",
    "00:26:37": "Samsung",
    "00:26:5D": "Samsung",
    "00:26:5F": "Samsung",
    "54:92:BE": "Samsung",

    # VMware
    "00:0C:29": "VMware",
    "00:50:56": "VMware",
    "00:05:69": "VMware",
    "00:1C:14": "VMware",

    # Virtual / Hypervisor
    "00:16:3E": "Xen",
    "08:00:27": "VirtualBox",
    "0A:00:27": "VirtualBox",
    "52:54:00": "QEMU/KVM",

    # Raspberry Pi
    "B8:27:EB": "Raspberry Pi",
    "DC:A6:32": "Raspberry Pi",
    "E4:5F:01": "Raspberry Pi",

    # Google
    "00:1A:11": "Google",
    "3C:5A:B4": "Google",
    "94:EB:2C": "Google",
    "F4:F5:D8": "Google",
    "F4:F5:E8": "Google",

    # Amazon
    "00:FC:8B": "Amazon",
    "0C:47:C9": "Amazon",
    "18:74:2E": "Amazon",
    "34:D2:70": "Amazon",
    "40:B4:CD": "Amazon",
    "44:65:0D": "Amazon",
    "50:DC:E7": "Amazon",
    "68:37:E9": "Amazon",
    "74:75:48": "Amazon",
    "84:D6:D0": "Amazon",
    "A0:02:DC": "Amazon",
    "AC:63:BE": "Amazon",
    "B4:7C:9C": "Amazon",
    "F0:27:2D": "Amazon",
    "F0:A2:25": "Amazon",
    "FC:A1:83": "Amazon",

    # Ubiquiti
    "00:27:22": "Ubiquiti",
    "04:18:D6": "Ubiquiti",
    "18:E8:29": "Ubiquiti",
    "24:A4:3C": "Ubiquiti",
    "44:D9:E7": "Ubiquiti",
    "68:72:51": "Ubiquiti",
    "74:83:C2": "Ubiquiti",
    "78:8A:20": "Ubiquiti",
    "80:2A:A8": "Ubiquiti",
    "B4:FB:E4": "Ubiquiti",
    "DC:9F:DB": "Ubiquiti",
    "E0:63:DA": "Ubiquiti",
    "F0:9F:C2": "Ubiquiti",
    "FC:EC:DA": "Ubiquiti",

    # TP-Link
    "00:1D:0F": "TP-Link",
    "14:CC:20": "TP-Link",
    "14:CF:92": "TP-Link",
    "1C:3B:F3": "TP-Link",
    "30:B5:C2": "TP-Link",
    "50:C7:BF": "TP-Link",
    "54:C8:0F": "TP-Link",
    "64:66:B3": "TP-Link",
    "64:70:02": "TP-Link",
    "78:44:76": "TP-Link",
    "90:F6:52": "TP-Link",
    "A0:F3:C1": "TP-Link",
    "B0:4E:26": "TP-Link",
    "C0:25:E9": "TP-Link",
    "C4:6E:1F": "TP-Link",
    "D4:6E:0E": "TP-Link",
    "E8:DE:27": "TP-Link",
    "EC:08:6B": "TP-Link",
    "F4:F2:6D": "TP-Link",
    "F8:1A:67": "TP-Link",

    # Netgear
    "00:09:5B": "Netgear",
    "00:0F:B5": "Netgear",
    "00:14:6C": "Netgear",
    "00:18:4D": "Netgear",
    "00:1B:2F": "Netgear",
    "00:1E:2A": "Netgear",
    "00:1F:33": "Netgear",
    "00:22:3F": "Netgear",
    "00:24:B2": "Netgear",
    "00:26:F2": "Netgear",
    "20:4E:7F": "Netgear",
    "28:C6:8E": "Netgear",
    "30:46:9A": "Netgear",
    "44:94:FC": "Netgear",
    "6C:B0:CE": "Netgear",
    "84:1B:5E": "Netgear",
    "9C:3D:CF": "Netgear",
    "A0:21:B7": "Netgear",
    "A0:40:A0": "Netgear",
    "A4:2B:8C": "Netgear",
    "B0:7F:B9": "Netgear",
    "C0:3F:0E": "Netgear",
    "C4:04:15": "Netgear",
    "C4:3D:C7": "Netgear",
    "E0:46:9A": "Netgear",
    "E0:91:F5": "Netgear",
    "E4:F4:C6": "Netgear",

    # Linksys
    "00:04:5A": "Linksys",
    "00:06:25": "Linksys",
    "00:0C:41": "Linksys",
    "00:0F:66": "Linksys",
    "00:12:17": "Linksys",
    "00:13:10": "Linksys",
    "00:14:BF": "Linksys",
    "00:16:B6": "Linksys",
    "00:18:39": "Linksys",
    "00:18:F8": "Linksys",
    "00:1A:70": "Linksys",
    "00:1C:10": "Linksys",
    "00:1D:7E": "Linksys",
    "00:1E:E5": "Linksys",
    "00:21:29": "Linksys",
    "00:22:6B": "Linksys",
    "00:23:69": "Linksys",
    "00:25:9C": "Linksys",

    # Juniper
    "00:05:85": "Juniper",
    "00:10:DB": "Juniper",
    "00:12:1E": "Juniper",
    "00:14:F6": "Juniper",
    "00:17:CB": "Juniper",
    "00:19:E2": "Juniper",
    "00:1D:B5": "Juniper",
    "00:21:59": "Juniper",
    "00:22:83": "Juniper",
    "00:23:9C": "Juniper",
    "00:24:DC": "Juniper",
    "00:26:88": "Juniper",
    "28:8A:1C": "Juniper",
    "28:C0:DA": "Juniper",
    "2C:21:31": "Juniper",
    "2C:21:72": "Juniper",
    "2C:6B:F5": "Juniper",
    "30:7C:5E": "Juniper",
    "3C:61:04": "Juniper",
    "3C:8A:B0": "Juniper",
    "40:71:83": "Juniper",
    "40:A6:77": "Juniper",
    "40:B4:F0": "Juniper",

    # Arista
    "00:1C:73": "Arista",
    "28:99:3A": "Arista",
    "44:4C:A8": "Arista",

    # D-Link
    "00:05:5D": "D-Link",
    "00:0D:88": "D-Link",
    "00:0F:3D": "D-Link",
    "00:11:95": "D-Link",
    "00:13:46": "D-Link",
    "00:15:E9": "D-Link",
    "00:17:9A": "D-Link",
    "00:19:5B": "D-Link",
    "00:1B:11": "D-Link",
    "00:1C:F0": "D-Link",
    "00:1E:58": "D-Link",
    "00:1F:E0": "D-Link",
    "00:21:91": "D-Link",
    "00:22:B0": "D-Link",
    "00:24:01": "D-Link",
    "00:26:5A": "D-Link",
    "14:D6:4D": "D-Link",
    "1C:7E:E5": "D-Link",
    "28:10:7B": "D-Link",
    "34:08:04": "D-Link",
    "5C:D9:98": "D-Link",
    "78:54:2E": "D-Link",
    "84:C9:B2": "D-Link",
    "90:94:E4": "D-Link",
    "9C:D6:43": "D-Link",
    "B8:A3:86": "D-Link",
    "BC:F6:85": "D-Link",
    "C8:BE:19": "D-Link",
    "C8:D3:A3": "D-Link",
    "CC:B2:55": "D-Link",
    "F0:7D:68": "D-Link",

    # ASUS
    "00:0C:6E": "ASUS",
    "00:0E:A6": "ASUS",
    "00:11:2F": "ASUS",
    "00:13:D4": "ASUS",
    "00:15:F2": "ASUS",
    "00:17:31": "ASUS",
    "00:18:F3": "ASUS",
    "00:1A:92": "ASUS",
    "00:1B:FC": "ASUS",
    "00:1D:60": "ASUS",
    "00:1E:8C": "ASUS",
    "00:1F:C6": "ASUS",
    "00:22:15": "ASUS",
    "00:23:54": "ASUS",
    "00:24:8C": "ASUS",
    "00:25:22": "ASUS",
    "00:26:18": "ASUS",
    "08:60:6E": "ASUS",
    "10:BF:48": "ASUS",
    "14:DA:E9": "ASUS",
    "1C:87:2C": "ASUS",
    "1C:B7:2C": "ASUS",
    "20:CF:30": "ASUS",
    "2C:4D:54": "ASUS",
    "2C:56:DC": "ASUS",
    "30:5A:3A": "ASUS",
    "30:85:A9": "ASUS",
    "38:D5:47": "ASUS",
    "3C:97:0E": "ASUS",
    "40:16:7E": "ASUS",
    "48:5B:39": "ASUS",
    "4C:ED:FB": "ASUS",
    "50:46:5D": "ASUS",
    "54:04:A6": "ASUS",
    "54:A0:50": "ASUS",
    "60:45:CB": "ASUS",
    "74:D0:2B": "ASUS",

    # Synology
    "00:11:32": "Synology",
}


class MacVendorLookup:
    """Service for looking up MAC address vendors."""

    def __init__(self, custom_db: Optional[Dict[str, str]] = None):
        """
        Initialize the MAC vendor lookup service.

        Args:
            custom_db: Optional custom vendor database to merge with built-in
        """
        self.vendor_db = MAC_VENDOR_DB.copy()
        if custom_db:
            self.vendor_db.update(custom_db)

    def normalize_mac(self, mac: str) -> Optional[str]:
        """
        Normalize MAC address to consistent format (XX:XX:XX:XX:XX:XX).

        Args:
            mac: MAC address in any common format

        Returns:
            Normalized MAC address or None if invalid
        """
        if not mac:
            return None

        # Remove common separators and convert to uppercase
        mac_clean = re.sub(r'[:\-\.]', '', mac.upper())

        # Validate length
        if len(mac_clean) != 12:
            return None

        # Validate hex characters
        if not re.match(r'^[0-9A-F]{12}$', mac_clean):
            return None

        # Format as XX:XX:XX:XX:XX:XX
        return ':'.join(mac_clean[i:i+2] for i in range(0, 12, 2))

    def get_oui(self, mac: str) -> Optional[str]:
        """
        Extract OUI (first 3 bytes) from MAC address.

        Args:
            mac: MAC address in any format

        Returns:
            OUI in XX:XX:XX format or None if invalid
        """
        normalized = self.normalize_mac(mac)
        if not normalized:
            return None

        return normalized[:8]

    def lookup(self, mac: str) -> Optional[str]:
        """
        Lookup vendor for a MAC address.

        Args:
            mac: MAC address in any format

        Returns:
            Vendor name or None if not found
        """
        oui = self.get_oui(mac)
        if not oui:
            return None

        return self.vendor_db.get(oui)

    def lookup_batch(self, macs: list) -> Dict[str, Optional[str]]:
        """
        Lookup vendors for multiple MAC addresses.

        Args:
            macs: List of MAC addresses

        Returns:
            Dictionary mapping MAC addresses to vendor names
        """
        return {mac: self.lookup(mac) for mac in macs}


# Global instance
_vendor_lookup: Optional[MacVendorLookup] = None


def get_vendor_lookup() -> MacVendorLookup:
    """Get or create the global vendor lookup instance."""
    global _vendor_lookup
    if _vendor_lookup is None:
        _vendor_lookup = MacVendorLookup()
    return _vendor_lookup


def lookup_mac_vendor(mac: str) -> Optional[str]:
    """
    Convenience function to lookup a MAC vendor.

    Args:
        mac: MAC address in any format

    Returns:
        Vendor name or None if not found
    """
    return get_vendor_lookup().lookup(mac)
