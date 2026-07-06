# Access Passcode Gate — lite spec

## Purpose
Protect the deployed MiroFish instance so only teammates who know a shared
**access code** can use it — preventing strangers from burning the MiniMax API
key. The gate is **environment-controlled**: off during local development, on in
the live (Hugging Face) deploy.

## Environment control (the key requirement)
| Setting | Local dev (default) | Testing locally | Live (HF) |
|---|---|---|---|
| `AUTH_ENABLED` | unset → `false` | `true` | `true` |
| `ACCESS_CODE` | — | your test code | Space secret |
| `SECRET_KEY` | dev default | any | Space secret |

- `AUTH_ENABLED=false` → **no gate**, zero local friction.
- `AUTH_ENABLED=true` → gate enforced. Set it locally only when testing the gate.

## Behaviors (entry → action → result)
1. **Unauthenticated page visit.** Entry: user opens any app URL with the gate on
   and no valid session. Action: they see the **cover page**, type the access
   code, click **Enter**. Result (correct): a signed session cookie is set and
   they land in the app. Result (incorrect): stay on the cover page with an
   `Incorrect code` error and HTTP `401`.
2. **Unauthenticated API call.** Entry: any `POST/GET /api/*` with the gate on and
   no session. Action: request reaches the server. Result: **`401` JSON**
   (`{"success": false, "error": "..."}`) — never an HTML redirect.
3. **Authenticated request.** Entry: request carries a valid session cookie.
   Result: passes through unchanged.
4. **Gate off.** Entry: `AUTH_ENABLED=false`. Result: every route behaves exactly
   as today (no cover page, no 401).

## Design
- **Config** (`app/config.py`): `AUTH_ENABLED` (bool from env, default `False`),
  `ACCESS_CODE` (str), reuse existing `SECRET_KEY` for signed sessions
  (7-day lifetime).
- **Guard** (`app/auth.py`, registered as an app-level `before_request`):
  - Return early (allow) if `AUTH_ENABLED` is false.
  - Always allow: the login route, the cover-page route, static assets, `/health`.
  - If the session is authenticated → allow.
  - Else: request path under `/api/` → `401` JSON; otherwise → serve the cover page.
- **Login** `POST /api/auth/login` `{code}`: constant-time compare against
  `ACCESS_CODE`; match → `session['authed']=True` + `{success:true}`; mismatch →
  `401`. A short per-session cooldown after repeated failures deters brute force.
- **Logout** `POST /api/auth/logout`: clears the session.
- **Cover page**: minimal server-rendered HTML (MiroFish-branded per the approved
  mockup) posting the code to the login endpoint, then reloading into the app.

## Testing (TDD)
- Gate off → a protected route returns normally.
- Gate on, no session → page route serves the cover page; `/api/*` returns `401`.
- Correct code → `200` + session set → protected route now allowed.
- Wrong code → `401` + error; comparison is constant-time.
- Repeated failures → cooldown enforced.

## Out of scope
- Per-user identity / Google OAuth (overkill for a trusted team, no DB).
- The Hugging Face single-container repackaging (separate follow-up).

Source-of-truth for the cover-page visuals: the approved access-gate mockup.
