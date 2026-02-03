"""Tests for tag-based correlation rules."""

from models import Host
from services.correlation import _group_hosts_by_tags, _should_merge_by_tag


def _host(ip, hostname=None, fqdn=None, mac=None, tags=None):
    host = Host(ip_address=ip)
    host.hostname = hostname
    host.fqdn = fqdn
    host.mac_address = mac
    host.tags = tags or []
    host.is_active = True
    return host


def test_group_hosts_by_tags_only_high_confidence():
    host_a = _host("10.0.0.1", tags=["hostname:alpha", "ip:10.0.0.1"]) 
    host_b = _host("10.0.0.2", tags=["fqdn:alpha.local", "subnet:10.0.0.0/24"])

    groups = _group_hosts_by_tags([host_a, host_b])

    assert "hostname:alpha" in groups
    assert "fqdn:alpha.local" in groups
    assert "ip:10.0.0.1" not in groups
    assert "subnet:10.0.0.0/24" not in groups


def test_should_merge_by_tag_allows_hostname_without_mac_conflict():
    tag = "hostname:router"
    primary = _host("10.0.0.1", hostname="router", mac=None)
    secondary = _host("10.0.0.2", hostname="router", mac=None)

    assert _should_merge_by_tag(primary, secondary, tag) is True


def test_should_merge_by_tag_rejects_conflicting_macs():
    tag = "hostname:router"
    primary = _host("10.0.0.1", hostname="router", mac="AA:BB:CC:DD:EE:FF")
    secondary = _host("10.0.0.2", hostname="router", mac="11:22:33:44:55:66")

    assert _should_merge_by_tag(primary, secondary, tag) is False


def test_should_merge_by_tag_rejects_ambiguous_hostname():
    tag = "hostname:localhost"
    primary = _host("127.0.0.1", hostname="localhost")
    secondary = _host("192.168.1.10", hostname="localhost")

    assert _should_merge_by_tag(primary, secondary, tag) is False
