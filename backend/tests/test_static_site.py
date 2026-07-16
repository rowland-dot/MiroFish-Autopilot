"""TDD: single-container mode — Flask serves the built Vue SPA + /api together.

init_static_site(app, dist_dir): when a built frontend exists, serve it with
SPA fallback; never swallow /api/* (JSON 404s stay JSON); no-op when the dist
folder is absent (local dev unchanged). Works with the access gate: unauthed
page requests still get the cover page.

Spec context: HF single-container deployment.
"""
from flask import Flask, jsonify

from app.static_site import init_static_site
from app.auth import init_auth


def make_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>SPA-INDEX</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('bundle')", encoding="utf-8")
    return str(dist)


def make_app(dist_dir, **config):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "t"
    app.config["AUTH_FAIL_DELAY"] = 0
    app.config.update(config)
    init_auth(app)

    @app.route("/api/data")
    def api_data():
        return jsonify(ok=True)

    init_static_site(app, dist_dir)
    return app.test_client()


def test_no_dist_dir_is_a_noop(tmp_path):
    c = make_app(str(tmp_path / "missing"))
    assert c.get("/").status_code == 404  # nothing registered


def test_serves_index_at_root(tmp_path):
    c = make_app(make_dist(tmp_path))
    r = c.get("/")
    assert r.status_code == 200
    assert b"SPA-INDEX" in r.data


def test_serves_asset_files(tmp_path):
    c = make_app(make_dist(tmp_path))
    r = c.get("/assets/app.js")
    assert r.status_code == 200
    assert b"bundle" in r.data


def test_spa_fallback_for_client_routes(tmp_path):
    c = make_app(make_dist(tmp_path))
    r = c.get("/report/report_abc123")
    assert r.status_code == 200
    assert b"SPA-INDEX" in r.data  # Vue router takes over client-side


def test_api_paths_never_fall_back_to_index(tmp_path):
    c = make_app(make_dist(tmp_path))
    ok = c.get("/api/data")
    assert ok.status_code == 200 and ok.is_json
    missing = c.get("/api/nope")
    assert missing.status_code == 404
    assert b"SPA-INDEX" not in missing.data


def test_gate_on_shows_cover_page_not_spa(tmp_path):
    c = make_app(make_dist(tmp_path), AUTH_ENABLED=True, ACCESS_CODE="s3cret")
    r = c.get("/")
    assert b"SPA-INDEX" not in r.data
    assert b"Access code" in r.data
    # login then the SPA is served
    assert c.post("/api/auth/login", json={"code": "s3cret"}).status_code == 200
    assert b"SPA-INDEX" in c.get("/").data
