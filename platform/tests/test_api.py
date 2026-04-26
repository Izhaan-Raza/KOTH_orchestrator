import os
import pytest
from fastapi.testclient import TestClient

# Set test DB before importing app
os.environ["DB_PATH"] = "test_platform.db"

from app import app
from engine.db import apply_migrations

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_teardown():
    # Setup
    if os.path.exists("test_platform.db"):
        os.remove("test_platform.db")
    migrations_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations")
    apply_migrations("test_platform.db", migrations_dir)
    
    yield
    
    # Teardown
    if os.path.exists("test_platform.db"):
        os.remove("test_platform.db")

def test_setup_status_initially_false():
    response = client.get("/api/setup/status")
    assert response.status_code == 200
    assert response.json()["is_setup"] == False

def test_legacy_status_endpoint():
    # legacy.router is protected now, so we need an API key
    os.environ["ADMIN_API_KEY"] = "test-key-123"
    response = client.get("/api/status", headers={"X-API-Key": "test-key-123"})
    assert response.status_code == 200
    assert response.json()["competition_status"] == "running"

def test_setup_initialize_creates_admin():
    payload = {
        "admin_username": "test_admin",
        "admin_password": "test_password",
        "node_name": "test_node",
        "node_ip": "10.0.0.1",
        "node_user": "root",
        "load_examples": False
    }
    response = client.post("/api/setup/initialize", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "initialized"

    # Now status should be true
    status_resp = client.get("/api/setup/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["is_setup"] == True

def test_unauthorized_access_to_protected_routes():
    # Attempt to hit /api/nodes without the X-Admin-Key header
    response = client.get("/api/nodes")
    assert response.status_code == 401

def test_authorized_access_with_admin_key():
    # First set an admin key in the environment or app
    os.environ["ADMIN_API_KEY"] = "secret123"
    
    # Needs to hit a protected route
    headers = {"X-API-Key": "secret123"}
    response = client.get("/api/nodes", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
