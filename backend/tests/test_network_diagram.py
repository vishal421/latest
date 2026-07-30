from fastapi.testclient import TestClient

from app.main import app
from app.models import Device, Vendor, DeviceType
from app.store import store

client = TestClient(app)


def setup_function():
    store.clear_all_for_tests()


def test_node_types_lists_the_full_icon_palette():
    resp = client.get("/network-diagram/node-types")
    assert resp.status_code == 200
    types = {t["type"] for t in resp.json()}
    assert {"access_point", "l2_switch", "l3_switch", "router", "firewall", "isp"}.issubset(types)


def test_create_unmapped_external_node():
    resp = client.post("/network-diagram/nodes", json={"node_type": "isp", "label": "ISP Uplink", "pos_x": 10, "pos_y": 20})
    assert resp.status_code == 200
    body = resp.json()
    assert body["device_id"] is None
    assert body["label"] == "ISP Uplink"


def test_create_node_rejects_unknown_type():
    resp = client.post("/network-diagram/nodes", json={"node_type": "toaster", "label": "x"})
    assert resp.status_code == 400


def test_create_node_mapped_to_real_device():
    fw = Device(device_id="fw-1", hostname="fw1", mgmt_ip="10.0.0.1", vendor=Vendor.PALOALTO, device_type=DeviceType.FIREWALL)
    store.add_device(fw)
    resp = client.post("/network-diagram/nodes", json={"node_type": "firewall", "label": "Edge FW", "device_id": "fw-1"})
    assert resp.status_code == 200
    assert resp.json()["device_id"] == "fw-1"


def test_create_node_rejects_unknown_device():
    resp = client.post("/network-diagram/nodes", json={"node_type": "firewall", "label": "x", "device_id": "nonexistent"})
    assert resp.status_code == 404


def test_update_node_position_and_mapping():
    create = client.post("/network-diagram/nodes", json={"node_type": "l2_switch", "label": "Switch 1"})
    node_id = create.json()["node_id"]
    resp = client.patch(f"/network-diagram/nodes/{node_id}", json={"pos_x": 99, "pos_y": 55})
    assert resp.status_code == 200
    assert resp.json()["pos_x"] == 99
    assert resp.json()["pos_y"] == 55
    assert resp.json()["label"] == "Switch 1"  # unspecified fields untouched


def test_edges_require_both_nodes_to_exist():
    n1 = client.post("/network-diagram/nodes", json={"node_type": "access_point", "label": "AP1"}).json()
    resp = client.post("/network-diagram/edges", json={"node_a": n1["node_id"], "node_b": "does-not-exist"})
    assert resp.status_code == 404


def test_create_edge_with_interfaces_and_full_graph_roundtrip():
    n1 = client.post("/network-diagram/nodes", json={"node_type": "access_point", "label": "AP1"}).json()
    n2 = client.post("/network-diagram/nodes", json={"node_type": "l2_switch", "label": "SW1"}).json()
    edge = client.post("/network-diagram/edges", json={
        "node_a": n1["node_id"], "node_b": n2["node_id"],
        "interface_a": None, "interface_b": "GigabitEthernet0/1",
    }).json()
    assert edge["interface_b"] == "GigabitEthernet0/1"

    graph = client.get("/network-diagram").json()
    assert len(graph["nodes"]) == 2
    assert len(graph["edges"]) == 1


def test_deleting_node_cascades_to_its_edges():
    n1 = client.post("/network-diagram/nodes", json={"node_type": "access_point", "label": "AP1"}).json()
    n2 = client.post("/network-diagram/nodes", json={"node_type": "l2_switch", "label": "SW1"}).json()
    client.post("/network-diagram/edges", json={"node_a": n1["node_id"], "node_b": n2["node_id"]})

    client.delete(f"/network-diagram/nodes/{n1['node_id']}")

    graph = client.get("/network-diagram").json()
    assert len(graph["nodes"]) == 1
    assert len(graph["edges"]) == 0
