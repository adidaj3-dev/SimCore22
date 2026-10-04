"""Shared helpers for tests that drive the web app as a logged-in person."""
from fastapi.testclient import TestClient

from simcore22.league import accounts
from simcore22.league.demo_seed import DEMO_ADMIN_EMAIL, DEMO_PASSWORD
from simcore22.web import auth

PASSWORD = "correct horse battery"
CSRF = {auth.CSRF_HEADER: auth.CSRF_VALUE}


def make_client(app, **kw) -> TestClient:
    """A test client that sends the anti-forgery header the real pages send."""
    return TestClient(app, headers=dict(CSRF), **kw)


def add_user(app, email, name, role="player", **kw):
    with app.state.db.connect() as conn:
        return accounts.create_user(conn, email=email, password=PASSWORD, display_name=name, role=role, **kw)


def login(client: TestClient, email: str, password: str = PASSWORD):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["user"]


def admin_client(app) -> TestClient:
    """A client logged in as a venue admin (the demo's own admin when the app is a demo)."""
    client = make_client(app)
    if app.state.demo_venue is not None:
        login(client, DEMO_ADMIN_EMAIL, DEMO_PASSWORD)
    else:
        add_user(app, "boss@example.com", "Venue Boss", role="admin")
        login(client, "boss@example.com")
    return client
