"""
Shared constants for network map visualization.
"""
from ipaddress import ip_network

# ── Node IDs ─────────────────────────────────────────────────────
PUBLIC_IPS_NODE_ID = "public_ips"
INTERNET_NODE_ID = "internet_cloud"

# ── Compound node types (not counted as hosts) ───────────────────
COMPOUND_NODE_TYPES = ("vlan", "subnet", "internet", "public_ips")

# ── Defaults ─────────────────────────────────────────────────────
DEFAULT_SUBNET_PREFIX = 24
DEFAULT_RESPONSE_FORMAT = "cytoscape"
DEFAULT_INTERNET_MODE = "cloud"
DEFAULT_GROUP_BY = "subnet"
DEFAULT_LAYOUT_MODE = "grouped"

# ── Node sizing ──────────────────────────────────────────────────
DEFAULT_NODE_SIZE = 30
MAX_NODE_SIZE_INCREMENT = 15  # Cap on port-count bonus to node size

# ── Gateway ──────────────────────────────────────────────────────
DEFAULT_GATEWAY_IP_OFFSET = 1  # .1 address assumed as gateway

# ── Colors ───────────────────────────────────────────────────────
INTERNET_NODE_COLOR = "#0ea5e9"
ROUTER_COLOR = "#f97316"

# ── Device type styling ──────────────────────────────────────────
DEVICE_STYLES = {
    "router":      {"color": "#f97316", "shape": "diamond",   "size": 50},
    "switch":      {"color": "#8b5cf6", "shape": "triangle",  "size": 45},
    "firewall":    {"color": "#ef4444", "shape": "star",      "size": 45},
    "server":      {"color": "#3b82f6", "shape": "rectangle", "size": 40},
    "workstation": {"color": "#22c55e", "shape": "ellipse",   "size": 35},
    "printer":     {"color": "#ec4899", "shape": "rectangle", "size": 35},
    "iot":         {"color": "#06b6d4", "shape": "hexagon",   "size": 35},
}

DEFAULT_STYLE = {"color": "#6b7280", "shape": "ellipse", "size": DEFAULT_NODE_SIZE}

# ── Color palettes ───────────────────────────────────────────────
VLAN_COLORS = [
    "#3b82f6", "#22c55e", "#f97316", "#8b5cf6",
    "#ec4899", "#06b6d4", "#eab308", "#ef4444",
    "#14b8a6", "#f43f5e",
]

SUBNET_COLORS = [
    "#60a5fa", "#4ade80", "#fb923c", "#a78bfa",
    "#f472b6", "#22d3ee", "#facc15", "#f87171",
]

# ── Private / non-routable IP ranges ─────────────────────────────
PRIVATE_NETWORKS = [
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("127.0.0.0/8"),       # Loopback
    ip_network("169.254.0.0/16"),     # Link-local
    ip_network("100.64.0.0/10"),      # CGNAT / Shared address space
    ip_network("fc00::/7"),           # IPv6 ULA
    ip_network("fe80::/10"),          # IPv6 link-local
    ip_network("::1/128"),            # IPv6 loopback
]

# ── Internet routing tooltip ─────────────────────────────────────
MAX_PUBLIC_IP_SAMPLES = 5  # Max IPs shown in gateway→Internet tooltip
