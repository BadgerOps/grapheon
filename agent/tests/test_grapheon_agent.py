import subprocess
import sys
import json
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent.grapheon_agent import (
    AgentConfig,
    AGENT_VERSION,
    DEFAULT_USER_AGENT,
    build_snapshot_payload,
    build_config,
    default_route_capture_interfaces,
    filter_local_net_records,
    http_json,
    load_topology_evidence_file,
    collect_configured_topology_evidence,
    collect_passive_capture_evidence,
    passive_capture_options,
    parse_pcap_topology_evidence,
    parse_ip_addr_json,
    parse_ip_neigh_json,
    parse_netstat_output,
    parse_args,
    parse_dns_evidence,
    parse_ss_output,
    parse_timestamp,
    main,
    run_agent,
    should_run_with_policy,
)


def _pcap_packet(*frames: bytes) -> bytes:
    data = bytearray()
    data.extend(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
    for frame in frames:
        data.extend(struct.pack("<IIII", 1, 0, len(frame), len(frame)))
        data.extend(frame)
    return bytes(data)


def _ether(
    payload: bytes,
    ether_type: int = 0x0800,
    *,
    dst: bytes = bytes.fromhex("ffffffffffff"),
    src: bytes = bytes.fromhex("aabbccddeeff"),
) -> bytes:
    return (
        dst
        + src
        + ether_type.to_bytes(2, "big")
        + payload
    )


def _ether_vlan(payload: bytes, ether_type: int, vlan_id: int) -> bytes:
    return (
        bytes.fromhex("ffffffffffff")
        + bytes.fromhex("aabbccddeeff")
        + b"\x81\x00"
        + vlan_id.to_bytes(2, "big")
        + ether_type.to_bytes(2, "big")
        + payload
    )


def _ipv4_udp(src: str, dst: str, sport: int, dport: int, payload: bytes) -> bytes:
    src_bytes = bytes(int(part) for part in src.split("."))
    dst_bytes = bytes(int(part) for part in dst.split("."))
    total_length = 20 + 8 + len(payload)
    ip_header = (
        b"\x45\x00"
        + total_length.to_bytes(2, "big")
        + b"\x00\x00\x00\x00\x40\x11\x00\x00"
        + src_bytes
        + dst_bytes
    )
    udp_header = sport.to_bytes(2, "big") + dport.to_bytes(2, "big") + (8 + len(payload)).to_bytes(2, "big") + b"\x00\x00"
    return ip_header + udp_header + payload


def _ipv4_proto(src: str, dst: str, protocol: int, payload: bytes) -> bytes:
    src_bytes = bytes(int(part) for part in src.split("."))
    dst_bytes = bytes(int(part) for part in dst.split("."))
    total_length = 20 + len(payload)
    return (
        b"\x45\x00"
        + total_length.to_bytes(2, "big")
        + b"\x00\x00\x00\x00\x40"
        + bytes([protocol])
        + b"\x00\x00"
        + src_bytes
        + dst_bytes
        + payload
    )


def _ipv4_tcp(src: str, dst: str, sport: int, dport: int) -> bytes:
    src_bytes = bytes(int(part) for part in src.split("."))
    dst_bytes = bytes(int(part) for part in dst.split("."))
    total_length = 20 + 20
    ip_header = (
        b"\x45\x00"
        + total_length.to_bytes(2, "big")
        + b"\x00\x00\x00\x00\x40\x06\x00\x00"
        + src_bytes
        + dst_bytes
    )
    tcp_header = (
        sport.to_bytes(2, "big")
        + dport.to_bytes(2, "big")
        + b"\x00\x00\x00\x01"
        + b"\x00\x00\x00\x00"
        + b"\x50\x02"
        + b"\xff\xff"
        + b"\x00\x00\x00\x00"
    )
    return ip_header + tcp_header


def _ipv6_udp(src: str, dst: str, sport: int, dport: int, payload: bytes) -> bytes:
    import ipaddress

    src_bytes = ipaddress.ip_address(src).packed
    dst_bytes = ipaddress.ip_address(dst).packed
    udp_header = sport.to_bytes(2, "big") + dport.to_bytes(2, "big") + (8 + len(payload)).to_bytes(2, "big") + b"\x00\x00"
    ip_header = (
        b"\x60\x00\x00\x00"
        + (len(udp_header) + len(payload)).to_bytes(2, "big")
        + b"\x11\x40"
        + src_bytes
        + dst_bytes
    )
    return ip_header + udp_header + payload


def _ipv6_icmp(src: str, dst: str, payload: bytes) -> bytes:
    import ipaddress

    return (
        b"\x60\x00\x00\x00"
        + len(payload).to_bytes(2, "big")
        + b"\x3a\xff"
        + ipaddress.ip_address(src).packed
        + ipaddress.ip_address(dst).packed
        + payload
    )


def _dns_name(name: str) -> bytes:
    encoded = bytearray()
    for label in name.split("."):
        encoded.append(len(label))
        encoded.extend(label.encode())
    encoded.append(0)
    return bytes(encoded)


def _dns_response(name: str, ip: str) -> bytes:
    qname = _dns_name(name)
    answer = (
        b"\xc0\x0c"
        + b"\x00\x01\x00\x01"
        + b"\x00\x00\x00\x3c"
        + b"\x00\x04"
        + bytes(int(part) for part in ip.split("."))
    )
    return b"\x12\x34\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00" + qname + b"\x00\x01\x00\x01" + answer


def _dns_ptr_response(name: str, target: str) -> bytes:
    qname = _dns_name(name)
    target_name = _dns_name(target)
    answer = (
        b"\xc0\x0c"
        + b"\x00\x0c\x00\x01"
        + b"\x00\x00\x00\x3c"
        + len(target_name).to_bytes(2, "big")
        + target_name
    )
    return b"\x12\x34\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00" + qname + b"\x00\x0c\x00\x01" + answer


def _dns_srv_response(name: str, target: str, port: int) -> bytes:
    qname = _dns_name(name)
    rdata = b"\x00\x00\x00\x05" + port.to_bytes(2, "big") + _dns_name(target)
    answer = (
        b"\xc0\x0c"
        + b"\x00\x21\x00\x01"
        + b"\x00\x00\x00\x3c"
        + len(rdata).to_bytes(2, "big")
        + rdata
    )
    return b"\x12\x36\x81\x80\x00\x01\x00\x01\x00\x00\x00\x00" + qname + b"\x00\x21\x00\x01" + answer


def _dns_misc_response() -> bytes:
    qname = _dns_name("2.0.0.10.in-addr.arpa")
    ptr = (
        b"\xc0\x0c"
        + b"\x00\x0c\x00\x01"
        + b"\x00\x00\x00\x3c"
        + len(_dns_name("host.local")).to_bytes(2, "big")
        + _dns_name("host.local")
    )
    srv_name = _dns_name("_printer._tcp.local")
    srv_rdata = b"\x00\x00\x00\x05\x23\x8c" + _dns_name("printer.local")
    srv = srv_name + b"\x00\x21\x00\x01" + b"\x00\x00\x00\x3c" + len(srv_rdata).to_bytes(2, "big") + srv_rdata
    https_rdata = b"\x00\x01" + _dns_name("svc.local")
    https = _dns_name("svc.example") + b"\x00\x41\x00\x01" + b"\x00\x00\x00\x3c" + len(https_rdata).to_bytes(2, "big") + https_rdata
    return b"\x12\x35\x81\x80\x00\x01\x00\x03\x00\x00\x00\x00" + qname + b"\x00\x0c\x00\x01" + ptr + srv + https


def _dhcp_ack(mac: str, ip: str, hostname: str) -> bytes:
    mac_bytes = bytes.fromhex(mac.replace(":", ""))
    payload = bytearray(240)
    payload[0] = 2
    payload[1] = 1
    payload[2] = 6
    payload[16:20] = bytes(int(part) for part in ip.split("."))
    payload[28:34] = mac_bytes
    payload[236:240] = b"\x63\x82\x53\x63"
    payload.extend([53, 1, 5])
    hostname_bytes = hostname.encode()
    payload.extend([12, len(hostname_bytes)])
    payload.extend(hostname_bytes)
    payload.extend([51, 4, 0, 0, 14, 16])
    payload.extend([3, 4, 10, 0, 0, 1])
    payload.extend([1, 4, 255, 255, 255, 0])
    payload.extend([6, 8, 10, 0, 0, 53, 10, 0, 0, 54])
    payload.extend([15, 5])
    payload.extend(b"local")
    payload.extend([60, 6])
    payload.extend(b"vendor")
    payload.extend([50, 4, *bytes(int(part) for part in ip.split("."))])
    payload.extend([255])
    return bytes(payload)


def _arp_reply(sender_mac: str, sender_ip: str, target_mac: str, target_ip: str) -> bytes:
    return (
        struct.pack("!HHBBH", 1, 0x0800, 6, 4, 2)
        + bytes.fromhex(sender_mac.replace(":", ""))
        + bytes(int(part) for part in sender_ip.split("."))
        + bytes.fromhex(target_mac.replace(":", ""))
        + bytes(int(part) for part in target_ip.split("."))
    )


def _lldp_tlv(tlv_type: int, value: bytes) -> bytes:
    header = (tlv_type << 9) | len(value)
    return header.to_bytes(2, "big") + value


def _cdp_tlv(tlv_type: int, value: bytes) -> bytes:
    return tlv_type.to_bytes(2, "big") + (len(value) + 4).to_bytes(2, "big") + value


def _nbns_name(name: str) -> bytes:
    raw = name.upper().ljust(15)[:15].encode("ascii") + b"\x00"
    encoded = bytearray([32])
    for byte in raw:
        encoded.append(0x41 + ((byte >> 4) & 0x0F))
        encoded.append(0x41 + (byte & 0x0F))
    encoded.append(0)
    return bytes(encoded)


def _nbns_response(name: str, ip: str) -> bytes:
    rr_name = _nbns_name(name)
    rdata = b"\x00\x00" + bytes(int(part) for part in ip.split("."))
    return (
        b"\x12\x34\x85\x00\x00\x00\x00\x01\x00\x00\x00\x00"
        + rr_name
        + b"\x00\x20\x00\x01\x00\x00\x00\x3c"
        + len(rdata).to_bytes(2, "big")
        + rdata
    )


def _dhcpv6_reply() -> bytes:
    import ipaddress

    duid = b"\x00\x03\x00\x01" + bytes.fromhex("aabbccddee03")
    iaaddr = ipaddress.ip_address("2001:db8::50").packed + b"\x00\x00\x0e\x10\x00\x00\x1c\x20"
    ia_na = b"\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00" + b"\x00\x05" + len(iaaddr).to_bytes(2, "big") + iaaddr
    iaprefix = b"\x00\x00\x0e\x10\x00\x00\x1c\x20\x38" + ipaddress.ip_address("2001:db8:1200::").packed
    ia_pd = b"\x00\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00" + b"\x00\x1a" + len(iaprefix).to_bytes(2, "big") + iaprefix
    return (
        b"\x07\x12\x34\x56"
        + b"\x00\x01" + len(duid).to_bytes(2, "big") + duid
        + b"\x00\x03" + len(ia_na).to_bytes(2, "big") + ia_na
        + b"\x00\x19" + len(ia_pd).to_bytes(2, "big") + ia_pd
        + b"\x00\x17\x00\x10" + ipaddress.ip_address("2001:db8::53").packed
        + b"\x00\x18" + len(_dns_name("example.local")).to_bytes(2, "big") + _dns_name("example.local")
        + b"\x00\x27\x00\x0b\x00lease-host"
    )


def _router_advertisement() -> bytes:
    import ipaddress

    prefix = (
        b"\x03\x04\x40\xc0"
        + b"\x00\x00\x0e\x10"
        + b"\x00\x00\x07\x08"
        + b"\x00\x00\x00\x00"
        + ipaddress.ip_address("2001:db8:1::").packed
    )
    mtu = b"\x05\x01\x00\x00\x00\x00\x05\xdc"
    rdnss = b"\x19\x03\x00\x00\x00\x00\x0e\x10" + ipaddress.ip_address("2001:db8::53").packed
    return b"\x86\x00\x00\x00\x40\x00\x07\x08\x00\x00\x00\x00\x00\x00\x00\x00" + prefix + mtu + rdnss


def _stp_frame() -> bytes:
    bpdu = (
        b"\x00\x00\x00\x00\x00"
        + bytes.fromhex("8000001122334455")
        + b"\x00\x00\x00\x04"
        + bytes.fromhex("8000aabbccddeeff")
        + b"\x80\x01"
        + b"\x00\x00\x14\x00\x02\x00\x0f\x00\x00\x00"
    )
    payload = b"\x42\x42\x03" + bpdu
    return bytes.fromhex("0180c2000000") + bytes.fromhex("aabbccddeeff") + len(payload).to_bytes(2, "big") + payload


def _lacp_frame() -> bytes:
    payload = bytearray(64)
    payload[0] = 1
    payload[1] = 1
    payload[2] = 1
    payload[3] = 20
    payload[4:6] = b"\x00\x01"
    payload[6:12] = bytes.fromhex("001122334455")
    payload[14:16] = b"\x00\x64"
    payload[18:20] = b"\x00\x09"
    payload[22] = 2
    payload[23] = 20
    payload[24:26] = b"\x00\x01"
    payload[26:32] = bytes.fromhex("66778899aabb")
    payload[34:36] = b"\x00\x64"
    payload[38:40] = b"\x00\x0a"
    return _ether(bytes(payload), ether_type=0x8809, dst=bytes.fromhex("0180c2000002"))


def _write_pcap(tmp_path: Path, *frames: bytes) -> Path:
    path = tmp_path / "capture.pcap"
    path.write_bytes(_pcap_packet(*frames))
    return path


def test_parse_ip_addr_json_ignores_loopback_and_extracts_mac():
    payload = """
    [
      {
        "ifname": "lo",
        "address": "00:00:00:00:00:00",
        "addr_info": [{"local": "127.0.0.1", "prefixlen": 8}]
      },
      {
        "ifname": "eth0",
        "address": "aa:bb:cc:dd:ee:ff",
        "addr_info": [
          {"local": "10.20.0.5", "prefixlen": 24},
          {"local": "fe80::1", "prefixlen": 64}
        ]
      }
    ]
    """

    result = parse_ip_addr_json(payload)

    assert result == [
        {
            "interface": "eth0",
            "ip_address": "10.20.0.5",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "prefix_length": 24,
        },
        {
            "interface": "eth0",
            "ip_address": "fe80::1",
            "mac_address": "aa:bb:cc:dd:ee:ff",
            "prefix_length": 64,
        },
    ]


def test_filter_local_net_records_removes_host_local_noise():
    records = [
        {"interface": "lo", "ip_address": "127.0.0.1"},
        {"interface": "vmnet1", "ip_address": "172.16.238.1"},
        {"interface": "eth0", "ip_address": "fe80::1"},
        {"interface": "eth0", "ip_address": "0.0.0.0"},
        {"interface": "eth0", "ip_address": "10.20.0.5"},
    ]

    assert filter_local_net_records(records, ip_fields=["ip_address"]) == [
        {"interface": "eth0", "ip_address": "10.20.0.5"}
    ]


def test_filter_local_net_records_removes_local_noise_networks():
    records = [
        {"interface": "eth0", "destination": "fe80::/64", "gateway": None},
        {"interface": "eth0", "destination": "169.254.0.0/16", "gateway": None},
        {"interface": "eth0", "destination": "10.20.0.0/24", "gateway": None},
    ]

    assert filter_local_net_records(records, ip_fields=["destination", "gateway"]) == [
        {"interface": "eth0", "destination": "10.20.0.0/24", "gateway": None}
    ]


def test_load_topology_evidence_file_bounds_records(tmp_path):
    evidence_path = tmp_path / "topology.json"
    evidence_path.write_text(
        json.dumps(
            {
                "topology_evidence": [
                    {"evidence_type": "dns_name", "source": "dns", "ip_address": "10.0.0.2", "name": "b.example"},
                    {"evidence_type": "dhcp_lease", "source": "dhcp", "ip_address": "10.0.0.3"},
                    {"evidence_type": "flow_relationship", "source": "zeek", "local_ip": "10.0.0.2"},
                ]
            }
        )
    )

    result = load_topology_evidence_file(evidence_path, max_records=2)

    assert len(result) == 2
    assert {item["evidence_type"] for item in result} == {"dns_name", "dhcp_lease"}


def test_collect_configured_topology_evidence_reads_paths(tmp_path):
    evidence_path = tmp_path / "topology.json"
    evidence_path.write_text(
        json.dumps(
            [
                {
                    "evidence_type": "network_segment",
                    "source": "agent",
                    "network": "10.20.0.0/24",
                    "vlan_id": 20,
                }
            ]
        )
    )
    config = AgentConfig(
        server_url="https://grapheon.example.com",
        enrollment_key=None,
        state_dir=tmp_path,
        config_path=tmp_path / "agent.env",
        request_timeout_seconds=30,
        verify_tls=True,
        ca_file=None,
        display_name=None,
        site_name=None,
        hostname=None,
        timer_interval_seconds=900,
        api_key_header="X-Agent-Api-Key",
        user_agent=DEFAULT_USER_AGENT,
        ignore_local_net=False,
        topology_evidence_paths=[str(evidence_path)],
        topology_evidence_max_records=10,
    )

    assert collect_configured_topology_evidence(config) == [
        {
            "evidence_type": "network_segment",
            "network": "10.20.0.0/24",
            "source": "agent",
            "vlan_id": 20,
        }
    ]


def test_parse_pcap_topology_evidence_extracts_passive_map_data(tmp_path):
    pcap_path = _write_pcap(
        tmp_path,
        _ether(
            _arp_reply(
                "aa:bb:cc:dd:ee:01",
                "10.0.0.2",
                "aa:bb:cc:dd:ee:ff",
                "10.0.0.1",
            ),
            ether_type=0x0806,
        ),
        _ether(_ipv4_udp("10.0.0.53", "10.0.0.2", 53, 53000, _dns_response("host.local", "10.0.0.2"))),
        _ether(_ipv4_udp("10.0.0.1", "255.255.255.255", 67, 68, _dhcp_ack("aa:bb:cc:dd:ee:02", "10.0.0.50", "lease-host"))),
        _ether(_ipv4_tcp("10.0.0.2", "10.0.0.3", 51514, 443)),
    )

    evidence = parse_pcap_topology_evidence(pcap_path, observer="collector01", include_flows=True)

    assert {item["evidence_type"] for item in evidence} >= {
        "mac_ip_binding",
        "dns_name",
        "dhcp_lease",
        "flow_relationship",
    }
    assert any(item["evidence_type"] == "dns_name" and item["name"] == "host.local" for item in evidence)
    assert any(item["evidence_type"] == "dhcp_lease" and item["hostname"] == "lease-host" for item in evidence)
    assert any(
        item["evidence_type"] == "flow_relationship"
        and item["protocol"] == "tcp"
        and item["local_ip"] == "10.0.0.2"
        and item["remote_ip"] == "10.0.0.3"
        for item in evidence
    )
    assert all(item.get("observer") == "collector01" for item in evidence)


def test_parse_dns_evidence_sanitizes_service_instance_names():
    evidence = parse_dns_evidence(
        _dns_ptr_response("_smb._tcp.local", "EPSON ET-16600 Series._smb._tcp.local"),
        source="mdns",
        observer="collector01",
        src_ip="10.0.0.20",
    )

    record = next(item for item in evidence if item["evidence_type"] == "dns_name")
    assert record["name"] == "EPSON_ET-16600_Series._smb._tcp.local"
    assert record["metadata"]["raw_name"] == "EPSON ET-16600 Series._smb._tcp.local"


def test_parse_pcap_topology_evidence_extracts_lldp_and_cdp(tmp_path):
    import ipaddress

    lldp_payload = b"".join(
        [
            _lldp_tlv(1, b"\x04\x00\x11\x22\x33\x44\x55"),
            _lldp_tlv(2, b"\x05Gi1/0/1"),
            _lldp_tlv(5, b"switch01"),
            _lldp_tlv(7, b"\x00\x14\x00\x14"),
            _lldp_tlv(8, b"\x05\x01\x0a\x00\x00\x01\x02\x00\x00"),
            _lldp_tlv(127, b"\x00\x80\xc2\x01\x00\x14"),
            _lldp_tlv(127, b"\x00\x80\xc2\x03\x00\x14Users"),
            _lldp_tlv(127, b"\x00\x12\x0f\x04\x05\xdc"),
            _lldp_tlv(0, b""),
        ]
    )
    lldp_ipv6_payload = b"".join(
        [
            _lldp_tlv(1, b"\x04\x00\x11\x22\x33\x44\x66"),
            _lldp_tlv(2, b"\x05Te1/0/49"),
            _lldp_tlv(5, b"switch-ipv6"),
            _lldp_tlv(8, b"\x11\x02" + ipaddress.ip_address("2001:db8::2").packed + b"\x02\x00\x00"),
            _lldp_tlv(0, b""),
        ]
    )
    cdp_address = (
        b"\x00\x00\x00\x01"
        + b"\x01\x01\xcc"
        + b"\x00\x04"
        + bytes([10, 0, 0, 254])
    )
    cdp_payload = (
        bytes.fromhex("01000000")
        + _cdp_tlv(0x0001, b"router01")
        + _cdp_tlv(0x0002, cdp_address)
        + _cdp_tlv(0x0003, b"Eth1/1")
        + _cdp_tlv(0x0004, b"\x00\x00\x00\x09")
        + _cdp_tlv(0x0005, b"IOS-XE")
        + _cdp_tlv(0x0006, b"C9300")
        + _cdp_tlv(0x000a, b"\x00\x14")
        + _cdp_tlv(0x000b, b"\x01")
    )
    cdp_frame = (
        bytes.fromhex("01000ccccccc")
        + bytes.fromhex("aabbccddeeff")
        + (len(cdp_payload) + 8).to_bytes(2, "big")
        + bytes.fromhex("aaaa0300000c2000")
        + cdp_payload
    )
    pcap_path = _write_pcap(
        tmp_path,
        _ether(
            lldp_payload,
            ether_type=0x88CC,
            dst=bytes.fromhex("0180c200000e"),
        ),
        _ether(
            lldp_ipv6_payload,
            ether_type=0x88CC,
            dst=bytes.fromhex("0180c200000e"),
        ),
        cdp_frame,
    )

    evidence = parse_pcap_topology_evidence(pcap_path, observer="collector01", interface="eth0")

    assert any(
        item["evidence_type"] == "l2_neighbor"
        and item["source"] == "lldp"
        and item["system_name"] == "switch01"
        and item["management_ip"] == "10.0.0.1"
        and item["interface"] == "eth0"
        and item["vlan_id"] == 20
        and item["metadata"]["mtu"] == 1500
        and "router" in item["metadata"]["enabled_capabilities"]
        for item in evidence
    )
    assert any(
        item["evidence_type"] == "l2_neighbor"
        and item["source"] == "cdp"
        and item["system_name"] == "router01"
        and item["management_ip"] == "10.0.0.254"
        and item["port_id"] == "Eth1/1"
        and item["vlan_id"] == 20
        and item["metadata"]["platform"] == "C9300"
        and item["metadata"]["software_version"] == "IOS-XE"
        and item["metadata"]["duplex"] == "full"
        for item in evidence
    )
    assert any(
        item["evidence_type"] == "l2_neighbor"
        and item["source"] == "lldp"
        and item["system_name"] == "switch-ipv6"
        and item["management_ip"] == "2001:db8::2"
        for item in evidence
    )


def test_parse_pcap_topology_evidence_enriches_dns_nbns_and_discovery(tmp_path):
    pcap_path = _write_pcap(
        tmp_path,
        _ether(_ipv4_udp("10.0.0.53", "10.0.0.2", 53, 53000, _dns_misc_response())),
        _ether(_ipv4_udp("10.0.0.20", "224.0.0.251", 5353, 5353, _dns_srv_response("EPSON ET-16600 Series._smb._tcp.local", "epson.local", 445))),
        _ether(_ipv4_udp("10.0.0.10", "10.0.0.255", 137, 137, _nbns_response("WORKSTATION", "10.0.0.10"))),
        _ether(_ipv4_udp("10.0.0.20", "239.255.255.250", 1900, 1900, b"NOTIFY * HTTP/1.1\r\nUSN: uuid:device-1\r\nLOCATION: http://10.0.0.20/root.xml\r\nST: upnp:rootdevice\r\n\r\n")),
        _ether(_ipv4_udp("10.0.0.30", "239.255.255.250", 3702, 3702, b"<Envelope><ProbeMatch><a:Address>urn:uuid:printer-1</a:Address><d:Types>dn:Printer</d:Types><d:XAddrs>http://10.0.0.30/wsd</d:XAddrs></ProbeMatch></Envelope>")),
    )

    evidence = parse_pcap_topology_evidence(pcap_path, observer="collector01")

    assert any(item["source"] == "dns" and item["name"] == "host.local" and item["ip_address"] == "10.0.0.2" for item in evidence)
    assert any(item["source"] == "dns" and item["name"] == "_printer._tcp.local" and item["metadata"]["service_port"] == 9100 for item in evidence)
    assert any(item["source"] == "dns" and item["metadata"].get("record_kind") == "https" for item in evidence)
    assert any(
        item["source"] == "mdns"
        and item["name"] == "EPSON_ET-16600_Series._smb._tcp.local"
        and item["metadata"]["raw_name"] == "EPSON ET-16600 Series._smb._tcp.local"
        and item["metadata"]["service_port"] == 445
        for item in evidence
    )
    assert any(item["source"] == "nbns" and item["name"] == "WORKSTATION" and item["ip_address"] == "10.0.0.10" for item in evidence)
    assert any(item["source"] == "ssdp" and item["metadata"]["location"] == "http://10.0.0.20/root.xml" for item in evidence)
    assert any(item["source"] == "wsd" and item["metadata"]["types"] == "dn:Printer" for item in evidence)


def test_parse_pcap_topology_evidence_enriches_dhcpv4_dhcpv6_and_ra(tmp_path):
    pcap_path = _write_pcap(
        tmp_path,
        _ether_vlan(_ipv4_udp("10.0.0.1", "255.255.255.255", 67, 68, _dhcp_ack("aa:bb:cc:dd:ee:02", "10.0.0.50", "lease-host")), 0x0800, 30),
        _ether(_ipv6_udp("fe80::1", "ff02::1:2", 547, 546, _dhcpv6_reply()), ether_type=0x86DD),
        _ether(_ipv6_icmp("fe80::1", "ff02::1", _router_advertisement()), ether_type=0x86DD),
    )

    evidence = parse_pcap_topology_evidence(pcap_path, observer="collector01")

    dhcpv4 = next(item for item in evidence if item["source"] == "dhcp" and item["ip_address"] == "10.0.0.50")
    assert dhcpv4["vlan_id"] == 30
    assert dhcpv4["metadata"]["router"] == "10.0.0.1"
    assert dhcpv4["metadata"]["dns_servers"] == ["10.0.0.53", "10.0.0.54"]
    assert dhcpv4["metadata"]["lease_time_seconds"] == 3600

    assert any(item["source"] == "dhcpv6" and item.get("ip_address") == "2001:db8::50" and item["hostname"] == "lease-host" for item in evidence)
    assert any(item["source"] == "dhcpv6" and item.get("network") == "2001:db8:1200::/56" for item in evidence)
    assert any(item["evidence_type"] == "network_segment" and item["network"] == "2001:db8:1::/64" for item in evidence)
    ra_route = next(item for item in evidence if item["evidence_type"] == "route" and item["gateway"] == "fe80::1")
    assert ra_route["metadata"]["mtu"] == 1500
    assert ra_route["metadata"]["rdnss"] == ["2001:db8::53"]


def test_parse_pcap_topology_evidence_extracts_l2_control_and_routing_hints(tmp_path):
    hsrp_payload = b"\x00\x00\x10\x00\x00\x05\x00\x00" + b"\x00" * 8 + bytes([10, 0, 0, 1])
    ospf_payload = b"\x02\x01\x00\x18" + bytes([10, 0, 0, 2]) + bytes([0, 0, 0, 0]) + b"\x00" * 12
    vrrp_payload = b"\x21\x2a\x64\x01\x00\x00\x00\x00" + bytes([10, 0, 0, 1])
    carp_payload = b"\x10\x07\x64\x00\x00\x00\x00\x00"
    pcap_path = _write_pcap(
        tmp_path,
        _stp_frame(),
        _lacp_frame(),
        _ether(_ipv4_udp("10.0.0.2", "224.0.0.2", 1985, 1985, hsrp_payload)),
        _ether(_ipv4_proto("10.0.0.2", "224.0.0.5", 89, ospf_payload)),
        _ether(_ipv4_proto("10.0.0.3", "224.0.0.18", 112, vrrp_payload)),
        _ether(_ipv4_proto("10.0.0.4", "224.0.0.18", 112, carp_payload)),
    )

    evidence = parse_pcap_topology_evidence(pcap_path, observer="collector01")

    assert any(item["source"] == "stp" and item["metadata"]["root_bridge_id"] == "80:00:00:11:22:33:44:55" for item in evidence)
    assert any(item["source"] == "lacp" and item["metadata"]["partner_system"] == "66:77:88:99:aa:bb" for item in evidence)
    assert any(item["source"] == "hsrp" and item["gateway"] == "10.0.0.1" and item["metadata"]["group"] == 5 for item in evidence)
    assert any(item["source"] == "ospf" and item["metadata"]["router_id"] == "10.0.0.2" for item in evidence)
    assert any(item["source"] == "vrrp" and item["metadata"]["vrid"] == 42 for item in evidence)
    assert any(item["source"] == "carp" and item["metadata"]["routing_protocol"] == "carp" for item in evidence)


def test_parse_pcap_topology_evidence_aggregates_optional_flows(tmp_path):
    pcap_path = _write_pcap(
        tmp_path,
        _ether(_ipv4_tcp("10.0.0.2", "10.0.0.3", 51514, 443)),
        _ether(_ipv4_tcp("10.0.0.2", "10.0.0.3", 51514, 443)),
    )

    evidence = parse_pcap_topology_evidence(pcap_path, observer="collector01", include_flows=True)

    flows = [item for item in evidence if item["evidence_type"] == "flow_relationship"]
    assert len(flows) == 1
    assert flows[0]["metadata"]["packet_count"] == 2
    assert flows[0]["metadata"]["byte_count"] > 0
    assert flows[0]["metadata"]["tcp_syn"] is True


def test_collect_passive_capture_evidence_deletes_temporary_pcap(monkeypatch, tmp_path):
    capture_paths = []

    def fake_run_tcpdump_capture(interface, output_path, *, duration_seconds, packet_limit, include_flows):
        capture_paths.append(output_path)
        assert interface == "eth0"
        assert duration_seconds == 30
        assert packet_limit >= 1
        assert include_flows is False
        output_path.write_bytes(
            _pcap_packet(
                _ether(
                    _arp_reply(
                        "aa:bb:cc:dd:ee:01",
                        "10.0.0.2",
                        "aa:bb:cc:dd:ee:ff",
                        "10.0.0.1",
                    ),
                    ether_type=0x0806,
                )
            )
        )
        return True

    monkeypatch.setattr("agent.grapheon_agent.run_tcpdump_capture", fake_run_tcpdump_capture)
    monkeypatch.setattr("agent.grapheon_agent.socket.gethostname", lambda: "collector01")
    config = AgentConfig(
        server_url="https://grapheon.example.com",
        enrollment_key=None,
        state_dir=tmp_path,
        config_path=tmp_path / "agent.env",
        request_timeout_seconds=30,
        verify_tls=True,
        ca_file=None,
        display_name=None,
        site_name=None,
        hostname=None,
        timer_interval_seconds=900,
        api_key_header="X-Agent-Api-Key",
        user_agent=DEFAULT_USER_AGENT,
        ignore_local_net=False,
        topology_ignore_filters=["docker*"],
    )

    evidence = collect_passive_capture_evidence(
        config,
        {
            "enabled": True,
            "duration_seconds": 30,
            "max_bytes": 65536,
            "interfaces": ["eth0"],
        },
    )

    assert any(item["evidence_type"] == "mac_ip_binding" and item["observer"] == "collector01" for item in evidence)
    assert len(capture_paths) == 1
    assert not capture_paths[0].exists()


def test_default_route_capture_interfaces_uses_default_route_devices(monkeypatch):
    calls = []

    def fake_run_command(command, timeout_seconds):
        calls.append(command)
        if "-6" in command:
            return json.dumps(
                [
                    {"dst": "default", "gateway": "fe80::1", "dev": "wlan0"},
                    {"dst": "fe80::/64", "dev": "wlan0"},
                ]
            )
        return json.dumps(
            [
                {"dst": "default", "gateway": "10.0.0.1", "dev": "eth0"},
                {"dst": "10.0.0.0/24", "dev": "eth0"},
                {"dst": "default", "gateway": "172.17.0.1", "dev": "docker0"},
            ]
        )

    monkeypatch.setattr("agent.grapheon_agent.choose_command", lambda *commands: commands[0])
    monkeypatch.setattr("agent.grapheon_agent.run_command", fake_run_command)

    assert default_route_capture_interfaces() == ["eth0", "wlan0"]
    assert calls == [
        ["ip", "-json", "route", "show"],
        ["ip", "-json", "-6", "route", "show"],
    ]


def test_passive_capture_options_defaults_to_default_route_interface(monkeypatch, tmp_path):
    monkeypatch.setattr("agent.grapheon_agent.default_route_capture_interfaces", lambda ignore_filters=(): ["eth0"])
    config = AgentConfig(
        server_url="https://grapheon.example.com",
        enrollment_key=None,
        state_dir=tmp_path,
        config_path=tmp_path / "agent.env",
        request_timeout_seconds=30,
        verify_tls=True,
        ca_file=None,
        display_name=None,
        site_name=None,
        hostname=None,
        timer_interval_seconds=900,
        api_key_header="X-Agent-Api-Key",
        user_agent=DEFAULT_USER_AGENT,
        ignore_local_net=False,
    )

    options = passive_capture_options(
        config,
        {
            "enabled": True,
            "duration_seconds": 60,
            "interfaces": None,
        },
    )

    assert options["interfaces"] == ["eth0"]


def test_parse_ip_neigh_json_handles_state_arrays():
    payload = """
    [
      {"dst": "10.20.0.1", "lladdr": "11:22:33:44:55:66", "dev": "eth0", "state": ["REACHABLE"]},
      {"dst": "fe80::2", "lladdr": "22:33:44:55:66:77", "dev": "eth0", "state": "STALE"}
    ]
    """

    result = parse_ip_neigh_json(payload)

    assert result == [
        {
            "interface": "eth0",
            "ip_address": "10.20.0.1",
            "mac_address": "11:22:33:44:55:66",
            "state": "reachable",
        },
        {
            "interface": "eth0",
            "ip_address": "fe80::2",
            "mac_address": "22:33:44:55:66:77",
            "state": "stale",
        },
    ]


def test_parse_ss_output_extracts_pid_and_process_name():
    output = (
        'tcp ESTAB 0 0 10.20.0.5:443 10.20.0.10:51514 '
        'users:(("python",pid=777,fd=5))\n'
        'udp UNCONN 0 0 0.0.0.0:68 0.0.0.0:* '
        'users:(("dhclient",pid=101,fd=7))'
    )

    result = parse_ss_output(output)

    assert result == [
        {
            "local_ip": "0.0.0.0",
            "local_port": 68,
            "pid": 101,
            "process_name": "dhclient",
            "protocol": "udp",
            "remote_ip": "0.0.0.0",
            "remote_port": None,
            "state": "unknown",
        },
        {
            "local_ip": "10.20.0.5",
            "local_port": 443,
            "pid": 777,
            "process_name": "python",
            "protocol": "tcp",
            "remote_ip": "10.20.0.10",
            "remote_port": 51514,
            "state": "established",
        },
    ]


def test_parse_netstat_output_supports_udp_without_state():
    output = (
        "tcp        0      0 10.20.0.5:22       10.20.0.10:51514   ESTABLISHED 100/sshd\n"
        "udp        0      0 0.0.0.0:68         0.0.0.0:*                     101/dhclient"
    )

    result = parse_netstat_output(output)

    assert result == [
        {
            "local_ip": "0.0.0.0",
            "local_port": 68,
            "pid": 101,
            "process_name": "dhclient",
            "protocol": "udp",
            "remote_ip": "0.0.0.0",
            "remote_port": None,
            "state": "unknown",
        },
        {
            "local_ip": "10.20.0.5",
            "local_port": 22,
            "pid": 100,
            "process_name": "sshd",
            "protocol": "tcp",
            "remote_ip": "10.20.0.10",
            "remote_port": 51514,
            "state": "established",
        },
    ]


def test_build_snapshot_payload_returns_full_snapshot_every_time():
    current = {
        "addresses": [{"ip_address": "10.20.0.5"}],
        "neighbors": [{"ip_address": "10.20.0.1"}],
        "connections": [],
        "routes": [],
    }
    previous = {
        "addresses": [{"ip_address": "10.20.0.5"}],
        "neighbors": [],
        "connections": [],
        "routes": [],
    }

    first_payload, first_snapshot = build_snapshot_payload(current, {})
    repeated_payload, repeated_snapshot = build_snapshot_payload(current, previous)

    assert first_snapshot is True
    assert first_payload == current
    assert repeated_snapshot is True
    assert repeated_payload == current


def test_should_run_with_policy_respects_interval():
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    stale = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")

    policy = {"checkin_interval_seconds": 3600}

    assert should_run_with_policy({}, policy, timer_interval_seconds=900, force=False) is True
    assert (
        should_run_with_policy(
            {"last_successful_checkin_at": recent},
            policy,
            timer_interval_seconds=900,
            force=False,
        )
        is False
    )
    assert (
        should_run_with_policy(
            {"last_successful_checkin_at": stale},
            policy,
            timer_interval_seconds=900,
            force=False,
        )
        is True
    )
    assert (
        should_run_with_policy(
            {"last_successful_checkin_at": recent},
            policy,
            timer_interval_seconds=900,
            force=True,
        )
        is True
    )


def test_parse_timestamp_accepts_naive_and_utc_z():
    assert parse_timestamp("2026-03-22T18:00:00Z") is not None
    naive = parse_timestamp("2026-03-22T18:00:00")
    assert naive is not None
    assert naive.tzinfo == timezone.utc


def test_help_output_mentions_manual_modes_and_examples():
    script = Path(__file__).resolve().parents[1] / "grapheon_agent.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--register-only" in result.stdout
    assert "--check-in-only" in result.stdout
    assert "--ignore-local-net" in result.stdout
    assert "--user-agent" in result.stdout
    assert "Examples:" in result.stdout
    assert "python3 agent/grapheon_agent.py" in result.stdout
    assert "/opt/grapheon/agent/current/grapheon_agent.py" in result.stdout


def test_build_config_uses_default_user_agent(monkeypatch, tmp_path):
    monkeypatch.delenv("GRAPHEON_AGENT_SERVER_URL", raising=False)
    monkeypatch.delenv("GRAPHEON_AGENT_USER_AGENT", raising=False)
    args = parse_args(
        [
            "--server-url",
            "https://grapheon.example.com",
            "--state-dir",
            str(tmp_path),
            "--config",
            str(tmp_path / "missing.env"),
        ]
    )

    config = build_config(args)

    assert config.user_agent == DEFAULT_USER_AGENT


def test_main_logs_agent_version_on_startup(monkeypatch, caplog):
    monkeypatch.setattr("agent.grapheon_agent.build_config", lambda args: object())
    monkeypatch.setattr("agent.grapheon_agent.run_agent", lambda *args, **kwargs: 0)

    with caplog.at_level("INFO", logger="grapheon_agent"):
        assert main(["--log-level", "INFO"]) == 0

    assert f"Starting Graphēon passive agent version {AGENT_VERSION}" in caplog.text


def test_build_config_reads_user_agent_from_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("GRAPHEON_AGENT_SERVER_URL", raising=False)
    monkeypatch.delenv("GRAPHEON_AGENT_USER_AGENT", raising=False)
    env_file = tmp_path / "agent.env"
    env_file.write_text(
        "\n".join(
            [
                "GRAPHEON_AGENT_SERVER_URL=https://grapheon.example.com",
                "GRAPHEON_AGENT_USER_AGENT=Custom-Agent/1.0",
            ]
        )
    )
    args = parse_args(["--config", str(env_file), "--state-dir", str(tmp_path)])

    config = build_config(args)

    assert config.user_agent == "Custom-Agent/1.0"


def test_build_config_reads_ignore_local_net_from_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("GRAPHEON_AGENT_SERVER_URL", raising=False)
    monkeypatch.delenv("GRAPHEON_AGENT_IGNORE_LOCAL_NET", raising=False)
    env_file = tmp_path / "agent.env"
    env_file.write_text(
        "\n".join(
            [
                "GRAPHEON_AGENT_SERVER_URL=https://grapheon.example.com",
                "GRAPHEON_AGENT_IGNORE_LOCAL_NET=true",
            ]
        )
    )
    args = parse_args(["--config", str(env_file), "--state-dir", str(tmp_path)])

    config = build_config(args)

    assert config.ignore_local_net is True


def test_build_config_cli_user_agent_overrides_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("GRAPHEON_AGENT_SERVER_URL", raising=False)
    monkeypatch.delenv("GRAPHEON_AGENT_USER_AGENT", raising=False)
    env_file = tmp_path / "agent.env"
    env_file.write_text(
        "\n".join(
            [
                "GRAPHEON_AGENT_SERVER_URL=https://grapheon.example.com",
                "GRAPHEON_AGENT_USER_AGENT=Env-Agent/1.0",
            ]
        )
    )
    args = parse_args(
        [
            "--config",
            str(env_file),
            "--state-dir",
            str(tmp_path),
            "--user-agent",
            "Cli-Agent/2.0",
        ]
    )

    config = build_config(args)

    assert config.user_agent == "Cli-Agent/2.0"


def test_http_json_sends_configured_user_agent(monkeypatch, tmp_path):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(req, timeout, context):
        captured["request"] = req
        captured["timeout"] = timeout
        captured["context"] = context
        return FakeResponse()

    monkeypatch.setattr("agent.grapheon_agent.request.urlopen", fake_urlopen)
    config = AgentConfig(
        server_url="https://grapheon.example.com",
        enrollment_key=None,
        state_dir=tmp_path,
        config_path=tmp_path / "agent.env",
        request_timeout_seconds=30,
        verify_tls=True,
        ca_file=None,
        display_name=None,
        site_name=None,
        hostname=None,
        timer_interval_seconds=900,
        api_key_header="X-Agent-Api-Key",
        user_agent="Custom-Agent/1.0",
        ignore_local_net=False,
    )

    http_json(
        config,
        "POST",
        "api/agents/check-in",
        {"agent_uuid": "agent-1"},
        headers={"X-Agent-Api-Key": "secret"},
        compress=True,
    )

    headers = {key.lower(): value for key, value in captured["request"].header_items()}
    assert headers["user-agent"] == "Custom-Agent/1.0"
    assert headers["x-agent-api-key"] == "secret"
    assert headers["content-encoding"] == "gzip"


def test_run_agent_polls_before_skipping_for_cached_interval(monkeypatch, tmp_path):
    (tmp_path / "agent_uuid").write_text("agent-poll-1\n")
    (tmp_path / "api_key").write_text("secret\n")
    recent = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "last_successful_checkin_at": recent,
                "policy": {"checkin_interval_seconds": 3600},
            }
        )
    )
    calls = []

    def fake_poll(config, api_key, agent_uuid_value):
        calls.append((api_key, agent_uuid_value))
        return {
            "policy": {"checkin_interval_seconds": 3600},
            "collection_request": {"requested": False},
        }

    monkeypatch.setattr("agent.grapheon_agent.poll_agent_control", fake_poll)
    monkeypatch.setattr(
        "agent.grapheon_agent.build_current_snapshot",
        lambda policy, config, ignore_local_net=False, passive_capture_request=None: pytest.fail("collection should not run"),
    )
    config = AgentConfig(
        server_url="https://grapheon.example.com",
        enrollment_key=None,
        state_dir=tmp_path,
        config_path=tmp_path / "agent.env",
        request_timeout_seconds=30,
        verify_tls=True,
        ca_file=None,
        display_name=None,
        site_name=None,
        hostname=None,
        timer_interval_seconds=900,
        api_key_header="X-Agent-Api-Key",
        user_agent=DEFAULT_USER_AGENT,
        ignore_local_net=False,
    )

    assert run_agent(config, force=False) == 0
    assert calls == [("secret", "agent-poll-1")]


def test_run_agent_on_demand_request_bypasses_cached_interval_and_jitter(monkeypatch, tmp_path):
    (tmp_path / "agent_uuid").write_text("agent-poll-2\n")
    (tmp_path / "api_key").write_text("secret\n")
    recent = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "last_successful_checkin_at": recent,
                "policy": {"checkin_interval_seconds": 3600, "jitter_seconds": 300},
            }
        )
    )
    checkins = []

    def fake_poll(config, api_key, agent_uuid_value):
        return {
            "policy": {"checkin_interval_seconds": 3600, "jitter_seconds": 300},
            "collection_request": {
                "requested": True,
                "requested_at": "2026-06-11T12:00:00Z",
            },
        }

    def fake_check_in(config, api_key, payload):
        checkins.append(payload)
        return {
            "server_time": "2026-06-11T12:01:00Z",
            "summary": {"accepted": True},
            "policy": {"checkin_interval_seconds": 3600, "jitter_seconds": 300},
        }

    monkeypatch.setattr("agent.grapheon_agent.poll_agent_control", fake_poll)
    monkeypatch.setattr(
        "agent.grapheon_agent.maybe_sleep_for_policy_jitter",
        lambda policy: pytest.fail("on-demand collection must not sleep for jitter"),
    )
    monkeypatch.setattr(
        "agent.grapheon_agent.build_current_snapshot",
        lambda policy, config, ignore_local_net=False, passive_capture_request=None: {
            "addresses": [],
            "neighbors": [],
            "connections": [],
            "routes": [],
            "topology_evidence": [],
        },
    )
    monkeypatch.setattr("agent.grapheon_agent.check_in_agent", fake_check_in)
    config = AgentConfig(
        server_url="https://grapheon.example.com",
        enrollment_key=None,
        state_dir=tmp_path,
        config_path=tmp_path / "agent.env",
        request_timeout_seconds=30,
        verify_tls=True,
        ca_file=None,
        display_name=None,
        site_name=None,
        hostname=None,
        timer_interval_seconds=900,
        api_key_header="X-Agent-Api-Key",
        user_agent=DEFAULT_USER_AGENT,
        ignore_local_net=False,
    )

    assert run_agent(config, force=False) == 0
    assert len(checkins) == 1
    assert checkins[0]["agent_uuid"] == "agent-poll-2"
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["last_collection_request_at"] == "2026-06-11T12:00:00Z"
    assert state["last_jitter_seconds"] == 0


def test_run_agent_recovers_invalid_local_api_key_with_enrollment(monkeypatch, tmp_path):
    (tmp_path / "agent_uuid").write_text("agent-recover-1\n")
    (tmp_path / "api_key").write_text("stale-secret\n")
    registrations = []
    checkins = []

    def fake_poll(config, api_key, agent_uuid_value):
        assert api_key == "stale-secret"
        raise RuntimeError(
            'HTTP 401 calling api/agents/poll: {"detail":"Invalid agent API key"}'
        )

    def fake_register(config, agent_uuid_value):
        registrations.append(agent_uuid_value)
        return {
            "status": "active",
            "api_key": "new-secret",
            "agent": {"id": 42, "enrollment_state": "active"},
            "policy": {"checkin_interval_seconds": 3600, "jitter_seconds": 0},
        }

    def fake_check_in(config, api_key, payload):
        checkins.append((api_key, payload))
        return {
            "server_time": "2026-06-11T12:01:00Z",
            "summary": {"accepted": True},
            "policy": {"checkin_interval_seconds": 3600, "jitter_seconds": 0},
        }

    monkeypatch.setattr("agent.grapheon_agent.poll_agent_control", fake_poll)
    monkeypatch.setattr("agent.grapheon_agent.register_agent", fake_register)
    monkeypatch.setattr("agent.grapheon_agent.maybe_sleep_for_policy_jitter", lambda policy: 0)
    monkeypatch.setattr(
        "agent.grapheon_agent.build_current_snapshot",
        lambda policy, config, ignore_local_net=False, passive_capture_request=None: {
            "addresses": [],
            "neighbors": [],
            "connections": [],
            "routes": [],
            "topology_evidence": [],
        },
    )
    monkeypatch.setattr("agent.grapheon_agent.check_in_agent", fake_check_in)
    config = AgentConfig(
        server_url="https://grapheon.example.com",
        enrollment_key="gaek_recovery",
        state_dir=tmp_path,
        config_path=tmp_path / "agent.env",
        request_timeout_seconds=30,
        verify_tls=True,
        ca_file=None,
        display_name=None,
        site_name=None,
        hostname=None,
        timer_interval_seconds=900,
        api_key_header="X-Agent-Api-Key",
        user_agent=DEFAULT_USER_AGENT,
        ignore_local_net=False,
    )

    assert run_agent(config, force=True) == 0
    assert registrations == ["agent-recover-1"]
    assert (tmp_path / "api_key").read_text(encoding="utf-8").strip() == "new-secret"
    assert checkins[0][0] == "new-secret"


def test_check_in_only_requires_existing_api_key(tmp_path):
    config = AgentConfig(
        server_url="https://grapheon.example.com",
        enrollment_key=None,
        state_dir=tmp_path,
        config_path=tmp_path / "agent.env",
        request_timeout_seconds=30,
        verify_tls=True,
        ca_file=None,
        display_name=None,
        site_name=None,
        hostname=None,
        timer_interval_seconds=900,
        api_key_header="X-Agent-Api-Key",
        user_agent=DEFAULT_USER_AGENT,
        ignore_local_net=False,
    )

    with pytest.raises(RuntimeError, match="existing local agent API key"):
        run_agent(config, force=False, check_in_only=True)
