"""Tests for tagging utilities."""

from utils.tagging import (
    build_host_tags,
    build_port_tags,
    build_connection_tags,
    build_arp_tags,
    merge_tags,
)


def test_build_host_tags():
    tags = build_host_tags(
        ip_address="10.0.0.1",
        mac_address="AA:BB:CC:DD:EE:FF",
        hostname="router.local",
        fqdn="router.local",
        vendor="Cisco Systems",
        os_family="linux",
        os_name="Ubuntu 22.04",
    )

    assert "ip:10.0.0.1" in tags
    assert "subnet:10.0.0.0/24" in tags
    assert "mac:aa:bb:cc:dd:ee:ff" in tags
    assert "hostname:router.local" in tags
    assert "vendor:cisco_systems" in tags
    assert "os_family:linux" in tags
    assert "os:ubuntu_22.04" in tags


def test_build_port_tags():
    tags = build_port_tags(
        port_number=22,
        protocol="tcp",
        state="open",
        service_name="ssh",
        service_product="OpenSSH",
        service_version="9.6",
    )

    assert "port:22" in tags
    assert "port_proto:22/tcp" in tags
    assert "protocol:tcp" in tags
    assert "state:open" in tags
    assert "service:ssh" in tags
    assert "product:openssh" in tags
    assert "version:9.6" in tags


def test_build_connection_tags():
    tags = build_connection_tags(
        local_ip="10.0.0.1",
        local_port=443,
        remote_ip="10.0.0.2",
        remote_port=51123,
        protocol="tcp",
        state="ESTABLISHED",
        process_name="nginx",
    )

    assert "local_ip:10.0.0.1" in tags
    assert "local_port:443" in tags
    assert "local_subnet:10.0.0.0/24" in tags
    assert "remote_ip:10.0.0.2" in tags
    assert "remote_port:51123" in tags
    assert "remote_subnet:10.0.0.0/24" in tags
    assert "protocol:tcp" in tags
    assert "state:established" in tags
    assert "process:nginx" in tags


def test_build_arp_tags():
    tags = build_arp_tags(
        ip_address="192.168.1.5",
        mac_address="00:11:22:33:44:55",
        interface="en0",
        entry_type="dynamic",
        vendor="Apple",
    )

    assert "ip:192.168.1.5" in tags
    assert "subnet:192.168.1.0/24" in tags
    assert "mac:00:11:22:33:44:55" in tags
    assert "interface:en0" in tags
    assert "entry_type:dynamic" in tags
    assert "vendor:apple" in tags


def test_merge_tags_unique_and_sorted():
    merged = merge_tags(["ip:10.0.0.1", "service:ssh"], ["service:ssh", "port:22"])
    assert merged == ["ip:10.0.0.1", "port:22", "service:ssh"]
