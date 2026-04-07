import pytest

@pytest.mark.anyio
async def test_register_email(client):
    resp = await client.post("/auth/register", json={
        "name": "TestUser",
        "email": "test@example.com",
        "password": "securepass123"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["name"] == "TestUser"
    assert data["user"]["soul_coin_balance"] == 100

@pytest.mark.anyio
async def test_login_email(client):
    await client.post("/auth/register", json={
        "name": "TestUser", "email": "login@example.com", "password": "securepass123"
    })
    resp = await client.post("/auth/login", json={
        "email": "login@example.com", "password": "securepass123"
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()

@pytest.mark.anyio
async def test_login_wrong_password(client):
    await client.post("/auth/register", json={
        "name": "U", "email": "wrong@example.com", "password": "correct"
    })
    resp = await client.post("/auth/login", json={
        "email": "wrong@example.com", "password": "incorrect"
    })
    assert resp.status_code == 401

@pytest.mark.anyio
async def test_get_me(client):
    reg = await client.post("/auth/register", json={
        "name": "Me", "email": "me@example.com", "password": "pass123"
    })
    token = reg.json()["access_token"]
    resp = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"

@pytest.mark.anyio
async def test_get_me_no_token(client):
    resp = await client.get("/users/me")
    assert resp.status_code == 401

@pytest.mark.anyio
async def test_register_duplicate_email(client):
    await client.post("/auth/register", json={"name": "A", "email": "dup@example.com", "password": "pass123"})
    resp = await client.post("/auth/register", json={"name": "B", "email": "dup@example.com", "password": "pass123"})
    assert resp.status_code == 409
