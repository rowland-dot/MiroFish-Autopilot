"""Environment-gated access passcode.

Wired onto a Flask app via ``init_auth(app)``. When ``app.config['AUTH_ENABLED']``
is false (the local default) the gate is inert and every route behaves as before.
When true (the live deploy, or local testing) unauthenticated requests are
blocked — page requests receive a cover page, API requests receive ``401`` — until
the shared ``ACCESS_CODE`` is entered, which sets a signed 7-day session.
"""

import hmac
import time
from datetime import timedelta

from flask import Response, jsonify, request, session

# Reachable without a session: the login route (so you can get in), static
# assets, and health checks.
_EXEMPT_PREFIXES = ("/api/auth/", "/static/", "/assets/")
_EXEMPT_EXACT = ("/health",)


def _is_exempt(path: str) -> bool:
    return path in _EXEMPT_EXACT or path.startswith(_EXEMPT_PREFIXES)


def init_auth(app) -> None:
    """Register the access gate and login/logout routes on a Flask app."""
    app.permanent_session_lifetime = timedelta(days=7)

    @app.before_request
    def _gate():
        if not app.config.get("AUTH_ENABLED"):
            return None
        if _is_exempt(request.path):
            return None
        if session.get("authed"):
            return None
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "Access code required"}), 401
        return Response(_COVER_PAGE_HTML, mimetype="text/html")

    @app.route("/api/auth/login", methods=["POST"])
    def _login():
        data = request.get_json(silent=True) or request.form
        submitted = str(data.get("code", ""))
        expected = str(app.config.get("ACCESS_CODE") or "")
        # A blank ACCESS_CODE must never authenticate (misconfigured-deploy guard);
        # constant-time compare avoids leaking the code length via timing.
        if expected and hmac.compare_digest(submitted, expected):
            session["authed"] = True
            session.permanent = True
            return jsonify({"success": True})
        # Small delay to deter brute-forcing; set AUTH_FAIL_DELAY=0 in tests.
        delay = app.config.get("AUTH_FAIL_DELAY", 1.0)
        if delay:
            time.sleep(delay)
        return jsonify({"success": False, "error": "Incorrect code"}), 401

    @app.route("/api/auth/logout", methods=["POST"])
    def _logout():
        session.pop("authed", None)
        return jsonify({"success": True})


_COVER_PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MiroFish — Access</title>
<style>
  :root{--accent:#FF5722;--bad:#C2283B;--muted:#666;--faint:#999;--line:#E5E7EB;
    --sans:'Space Grotesk','Noto Sans SC',system-ui,sans-serif;--mono:'JetBrains Mono',ui-monospace,monospace;}
  *{box-sizing:border-box;}
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
    background:#FCFCFB;font-family:var(--sans);color:#000;}
  .brand{position:fixed;top:22px;left:24px;font-family:var(--mono);font-weight:800;font-size:16px;letter-spacing:1px;}
  .brand .dot{color:var(--accent);}
  .card{width:330px;text-align:center;padding:6px 8px;}
  .lock{width:44px;height:44px;border-radius:12px;background:#111;color:#fff;display:flex;
    align-items:center;justify-content:center;margin:0 auto 18px;font-size:20px;}
  h1{font-size:20px;font-weight:700;margin:0 0 6px;letter-spacing:-.01em;}
  .sub{font-size:13px;color:var(--muted);line-height:1.55;margin:0 0 22px;}
  .lbl{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);
    display:block;text-align:left;margin:0 0 6px;}
  input{width:100%;height:44px;border:1.5px solid var(--line);border-radius:9px;padding:0 14px;
    font-family:var(--mono);font-size:14px;letter-spacing:.2em;background:#fff;outline:none;}
  input:focus{border-color:var(--accent);}
  input.err{border-color:var(--bad);}
  .err{color:var(--bad);font-size:12px;font-weight:600;margin-top:8px;text-align:left;min-height:16px;}
  button{width:100%;height:44px;margin-top:14px;border:none;border-radius:9px;background:#111;color:#fff;
    font:600 13.5px var(--sans);cursor:pointer;}
  .foot{position:fixed;bottom:18px;font-size:11px;color:var(--faint);font-family:var(--mono);}
</style>
</head>
<body>
  <div class="brand">MIRO<span class="dot">&middot;</span>FISH</div>
  <div class="card">
    <div class="lock">&#128274;</div>
    <h1>Restricted access</h1>
    <p class="sub">This is a private team instance. Enter the access code to continue.</p>
    <label class="lbl" for="code">Access code</label>
    <input id="code" type="password" placeholder="&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;" autofocus autocomplete="off">
    <div class="err" id="err"></div>
    <button id="go">Enter &rarr;</button>
  </div>
  <div class="foot">team use only &middot; powered by MiroFish</div>
<script>
  const inp=document.getElementById('code'),err=document.getElementById('err'),btn=document.getElementById('go');
  async function submit(){
    err.textContent='';inp.classList.remove('err');btn.disabled=true;
    try{
      const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:inp.value})});
      if(r.ok){location.reload();return;}
    }catch(e){}
    err.textContent='Incorrect code — try again';inp.classList.add('err');inp.value='';inp.focus();btn.disabled=false;
  }
  btn.addEventListener('click',submit);
  inp.addEventListener('keydown',e=>{if(e.key==='Enter')submit();});
</script>
</body>
</html>"""
