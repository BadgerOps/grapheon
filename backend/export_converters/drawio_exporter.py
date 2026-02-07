"""
draw.io / diagrams.net exporter for Cytoscape.js network topology data.

Converts Cytoscape.js JSON elements into an mxGraph XML document (``.drawio``)
that can be opened in draw.io (desktop or web) for editing, sharing, and
further diagramming.

Features
--------
* Hierarchical grouping: VLANs and subnets become collapsible container
  shapes so the compound-node hierarchy is preserved.
* Device‑type styling: colors and rounded shapes match the Cytoscape
  visualization theme for a consistent look.
* Edge routing: connections carry labels and color from the Cytoscape data.
* Auto‑layout: nodes are positioned using a simple grid packing algorithm
  so the diagram is immediately usable without manual rearranging.

Usage
-----
::

    xml_string = cytoscape_to_drawio(elements)
    # elements = {"nodes": [...], "edges": [...]}

"""

import xml.etree.ElementTree as ET
import io
from collections import defaultdict
from typing import Any


# ── Style constants ──────────────────────────────────────────────────

_CONTAINER_STYLE = (
    "rounded=1;whiteSpace=wrap;html=1;container=1;"
    "collapsible=1;childLayout=stackLayout;horizontalStack=0;"
    "resizeParent=1;resizeParentMax=0;fillColor={fill};"
    "strokeColor={stroke};fontColor=#333333;fontSize=13;"
    "fontStyle=1;arcSize=12;swimlaneLine=0;"
    "startSize=30;dashed=0;"
)

_HOST_STYLE = (
    "rounded=1;whiteSpace=wrap;html=1;fillColor={fill};"
    "strokeColor={stroke};fontColor=#ffffff;fontSize=11;"
    "arcSize=8;shadow=1;"
)

_EDGE_STYLE = (
    "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;"
    "jettySize=auto;html=1;strokeColor={color};"
    "strokeWidth=1.5;fontSize=10;labelBackgroundColor=#ffffff;"
)

# Default colors by type
_TYPE_COLORS: dict[str, tuple[str, str]] = {
    # (fill, stroke)
    "vlan":       ("#dbeafe", "#93c5fd"),   # blue-100 / blue-300
    "subnet":     ("#f0fdf4", "#86efac"),   # green-50  / green-300
    "host":       ("#3b82f6", "#2563eb"),   # blue-500  / blue-600
    "router":     ("#f59e0b", "#d97706"),   # amber-500 / amber-600
    "switch":     ("#06b6d4", "#0891b2"),   # cyan-500  / cyan-600
    "firewall":   ("#ef4444", "#dc2626"),   # red-500   / red-600
    "server":     ("#3b82f6", "#2563eb"),   # blue-500  / blue-600
    "workstation": ("#8b5cf6", "#7c3aed"),  # violet-500/ violet-600
    "printer":    ("#6b7280", "#4b5563"),   # gray-500  / gray-600
    "iot":        ("#10b981", "#059669"),   # emerald-500/emerald-600
    "unknown":    ("#9ca3af", "#6b7280"),   # gray-400  / gray-500
    "gateway":    ("#f59e0b", "#d97706"),   # amber-500 / amber-600
    "internet":   ("#6366f1", "#4f46e5"),   # indigo-500/ indigo-600
    "public_ips": ("#a78bfa", "#7c3aed"),   # violet-400/ violet-600
}

# Compound node types that become containers
_COMPOUND_TYPES = {"vlan", "subnet", "public_ips"}

# ── Sizing ───────────────────────────────────────────────────────────

_HOST_W, _HOST_H = 140, 50
_CONTAINER_PAD = 20
_CONTAINER_HEADER = 35
_GRID_GAP = 20
_COLS_PER_CONTAINER = 4


def _resolve_colors(data: dict) -> tuple[str, str]:
    """Pick fill + stroke colors from node data or defaults."""
    dtype = data.get("device_type", data.get("type", "unknown"))
    default_fill, default_stroke = _TYPE_COLORS.get(dtype, _TYPE_COLORS["unknown"])
    fill = data.get("color", default_fill)
    # Darken fill slightly for stroke if not compound
    stroke = default_stroke
    return fill, stroke


def _build_host_label(data: dict) -> str:
    """Build a multi-line HTML label for a host cell."""
    name = data.get("hostname") or data.get("label") or data.get("id", "?")
    ip = data.get("ip", "")
    dtype = data.get("device_type", "")
    parts = [f"<b>{_escape(name)}</b>"]
    if ip:
        parts.append(f"<br/><font point-size='9'>{_escape(ip)}</font>")
    if dtype and dtype not in ("host", "unknown"):
        parts.append(f"<br/><font point-size='8' color='#cccccc'>{_escape(dtype)}</font>")
    return "".join(parts)


def _escape(text: str) -> str:
    """Minimal HTML escaping for draw.io labels."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def cytoscape_to_drawio(elements: dict[str, list[dict[str, Any]]]) -> str:
    """Convert Cytoscape.js ``elements`` dict to a draw.io XML string.

    Parameters
    ----------
    elements : dict
        ``{"nodes": [...], "edges": [...]}`` as returned by the
        ``/api/network/map`` endpoint.

    Returns
    -------
    str
        UTF-8 encoded draw.io mxGraph XML document.
    """
    nodes = elements.get("nodes", [])
    edges = elements.get("edges", [])

    # ── Index nodes ──────────────────────────────────────────────────
    node_by_id: dict[str, dict] = {}
    children: dict[str, list[str]] = defaultdict(list)

    for n in nodes:
        data = n.get("data", {})
        nid = data.get("id", "")
        node_by_id[nid] = data
        parent = data.get("parent")
        if parent:
            children[parent].append(nid)

    root_ids = [
        nid for nid, data in node_by_id.items()
        if not data.get("parent") or data["parent"] not in node_by_id
    ]

    # ── Assign cell IDs (draw.io uses numeric strings starting at 2) ──
    cell_id_map: dict[str, str] = {}
    next_id = 2

    def _alloc_id(nid: str) -> str:
        nonlocal next_id
        cid = str(next_id)
        cell_id_map[nid] = cid
        next_id += 1
        return cid

    # Pre-allocate IDs depth-first so parents always exist
    def _alloc_tree(nid: str) -> None:
        _alloc_id(nid)
        for cid in children.get(nid, []):
            _alloc_tree(cid)

    for rid in root_ids:
        _alloc_tree(rid)

    # ── Compute sizes bottom-up ──────────────────────────────────────
    node_size: dict[str, tuple[int, int]] = {}  # nid → (w, h)

    def _compute_size(nid: str) -> tuple[int, int]:
        child_ids = children.get(nid, [])
        if not child_ids:
            node_size[nid] = (_HOST_W, _HOST_H)
            return _HOST_W, _HOST_H

        # Compute children first
        child_sizes = [_compute_size(c) for c in child_ids]
        cols = min(len(child_sizes), _COLS_PER_CONTAINER)
        rows = (len(child_sizes) + cols - 1) // cols

        max_w = max(s[0] for s in child_sizes) if child_sizes else _HOST_W
        max_h = max(s[1] for s in child_sizes) if child_sizes else _HOST_H

        w = cols * (max_w + _GRID_GAP) + _CONTAINER_PAD * 2 - _GRID_GAP
        h = rows * (max_h + _GRID_GAP) + _CONTAINER_PAD + _CONTAINER_HEADER - _GRID_GAP
        w = max(w, 200)
        h = max(h, 80)
        node_size[nid] = (w, h)
        return w, h

    for rid in root_ids:
        _compute_size(rid)

    # ── Compute positions ────────────────────────────────────────────
    node_pos: dict[str, tuple[int, int]] = {}  # nid → (x, y)

    def _layout_children(parent_nid: str, ox: int, oy: int) -> None:
        """Grid-pack children inside a container at offset (ox, oy)."""
        child_ids = children.get(parent_nid, [])
        if not child_ids:
            return

        child_sizes = [node_size[c] for c in child_ids]
        max_cw = max(s[0] for s in child_sizes)
        max_ch = max(s[1] for s in child_sizes)
        cols = min(len(child_ids), _COLS_PER_CONTAINER)

        start_x = _CONTAINER_PAD
        start_y = _CONTAINER_HEADER

        for i, cid in enumerate(child_ids):
            col = i % cols
            row = i // cols
            cx = start_x + col * (max_cw + _GRID_GAP)
            cy = start_y + row * (max_ch + _GRID_GAP)
            node_pos[cid] = (ox + cx, oy + cy)
            _layout_children(cid, ox + cx, oy + cy)

    # Lay out root nodes in a horizontal row
    root_x = 40
    for rid in root_ids:
        rw, rh = node_size[rid]
        node_pos[rid] = (root_x, 40)
        _layout_children(rid, root_x, 40)
        root_x += rw + _GRID_GAP * 2

    # ── Build mxGraph XML ────────────────────────────────────────────
    mxfile = ET.Element("mxfile", host="app.diagrams.net",
                        modified="2026-01-01T00:00:00.000Z",
                        type="device")
    diagram = ET.SubElement(mxfile, "diagram", id="network-topology",
                            name="Network Topology")
    mx_model = ET.SubElement(diagram, "mxGraphModel", dx="1422", dy="762",
                             grid="1", gridSize="10", guides="1",
                             tooltips="1", connect="1", arrows="1",
                             fold="1", page="1", pageScale="1",
                             pageWidth="2400", pageHeight="1600")
    mx_root = ET.SubElement(mx_model, "root")

    # draw.io requires cell 0 and cell 1 (background + default parent)
    ET.SubElement(mx_root, "mxCell", id="0")
    ET.SubElement(mx_root, "mxCell", id="1", parent="0")

    # ── Add node cells ───────────────────────────────────────────────
    for nid in cell_id_map:
        data = node_by_id[nid]
        cid = cell_id_map[nid]
        parent_nid = data.get("parent")
        parent_cid = cell_id_map.get(parent_nid, "1") if parent_nid else "1"
        ntype = data.get("type", "host")
        is_compound = ntype in _COMPOUND_TYPES or nid in children

        x, y = node_pos.get(nid, (0, 0))
        # For children, use position relative to parent
        if parent_nid and parent_nid in node_pos:
            px, py = node_pos[parent_nid]
            x -= px
            y -= py
        w, h = node_size.get(nid, (_HOST_W, _HOST_H))

        fill, stroke = _resolve_colors(data)

        if is_compound:
            style = _CONTAINER_STYLE.format(fill=fill, stroke=stroke)
            label = _escape(data.get("label", nid))
        else:
            style = _HOST_STYLE.format(fill=fill, stroke=stroke)
            label = _build_host_label(data)

        cell = ET.SubElement(mx_root, "mxCell", id=cid, value=label,
                             style=style, vertex="1", parent=parent_cid)
        if is_compound:
            cell.set("connectable", "0")
        ET.SubElement(cell, "mxGeometry", x=str(x), y=str(y),
                      width=str(w), height=str(h), attrib={"as": "geometry"})

    # ── Add edge cells ───────────────────────────────────────────────
    for idx, e in enumerate(edges):
        data = e.get("data", {})
        source = data.get("source", "")
        target = data.get("target", "")
        label = data.get("label", "")
        color = data.get("color", "#9ca3af")
        eid = str(next_id)
        next_id += 1

        source_cid = cell_id_map.get(source)
        target_cid = cell_id_map.get(target)
        if not source_cid or not target_cid:
            continue

        style = _EDGE_STYLE.format(color=color)
        edge = ET.SubElement(mx_root, "mxCell", id=eid,
                             value=_escape(label), style=style,
                             edge="1", parent="1",
                             source=source_cid, target=target_cid)
        ET.SubElement(edge, "mxGeometry", relative="1",
                      attrib={"as": "geometry"})

    # ── Serialize ────────────────────────────────────────────────────
    ET.indent(mxfile, space="  ")
    buf = io.BytesIO()
    tree = ET.ElementTree(mxfile)
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    return buf.getvalue().decode("utf-8")
