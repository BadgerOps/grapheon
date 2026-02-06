"""
Legacy vis-network format converter for backward compatibility.
"""


def build_legacy_response(nodes, edges, seen_subnets, stats, subnet_prefix):
    """Build vis-network compatible response for backward compatibility."""
    legacy_nodes = []
    legacy_edges = []
    groups = {}

    for node in nodes:
        d = node["data"]
        if d.get("type") in ("vlan", "subnet"):
            # Compound nodes become groups
            groups[d["id"]] = {
                "id": d["id"],
                "label": d["label"],
                "host_count": seen_subnets.get(d["id"], {}).get("host_count", 0),
                "color": d.get("color", "#6b7280"),
            }
        else:
            legacy_nodes.append({
                "id": int(d["id"]) if d["id"].isdigit() else d["id"],
                "label": d["label"],
                "title": d.get("tooltip", ""),
                "color": d.get("color", "#6b7280"),
                "shape": {"diamond": "diamond", "triangle": "triangle", "star": "star",
                          "rectangle": "box", "hexagon": "hexagon", "ellipse": "dot"
                          }.get(d.get("node_shape", "ellipse"), "dot"),
                "size": d.get("node_size", 15),
                "group": d.get("subnet", "unknown"),
                "ip": d.get("ip"),
                "hostname": d.get("hostname"),
                "os": d.get("os"),
                "device_type": d.get("device_type"),
                "open_ports": d.get("open_ports", 0),
                "subnet": d.get("subnet"),
                "segment": d.get("segment"),
                "is_gateway": d.get("is_gateway", False),
            })

    for edge in edges:
        d = edge["data"]
        is_cross = d.get("connection_type") in ("cross_vlan", "cross_subnet")
        legacy_edges.append({
            "id": d["id"],
            "from": int(d["source"]) if str(d["source"]).isdigit() else d["source"],
            "to": int(d["target"]) if str(d["target"]).isdigit() else d["target"],
            "title": d.get("tooltip", ""),
            "color": {"color": "#f59e0b" if is_cross else "#64748b", "opacity": 0.8 if is_cross else 0.6},
            "width": 2 if is_cross else 1,
            "dashes": [8, 4] if is_cross else False,
            "cross_segment": is_cross,
        })

    return {
        "nodes": legacy_nodes,
        "edges": legacy_edges,
        "groups": groups,
        "stats": stats,
    }
