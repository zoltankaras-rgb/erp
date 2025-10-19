# csrf.py — lightweight CSRF middleware for Flask session-based apps
import secrets
from flask import request, session, make_response

CSRF_SESSION_KEY = "csrf_token"
CSRF_COOKIE_NAME = "XSRF-TOKEN"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

def _get_or_create_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_hex(32)
        session[CSRF_SESSION_KEY] = token
    return token

def ensure_csrf_token():
    """Ensure a CSRF token exists in session for any request (so GET can receive the cookie)."""
    _get_or_create_token()

def inject_csrf(response):
    """Mirror the session token into a cookie readable by JS (SameSite=Lax)."""
    token = session.get(CSRF_SESSION_KEY)
    if token:
        response.set_cookie(CSRF_COOKIE_NAME, token, httponly=False, samesite="Lax")
    return response

def csrf_protect():
    """Validate X-CSRF-Token header for state-changing requests under /api/*."""
    if request.method in SAFE_METHODS:
        return
    # Only protect API routes
    if not request.path.startswith("/api/"):
        return
    sent = request.headers.get("X-CSRF-Token") or request.headers.get("X-XSRF-Token")
    expected = session.get(CSRF_SESSION_KEY)
    if not expected or not sent or not secrets.compare_digest(str(sent), str(expected)):
        return make_response(("CSRF validation failed", 403))
