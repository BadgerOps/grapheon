"""
GraphML exporter for Cytoscape.js network topology data.

Converts the Cytoscape.js JSON elements (nodes + edges) returned by
``/api/network/map`` into a standard GraphML XML document that can be
imported into Gephi, yEd, Cytoscape Desktop, and other graph tools.

Features
--------
* Preserves compound‑node hierarchy (VLAN → Subnet → Host) via nested
  ``<graph>`` elements inside parent nodes.
* Maps all node metadata (IP, hostname, device type, VLAN, OS, …) and
  edge metadata (connection type, label) to GraphML ``<data>`` keys.
* Includes visual hints (color, shape, size) as GraphML attributes so
  tools like yEd can render a styled graph on import.

Usage
-----
::

    xml_string = cytoscape_to_graphml(elements)
    # elements = {"nodes": [...], "edges": [...]}

"""

import io
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Any


# ── GraphML key definitions ──────────────────────────────────────────

# Node attribute keys (id, attr.name, attr.type, default)
_NODE_KEYS = [
    ("d_label",       "label",           "string",  ""),
    ("d_type",        "type",            "string",  "host"),
    ("d_ip",          "ip",              "string",  ""),
    ("d_hostname",    "hostname",        "string",  ""),
    ("d_mac",         "mac",             "string",  ""),
    ("d_os",          "os",              "string",  ""),
    ("d_device_type", "device_type",     "string",  "unknown"),
    ("d_vendor",      "vendor",          "string",  ""),
    ("d_vlan_id",     "vlan_id",         "string",  ""),
    ("d_vlan_name",   "vlan_name",       "string",  ""),
    ("d_subnet",      "subnet",          "string",  ""),
    ("d_open_ports",  "open_ports",      "int",     "0"),
    ("d_color",       "color",           "string",  "#6b7280"),
    ("d_shape",       "shape",           "string",  "ellipse"),
    ("d_is_gateway",  "is_gateway",      "boolean", "false"),
    ("d_parent",      "parent",          "string",  ""),
]

# Edge attribute keys
_EDGE_KEYS = [
    ("d_conn_type",  "connection_type", "string", ""),
    ("d_label",      "label",          "string", ""),
    ("d_edge_color", "color",          "string", "#9ca3af"),
]

# Cytoscape data field → GraphML key ID mapping for nodes
_NODE_FIELD_MAP = {
    "label":           "d_label",
    "type":            "d_type",
    "ip":              "d_ip",
    "hostname":        "d_hostname",
    "mac":             "d_mac",
    "os":              "d_os",
    "device_type":     "d_device_type",
    "vendor":          "d_vendor",
    "vlan_id":         "d_vlan_id",
    "vlan_name":       "d_vlan_name",
    "subnet":          "d_subnet",
    "open_ports":      "d_open_ports",
    "color":           "d_color",
    "shape":           "d_shape",
    "is_gateway":      "d_is_gateway",
    "parent":          "d_parent",
}

# Cytoscape data field → GraphML key ID mapping for edges
_EDGE_FIELD_MAP = {
    "connection_type": "d_conn_type",
    "label":           "d_label",
    "color":           "d_edge_color",
}


def cytoscape_to_graphml(elements: dict[str, list[dict[str, Any]]]) -> str:
    """Convert Cytoscape.js ``elements`` dict to a GraphML XML string.

    Parameters
    ----------
    elements : dict
        ``{"nodes": [...], "edges": [...]}`` as returned by the
        ``/api/network/map`` endpoint.

    Returns
    -------
    str
        UTF-8 encoded GraphML XML document.
    """
    ns = "http://graphml.graphdrawing.org/xmlns"
    ET.register_namespace("", ns)

    root = ET.Element("graphml", xmlns=ns)

    # ── Declare attribute keys ───────────────────────────────────────
    for key_id, attr_name, attr_type, default in _NODE_KEYS:
        key_el = ET.SubElement(root, "key", id=key_id, attrib={
            "for": "node",
            "attr.name": attr_name,
            "attr.type": attr_type,
        })
        if default:
            ET.SubElement(key_el, "default").text = default

    for key_id, attr_name, attr_type, default in _EDGE_KEYS:
        key_el = ET.SubElement(root, "key", id=key_id, attrib={
            "for": "edge",
            "attr.name": attr_name,
            "attr.type": attr_type,
        })
        if default:
            ET.SubElement(key_el, "default").text = default

    # ── Build graph ──────────────────────────────────────────────────
    graph = ET.SubElement(root, "graph", id="G", edgedefault="directed")

    nodes = elements.get("nodes", [])
    edges = elements.get("edges", [])

    # Index nodes by ID and group children by parent
    node_by_id: dict[str, dict] = {}
    children: dict[str, list[str]] = defaultdict(list)

    for n in nodes:
        data = n.get("data", {})
        nid = data.get("id", "")
        node_by_id[nid] = data
        parent = data.get("parent")
        if parent:
            children[parent].append(nid)

    # Determine root-level nodes (no parent, or parent not in node set)
    root_node_ids = [
        nid for nid, data in node_by_id.items()
        if not data.get("parent") or data["parent"] not in node_by_id
    ]

    def _add_node(parent_el: ET.Element, nid: str) -> None:
        """Recursively add a node, nesting children via sub-<graph>."""
        data = node_by_id[nid]
        node_el = ET.SubElement(parent_el, "node", id=nid)

        # Write data attributes
        for field, key_id in _NODE_FIELD_MAP.items():
            value = data.get(field)
            if value is not None:
                d_el = ET.SubElement(node_el, "data", key=key_id)
                d_el.text = str(value)

        # If this node has children, nest them inside a sub-graph
        child_ids = children.get(nid, [])
        if child_ids:
            sub = ET.SubElement(node_el, "graph", id=f"G_{nid}",
                                edgedefault="directed")
            for cid in child_ids:
                _add_node(sub, cid)

    # Add root-level nodes
    for nid in root_node_ids:
        _add_node(graph, nid)

    # ── Add edges ────────────────────────────────────────────────────
    for idx, e in enumerate(edges):
        data = e.get("data", {})
        source = data.get("source", "")
        target = data.get("target", "")
        eid = data.get("id", f"e{idx}")

        edge_el = ET.SubElement(graph, "edge", id=eid,
                                source=source, target=target)
        for field, key_id in _EDGE_FIELD_MAP.items():
            value = data.get(field)
            if value is not None:
                d_el = ET.SubElement(edge_el, "data", key=key_id)
                d_el.text = str(value)

    # ── Serialize ────────────────────────────────────────────────────
    ET.indent(root, space="  ")
    buf = io.BytesIO()
    tree = ET.ElementTree(root)
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    return buf.getvalue().decode("utf-8")
