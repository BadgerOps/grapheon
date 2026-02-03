"""
Simple test script to verify the API is working.
This can be run after starting the server with: python main.py
"""

import os
import httpx
import asyncio
import json
import pytest


BASE_URL = "http://localhost:8000"

pytestmark = [pytest.mark.anyio, pytest.mark.integration]

if os.getenv("RUN_API_TESTS") != "1":
    pytest.skip(
        "API tests require a running server. Set RUN_API_TESTS=1 to enable.",
        allow_module_level=True,
    )


@pytest.fixture
async def client():
    async with httpx.AsyncClient() as async_client:
        yield async_client


@pytest.fixture
async def host_id(client: httpx.AsyncClient):
    host_data = {
        "ip_address": "192.168.1.100",
        "hostname": "test-host",
        "mac_address": "00:11:22:33:44:55",
        "os_name": "Ubuntu",
        "os_version": "22.04",
        "os_family": "linux",
        "device_type": "workstation",
        "criticality": "medium",
        "tags": ["test", "demo"],
    }

    response = await client.post(f"{BASE_URL}/api/hosts", json=host_data)
    assert response.status_code == 201
    data = response.json()
    return data["id"]


@pytest.fixture
async def import_id(client: httpx.AsyncClient):
    raw_data = """
    Nmap scan results:
    Host: 192.168.1.50 (router.local)
    MAC Address: AA:BB:CC:DD:EE:FF
    Port 22: Open SSH
    Port 80: Open HTTP
    """

    response = await client.post(
        f"{BASE_URL}/api/import/raw",
        data={
            "source_type": "nmap",
            "raw_data": raw_data,
            "tags": "test,demo",
            "notes": "Test import",
        },
    )
    assert response.status_code == 201
    data = response.json()
    return data["id"]


async def test_health(client: httpx.AsyncClient):
    """Test health check endpoint."""
    print("\n=== Testing Health Check ===")
    response = await client.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200


async def test_api_root(client: httpx.AsyncClient):
    """Test API root endpoint."""
    print("\n=== Testing API Root ===")
    response = await client.get(f"{BASE_URL}/api")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200


async def test_create_host(host_id: int):
    """Test creating a host."""
    print("\n=== Testing Create Host ===")
    assert host_id is not None


async def test_list_hosts(client: httpx.AsyncClient):
    """Test listing hosts."""
    print("\n=== Testing List Hosts ===")
    response = await client.get(f"{BASE_URL}/api/hosts?skip=0&limit=10")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Total hosts: {data['total']}")
    print(f"Items returned: {len(data['items'])}")
    if data["items"]:
        print(f"First host: {json.dumps(data['items'][0], indent=2, default=str)}")


async def test_get_host(client: httpx.AsyncClient, host_id: int):
    """Test getting a specific host."""
    print(f"\n=== Testing Get Host {host_id} ===")
    response = await client.get(f"{BASE_URL}/api/hosts/{host_id}")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2, default=str)}")


async def test_update_host(client: httpx.AsyncClient, host_id: int):
    """Test updating a host."""
    print(f"\n=== Testing Update Host {host_id} ===")

    update_data = {
        "hostname": "updated-hostname",
        "criticality": "high",
    }

    response = await client.put(
        f"{BASE_URL}/api/hosts/{host_id}",
        json=update_data,
    )
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2, default=str)}")


async def test_import_raw_data(import_id: int):
    """Test importing raw data."""
    print("\n=== Testing Import Raw Data ===")
    assert import_id is not None


async def test_list_imports(client: httpx.AsyncClient):
    """Test listing imports."""
    print("\n=== Testing List Imports ===")
    response = await client.get(f"{BASE_URL}/api/imports?skip=0&limit=10")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Total imports: {data['total']}")
    print(f"Items returned: {len(data['items'])}")
    if data["items"]:
        print(f"First import: {json.dumps(data['items'][0], indent=2, default=str)}")


async def test_get_import(client: httpx.AsyncClient, import_id: int):
    """Test getting a specific import."""
    print(f"\n=== Testing Get Import {import_id} ===")
    response = await client.get(f"{BASE_URL}/api/imports/{import_id}")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Import metadata: {json.dumps(data['import'], indent=2, default=str)}")
    print(f"Raw data length: {len(data['raw_data'])} characters")


async def main():
    """Run all tests."""
    print("Graphēon - API Test Suite")
    print("=" * 50)

    try:
        # Test basic endpoints
        await test_health()
        await test_api_root()

        # Test host endpoints
        host_id = await test_create_host()
        await test_list_hosts()

        if host_id:
            await test_get_host(host_id)
            await test_update_host(host_id)

        # Test import endpoints
        import_id = await test_import_raw_data()
        await test_list_imports()

        if import_id:
            await test_get_import(import_id)

        print("\n" + "=" * 50)
        print("All tests completed successfully!")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("Note: Make sure the server is running first!")
    print("Run: python main.py")
    input("Press Enter to continue with tests...")
    asyncio.run(main())
