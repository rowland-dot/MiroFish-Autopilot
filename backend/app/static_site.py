"""Single-container mode: serve the built Vue SPA from Flask alongside /api.

When a built frontend (dist folder) exists — the Hugging Face deployment —
Flask serves it with SPA fallback so Vue Router paths deep-link correctly.
/api/* is never swallowed (unknown API paths stay JSON 404s). When the dist
folder is absent (local dev with Vite on :3000), this is a no-op.
"""

import os

from flask import abort, send_from_directory


def init_static_site(app, dist_dir: str) -> None:
    """Register SPA-serving routes if a built frontend exists at dist_dir."""
    dist = os.path.abspath(dist_dir)
    if not os.path.isfile(os.path.join(dist, "index.html")):
        return  # 本地开发（Vite 独立服务前端）：不注册任何路由

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def _spa(path):
        # API 路径永不回退到 index.html——保持 JSON 404 语义
        if path == "api" or path.startswith("api/"):
            abort(404)
        candidate = os.path.join(dist, path)
        if path and os.path.isfile(candidate):
            return send_from_directory(dist, path)
        return send_from_directory(dist, "index.html")
