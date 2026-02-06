"""
MAC Vendor lookup service.

Uses the IEEE OUI database (downloaded by mac-vendor-lookup) to resolve
vendor information from MAC addresses.  The vendor file is read directly
to avoid the package's async-incompatible sync API that crashes inside
uvicorn's event loop.
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Locally-administered MAC detection
# ---------------------------------------------------------------------------
# The second hex character of a MAC address encodes two flag bits:
#   bit 0 (LSB of first octet) = multicast (1) / unicast (0)
#   bit 1                      = locally administered (1) / universally administered (0)
# If bit 1 is set the OUI was NOT assigned by IEEE and cannot be looked up.
# Second hex digits where bit 1 is set: 2, 3, 6, 7, A, B, E, F

_LOCAL_ADMIN_SECOND_CHARS = set("2367abefABEF")


def is_locally_administered(mac: str) -> bool:
    """Return True if the MAC is locally administered (random / not IEEE-assigned)."""
    clean = re.sub(r"[:\-.]", "", mac)
    if len(clean) < 2:
        return False
    return clean[1] in _LOCAL_ADMIN_SECOND_CHARS


# ---------------------------------------------------------------------------
# Load the IEEE OUI vendor file
# ---------------------------------------------------------------------------
# The mac-vendor-lookup package downloads a plain-text vendor list to its
# cache directory.  Format: one line per entry, "HEXPREFIX:Vendor Name".
# We read this file directly at import time (no asyncio needed).

def _find_vendor_file() -> Optional[str]:
    """Locate the mac-vendors.txt file in common cache locations."""
    candidates = []

    # 1. Check where mac-vendor-lookup would put it
    try:
        import mac_vendor_lookup
        pkg_dir = os.path.dirname(os.path.abspath(mac_vendor_lookup.__file__))
        # The package stores it relative to sys.prefix or in a cache dir
        candidates.append(os.path.join(os.path.dirname(pkg_dir), "cache", "mac-vendors.txt"))
    except ImportError:
        pass

    # 2. Common venv/system paths
    import sys
    candidates.extend([
        os.path.join(sys.prefix, "cache", "mac-vendors.txt"),
        os.path.join(os.path.expanduser("~"), ".cache", "mac-vendors.txt"),
        # Project-local fallback
        os.path.join(os.path.dirname(__file__), "..", "data", "mac-vendors.txt"),
    ])

    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _load_vendor_db() -> Dict[str, str]:
    """Load the OUI→vendor mapping from the vendor file."""
    db: Dict[str, str] = {}
    vendor_file = _find_vendor_file()

    if not vendor_file:
        logger.warning(
            "IEEE OUI vendor file not found. Run: "
            "python -c \"from mac_vendor_lookup import MacLookup; MacLookup().update_vendors()\" "
            "to download it.  Falling back to built-in subset."
        )
        return db

    try:
        with open(vendor_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or ":" not in line:
                    continue
                # Format: "00E04C:REALTEK SEMICONDUCTOR CORP."
                prefix, _, vendor = line.partition(":")
                prefix = prefix.strip().upper()
                vendor = vendor.strip()
                if prefix and vendor:
                    db[prefix] = vendor
        logger.info(f"Loaded {len(db)} OUI entries from {vendor_file}")
    except Exception as e:
        logger.error(f"Failed to read vendor file {vendor_file}: {e}")

    return db


# Build the lookup table once at import time
_OUI_DB: Dict[str, str] = _load_vendor_db()

# Minimal fallback for the most common vendors if the file is missing
_FALLBACK_DB: Dict[str, str] = {
    "000C29": "VMware",
    "005056": "VMware",
    "000569": "VMware",
    "00163E": "Xen",
    "080027": "VirtualBox",
    "525400": "QEMU/KVM",
    "B827EB": "Raspberry Pi",
    "DCA632": "Raspberry Pi",
    "E45F01": "Raspberry Pi",
}


# ---------------------------------------------------------------------------
# Public lookup class
# ---------------------------------------------------------------------------
class MacVendorLookup:
    """Service for looking up MAC address vendors."""

    def normalize_mac(self, mac: str) -> Optional[str]:
        """Normalize MAC address to XX:XX:XX:XX:XX:XX."""
        if not mac:
            return None
        mac_clean = re.sub(r"[:\-.]", "", mac.upper())
        if len(mac_clean) != 12 or not re.match(r"^[0-9A-F]{12}$", mac_clean):
            return None
        return ":".join(mac_clean[i : i + 2] for i in range(0, 12, 2))

    def get_oui(self, mac: str) -> Optional[str]:
        """Extract OUI (first 3 bytes) in XX:XX:XX format."""
        normalized = self.normalize_mac(mac)
        return normalized[:8] if normalized else None

    def lookup(self, mac: str) -> Optional[str]:
        """
        Lookup vendor for a MAC address.

        Returns:
            Vendor name, "Locally Administered" for random MACs, or None.
        """
        normalized = self.normalize_mac(mac)
        if not normalized:
            return None

        if is_locally_administered(normalized):
            return "Locally Administered"

        # OUI prefix without colons (e.g. "00E04C")
        oui_hex = normalized[:8].replace(":", "")

        # Try the full IEEE database first, then fallback
        vendor = _OUI_DB.get(oui_hex) or _FALLBACK_DB.get(oui_hex)
        return vendor

    def lookup_batch(self, macs: list) -> Dict[str, Optional[str]]:
        """Lookup vendors for multiple MAC addresses."""
        return {mac: self.lookup(mac) for mac in macs}


# ---------------------------------------------------------------------------
# Module-level convenience API (unchanged interface)
# ---------------------------------------------------------------------------
_vendor_lookup: Optional[MacVendorLookup] = None


def get_vendor_lookup() -> MacVendorLookup:
    """Get or create the global vendor lookup instance."""
    global _vendor_lookup
    if _vendor_lookup is None:
        _vendor_lookup = MacVendorLookup()
    return _vendor_lookup


def lookup_mac_vendor(mac: str) -> Optional[str]:
    """Convenience function to lookup a MAC vendor."""
    return get_vendor_lookup().lookup(mac)
