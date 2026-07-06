"""TDD: environment-gated access passcode.

The gate is wired onto any Flask app via init_auth(app). Tests use a bare app
(no heavy MiroFish imports) so they exercise the real before_request wiring
fast. Config comes from app.config so tests can toggle it directly.
"""
from flask import Flask, jsonify

from app.auth import init_auth


def make_app(**config):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    app.config["AUTH_FAIL_DELAY"] = 0  # no sleep in tests
    app.config.update(config)
    init_auth(app)

    @app.route("/protected")
    def protected():
        return "SECRET CONTENT"

    @app.route("/api/data")
    def api_data():
        return jsonify(ok=True)

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    return app


def test_gate_off_allows_page_and_api():
    c = make_app(AUTH_ENABLED=False, ACCESS_CODE="x").test_client()
    assert c.get("/protected").data == b"SECRET CONTENT"
    assert c.get("/api/data").status_code == 200


def test_gate_on_serves_cover_page_for_unauthed_page():
    r = make_app(AUTH_ENABLED=True, ACCESS_CODE="secret").test_client().get("/protected")
    assert r.status_code == 200
    assert b"SECRET CONTENT" not in r.data     # real content withheld
    assert b"Access code" in r.data            # cover page shown


def test_gate_on_returns_401_json_for_unauthed_api():
    r = make_app(AUTH_ENABLED=True, ACCESS_CODE="secret").test_client().get("/api/data")
    assert r.status_code == 401
    assert r.is_json


def test_health_and_login_are_exempt():
    c = make_app(AUTH_ENABLED=True, ACCESS_CODE="secret").test_client()
    assert c.get("/health").status_code == 200
    # login endpoint must be reachable without a session (it's how you get in)
    assert c.post("/api/auth/login", json={"code": "wrong"}).status_code == 401


def test_correct_code_unlocks_the_app():
    c = make_app(AUTH_ENABLED=True, ACCESS_CODE="secret").test_client()
    assert b"SECRET CONTENT" not in c.get("/protected").data      # gated first
    assert c.post("/api/auth/login", json={"code": "secret"}).status_code == 200
    assert c.get("/protected").data == b"SECRET CONTENT"          # now open
    assert c.get("/api/data").status_code == 200


def test_wrong_code_is_rejected():
    r = make_app(AUTH_ENABLED=True, ACCESS_CODE="secret").test_client().post(
        "/api/auth/login", json={"code": "nope"}
    )
    assert r.status_code == 401


def test_empty_access_code_never_authenticates():
    # Guards against a misconfigured deploy where ACCESS_CODE is blank.
    c = make_app(AUTH_ENABLED=True, ACCESS_CODE="").test_client()
    assert c.post("/api/auth/login", json={"code": ""}).status_code == 401
    assert c.get("/api/data").status_code == 401


def test_logout_re_locks():
    c = make_app(AUTH_ENABLED=True, ACCESS_CODE="secret").test_client()
    c.post("/api/auth/login", json={"code": "secret"})
    assert c.get("/api/data").status_code == 200
    c.post("/api/auth/logout")
    assert c.get("/api/data").status_code == 401
