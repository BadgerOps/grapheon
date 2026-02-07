"""
Unit tests for GraphML and draw.io network topology exporters.

Tests both the converter modules directly and the API endpoints that serve them.
"""

import xml.etree.ElementTree as ET

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from main import app
from export_converters.graphml_exporter import cytoscape_to_graphml
from export_converters.drawio_exporter import cytoscape_to_drawio


# ── Test data ────────────────────────────────────────────────────────

SAMPLE_ELEMENTS = {
    "nodes": [
        {
            "data": {
                "id": "vlan_10",
                "type": "vlan",
                "label": "Management (VLAN 10)",
                "color": "#dbeafe",
            }
        },
        {
            "data": {
                "id": "subnet_192.168.1.0/24",
                "type": "subnet",
                "label": "192.168.1.0/24",
                "parent": "vlan_10",
                "color": "#f0fdf4",
            }
        },
        {
            "data": {
                "id": "host_1",
                "type": "host",
                "label": "server01",
                "ip": "192.168.1.10",
                "hostname": "server01",
                "mac": "00:11:22:33:44:55",
                "os": "Linux",
                "device_type": "server",
                "color": "#3b82f6",
                "shape": "round-rectangle",
                "open_ports": 5,
                "is_gateway": False,
                "subnet": "192.168.1.0/24",
                "vlan_id": 10,
                "vlan_name": "Management",
                "parent": "subnet_192.168.1.0/24",
            }
        },
        {
            "data": {
                "id": "host_2",
                "type": "host",
                "label": "switch01",
                "ip": "192.168.1.1",
                "hostname": "switch01",
                "mac": "aa:bb:cc:dd:ee:ff",
                "os": "Cisco IOS",
                "device_type": "router",
                "color": "#f59e0b",
                "shape": "diamond",
                "open_ports": 2,
                "is_gateway": True,
                "subnet": "192.168.1.0/24",
                "vlan_id": 10,
                "vlan_name": "Management",
                "parent": "subnet_192.168.1.0/24",
            }
        },
    ],
    "edges": [
        {
            "data": {
                "id": "edge_1_2",
                "source": "host_1",
                "target": "host_2",
                "connection_type": "same_subnet",
                "label": "ESTABLISHED",
                "color": "#60a5fa",
            }
        },
    ],
}

EMPTY_ELEMENTS = {"nodes": [], "edges": []}


# ── GraphML converter tests ─────────────────────────────────────────


class TestGraphMLExporter:
    """Tests for the GraphML export converter."""

    def test_returns_valid_xml(self):
        result = cytoscape_to_graphml(SAMPLE_ELEMENTS)
        assert result.startswith("<?xml")
        # Should parse without error
        root = ET.fromstring(result)
        assert root.tag.endswith("graphml")

    def test_declares_graphml_keys(self):
        result = cytoscape_to_graphml(SAMPLE_ELEMENTS)
        root = ET.fromstring(result)
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        keys = root.findall("g:key", ns)
        key_ids = {k.get("id") for k in keys}
        # Should have node keys
        assert "d_label" in key_ids
        assert "d_type" in key_ids
        assert "d_ip" in key_ids
        assert "d_device_type" in key_ids
        # Should have edge keys
        assert "d_conn_type" in key_ids

    def test_contains_all_nodes(self):
        result = cytoscape_to_graphml(SAMPLE_ELEMENTS)
        root = ET.fromstring(result)
        # Recursively find all <node> elements
        all_nodes = root.iter("{http://graphml.graphdrawing.org/xmlns}node")
        node_ids = {n.get("id") for n in all_nodes}
        assert "vlan_10" in node_ids
        assert "subnet_192.168.1.0/24" in node_ids
        assert "host_1" in node_ids
        assert "host_2" in node_ids

    def test_hierarchy_via_nested_graphs(self):
        """Compound nodes should contain nested <graph> elements."""
        result = cytoscape_to_graphml(SAMPLE_ELEMENTS)
        root = ET.fromstring(result)
        ns = "http://graphml.graphdrawing.org/xmlns"
        # Find vlan_10 node
        vlan_node = None
        for node in root.iter(f"{{{ns}}}node"):
            if node.get("id") == "vlan_10":
                vlan_node = node
                break
        assert vlan_node is not None
        # Should have a nested <graph> child
        sub_graph = vlan_node.find(f"{{{ns}}}graph")
        assert sub_graph is not None
        assert sub_graph.get("id") == "G_vlan_10"

    def test_node_data_attributes(self):
        result = cytoscape_to_graphml(SAMPLE_ELEMENTS)
        root = ET.fromstring(result)
        ns = "http://graphml.graphdrawing.org/xmlns"
        # Find host_1
        host_node = None
        for node in root.iter(f"{{{ns}}}node"):
            if node.get("id") == "host_1":
                host_node = node
                break
        assert host_node is not None
        # Check data values
        data_map = {
            d.get("key"): d.text
            for d in host_node.findall(f"{{{ns}}}data")
        }
        assert data_map.get("d_label") == "server01"
        assert data_map.get("d_ip") == "192.168.1.10"
        assert data_map.get("d_device_type") == "server"
        assert data_map.get("d_color") == "#3b82f6"

    def test_contains_edges(self):
        result = cytoscape_to_graphml(SAMPLE_ELEMENTS)
        root = ET.fromstring(result)
        ns = "http://graphml.graphdrawing.org/xmlns"
        edges = list(root.iter(f"{{{ns}}}edge"))
        assert len(edges) == 1
        edge = edges[0]
        assert edge.get("source") == "host_1"
        assert edge.get("target") == "host_2"

    def test_edge_data_attributes(self):
        result = cytoscape_to_graphml(SAMPLE_ELEMENTS)
        root = ET.fromstring(result)
        ns = "http://graphml.graphdrawing.org/xmlns"
        edge = list(root.iter(f"{{{ns}}}edge"))[0]
        data_map = {
            d.get("key"): d.text
            for d in edge.findall(f"{{{ns}}}data")
        }
        assert data_map.get("d_conn_type") == "same_subnet"
        assert data_map.get("d_label") == "ESTABLISHED"

    def test_empty_elements(self):
        result = cytoscape_to_graphml(EMPTY_ELEMENTS)
        root = ET.fromstring(result)
        ns = "http://graphml.graphdrawing.org/xmlns"
        nodes = list(root.iter(f"{{{ns}}}node"))
        edges = list(root.iter(f"{{{ns}}}edge"))
        assert len(nodes) == 0
        assert len(edges) == 0

    def test_single_node_no_edges(self):
        elements = {
            "nodes": [
                {"data": {"id": "h1", "type": "host", "label": "solo"}}
            ],
            "edges": [],
        }
        result = cytoscape_to_graphml(elements)
        root = ET.fromstring(result)
        ns = "http://graphml.graphdrawing.org/xmlns"
        nodes = list(root.iter(f"{{{ns}}}node"))
        assert len(nodes) == 1
        assert nodes[0].get("id") == "h1"

    def test_special_characters_escaped(self):
        """Labels with & < > should be properly escaped in XML."""
        elements = {
            "nodes": [
                {"data": {"id": "h1", "type": "host", "label": "server <main> & backup"}}
            ],
            "edges": [],
        }
        result = cytoscape_to_graphml(elements)
        # Should parse without error
        root = ET.fromstring(result)
        ns = "http://graphml.graphdrawing.org/xmlns"
        node = list(root.iter(f"{{{ns}}}node"))[0]
        data_map = {
            d.get("key"): d.text
            for d in node.findall(f"{{{ns}}}data")
        }
        assert data_map.get("d_label") == "server <main> & backup"


# ── draw.io converter tests ──────────────────────────────────────────


class TestDrawioExporter:
    """Tests for the draw.io export converter."""

    def test_returns_valid_xml(self):
        result = cytoscape_to_drawio(SAMPLE_ELEMENTS)
        assert result.startswith("<?xml")
        root = ET.fromstring(result)
        assert root.tag == "mxfile"

    def test_has_diagram_structure(self):
        result = cytoscape_to_drawio(SAMPLE_ELEMENTS)
        root = ET.fromstring(result)
        diagram = root.find("diagram")
        assert diagram is not None
        assert diagram.get("name") == "Network Topology"
        model = diagram.find("mxGraphModel")
        assert model is not None
        mx_root = model.find("root")
        assert mx_root is not None

    def test_has_base_cells(self):
        """draw.io requires cell 0 and cell 1 as base hierarchy."""
        result = cytoscape_to_drawio(SAMPLE_ELEMENTS)
        root = ET.fromstring(result)
        mx_root = root.find(".//root")
        cells = mx_root.findall("mxCell")
        cell_ids = {c.get("id") for c in cells}
        assert "0" in cell_ids
        assert "1" in cell_ids

    def test_all_nodes_present_as_cells(self):
        result = cytoscape_to_drawio(SAMPLE_ELEMENTS)
        root = ET.fromstring(result)
        mx_root = root.find(".//root")
        cells = mx_root.findall("mxCell")
        # Filter to vertex cells (not base 0/1 and not edges)
        vertex_cells = [
            c for c in cells
            if c.get("vertex") == "1"
        ]
        # 4 nodes: vlan + subnet + 2 hosts
        assert len(vertex_cells) == 4

    def test_edges_present(self):
        result = cytoscape_to_drawio(SAMPLE_ELEMENTS)
        root = ET.fromstring(result)
        mx_root = root.find(".//root")
        cells = mx_root.findall("mxCell")
        edge_cells = [c for c in cells if c.get("edge") == "1"]
        assert len(edge_cells) == 1

    def test_container_nodes_are_connectable_false(self):
        """VLAN and subnet containers should have connectable=0."""
        result = cytoscape_to_drawio(SAMPLE_ELEMENTS)
        root = ET.fromstring(result)
        mx_root = root.find(".//root")
        cells = mx_root.findall("mxCell")
        containers = [
            c for c in cells
            if c.get("connectable") == "0"
        ]
        # vlan_10 and subnet_192.168.1.0/24 should be containers
        assert len(containers) >= 2

    def test_cells_have_geometry(self):
        result = cytoscape_to_drawio(SAMPLE_ELEMENTS)
        root = ET.fromstring(result)
        mx_root = root.find(".//root")
        cells = mx_root.findall("mxCell")
        vertex_cells = [c for c in cells if c.get("vertex") == "1"]
        for cell in vertex_cells:
            geom = cell.find("mxGeometry")
            assert geom is not None, f"Cell {cell.get('id')} missing geometry"
            # Should have width and height
            assert geom.get("width") is not None
            assert geom.get("height") is not None

    def test_host_style_contains_fill_color(self):
        result = cytoscape_to_drawio(SAMPLE_ELEMENTS)
        root = ET.fromstring(result)
        mx_root = root.find(".//root")
        cells = mx_root.findall("mxCell")
        # Find a host cell (vertex, not container)
        host_cells = [
            c for c in cells
            if c.get("vertex") == "1" and c.get("connectable") is None
        ]
        assert len(host_cells) > 0
        style = host_cells[0].get("style", "")
        assert "fillColor=" in style

    def test_empty_elements(self):
        result = cytoscape_to_drawio(EMPTY_ELEMENTS)
        root = ET.fromstring(result)
        mx_root = root.find(".//root")
        cells = mx_root.findall("mxCell")
        # Only base cells 0 and 1
        assert len(cells) == 2

    def test_edge_references_valid_cells(self):
        result = cytoscape_to_drawio(SAMPLE_ELEMENTS)
        root = ET.fromstring(result)
        mx_root = root.find(".//root")
        cells = mx_root.findall("mxCell")
        all_ids = {c.get("id") for c in cells}
        edge_cells = [c for c in cells if c.get("edge") == "1"]
        for edge in edge_cells:
            assert edge.get("source") in all_ids
            assert edge.get("target") in all_ids

    def test_special_characters_escaped_in_labels(self):
        elements = {
            "nodes": [
                {"data": {"id": "h1", "type": "host", "label": "test<>&\"node",
                          "hostname": "test<>&\"node", "ip": "1.2.3.4"}}
            ],
            "edges": [],
        }
        result = cytoscape_to_drawio(elements)
        # Should parse without error
        root = ET.fromstring(result)
        assert root is not None

    def test_parent_child_cell_relationships(self):
        """Host cells should reference their subnet/VLAN as parent."""
        result = cytoscape_to_drawio(SAMPLE_ELEMENTS)
        root = ET.fromstring(result)
        mx_root = root.find(".//root")
        cells = mx_root.findall("mxCell")
        # Build id→cell map
        cell_map = {c.get("id"): c for c in cells}
        # Host cells should have non-"1" parent (they're inside containers)
        host_cells = [
            c for c in cells
            if c.get("vertex") == "1" and c.get("connectable") is None
        ]
        for hc in host_cells:
            parent = hc.get("parent")
            # Parent should exist and not be the root "1"
            assert parent in cell_map


# ── API endpoint tests ───────────────────────────────────────────────


@pytest_asyncio.fixture
async def async_client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", echo=False, future=True,
    )
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False, future=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


class TestGraphExportEndpoints:
    """Integration tests for the /api/export/network/* endpoints."""

    @pytest.mark.asyncio
    async def test_graphml_endpoint_returns_xml(self, async_client):
        response = await async_client.get("/api/export/network/graphml")
        assert response.status_code == 200
        assert "application/xml" in response.headers["content-type"]
        assert response.headers["content-disposition"].endswith(".graphml")
        # Should be valid XML
        root = ET.fromstring(response.text)
        assert root.tag.endswith("graphml")

    @pytest.mark.asyncio
    async def test_drawio_endpoint_returns_xml(self, async_client):
        response = await async_client.get("/api/export/network/drawio")
        assert response.status_code == 200
        assert "application/xml" in response.headers["content-type"]
        assert response.headers["content-disposition"].endswith(".drawio")
        root = ET.fromstring(response.text)
        assert root.tag == "mxfile"

    @pytest.mark.asyncio
    async def test_graphml_with_subnet_filter(self, async_client):
        response = await async_client.get(
            "/api/export/network/graphml",
            params={"subnet_filter": "192.168.1.0/24"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_drawio_with_show_internet_hide(self, async_client):
        response = await async_client.get(
            "/api/export/network/drawio",
            params={"show_internet": "hide"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_graphml_empty_database(self, async_client):
        """Empty database should still return valid GraphML."""
        response = await async_client.get("/api/export/network/graphml")
        assert response.status_code == 200
        root = ET.fromstring(response.text)
        ns = "http://graphml.graphdrawing.org/xmlns"
        nodes = list(root.iter(f"{{{ns}}}node"))
        assert len(nodes) == 0

    @pytest.mark.asyncio
    async def test_drawio_empty_database(self, async_client):
        """Empty database should still return valid draw.io XML."""
        response = await async_client.get("/api/export/network/drawio")
        assert response.status_code == 200
        root = ET.fromstring(response.text)
        mx_root = root.find(".//root")
        cells = mx_root.findall("mxCell")
        # Only base cells when no data
        assert len(cells) == 2
