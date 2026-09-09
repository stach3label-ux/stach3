"""Shared helpers for the Vektra Open MCP server: token issuing/verification,
PKCE, and the small HTML pages used by the OAuth password flow."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

from core import database as store
from core.config import (
    MCP_ACCESS_TOKEN_TTL,
    MCP_AUTH_CODE_TTL,
    MCP_NAME,
    MCP_REFRESH_TOKEN_TTL,
    MCP_VERSION,
)

# ── hashing / secrets ────────────────────────────────────────────────────────


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def random_secret() -> str:
    return secrets.token_hex(32)


def password_matches(provided: str, expected: str) -> bool:
    """Constant-time password comparison; both sides hashed to equal length."""
    if not expected:
        return False
    a = hashlib.sha256((provided or "").encode("utf-8")).digest()
    b = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(a, b)


def pkce_matches(verifier: str, challenge: str) -> bool:
    if not verifier or not challenge:
        return False
    digest = hashlib.sha256(verifier.encode("ascii", "ignore")).digest()
    computed = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return hmac.compare_digest(computed, challenge)


# ── token lifecycle ──────────────────────────────────────────────────────────


def issue_token_pair() -> dict:
    """Create + persist a fresh access/refresh pair. Returns the token response body."""
    access = random_secret()
    refresh = random_secret()
    store.insert_mcp_tokens(
        sha256_hex(access),
        sha256_hex(refresh),
        MCP_ACCESS_TOKEN_TTL,
        MCP_REFRESH_TOKEN_TTL,
    )
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": MCP_ACCESS_TOKEN_TTL,
        "refresh_token": refresh,
    }


def rotate_token_pair(refresh_token: str) -> dict | None:
    """Rotate a refresh token for a new pair. None when unknown/expired."""
    old_hash = sha256_hex(refresh_token)
    access = random_secret()
    refresh = random_secret()
    ok = store.rotate_mcp_token(
        old_hash,
        sha256_hex(access),
        sha256_hex(refresh),
        MCP_ACCESS_TOKEN_TTL,
        MCP_REFRESH_TOKEN_TTL,
    )
    if not ok:
        return None
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": MCP_ACCESS_TOKEN_TTL,
        "refresh_token": refresh,
    }


def bearer_is_valid(token: str) -> bool:
    if not token:
        return False
    return store.get_mcp_token(sha256_hex(token)) is not None


def create_auth_code(redirect_uri: str, code_challenge: str) -> str:
    code = random_secret()
    store.insert_mcp_auth_code(sha256_hex(code), redirect_uri, code_challenge, MCP_AUTH_CODE_TTL)
    return code


def consume_auth_code(code: str, redirect_uri: str, verifier: str) -> bool:
    row = store.take_mcp_auth_code(sha256_hex(code))
    if not row:
        return False
    if row["redirect_uri"] != redirect_uri:
        return False
    return pkce_matches(verifier, row["code_challenge"])


# ── OAuth endpoints metadata ─────────────────────────────────────────────────


def oauth_metadata(base_url: str) -> dict:
    return {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/oauth/authorize",
        "token_endpoint": f"{base_url}/oauth/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
    }


# ── OAuth flow HTML ──────────────────────────────────────────────────────────

PAGE_STYLES = """
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0a0d0c;color:#e7edf3;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:24px 16px}
  .card{background:#11161a;border:1px solid #1f2730;border-radius:16px;padding:30px 32px;width:min(460px,100%)}
  .logo{display:flex;align-items:center;gap:9px;font-weight:700;font-size:13px;letter-spacing:.5px;color:#34d399;margin-bottom:22px}
  .logo-mark{width:24px;height:24px;border-radius:7px;background:linear-gradient(135deg,#10b981,#059669);display:inline-flex;align-items:center;justify-content:center;font-size:12px;color:#fff;font-weight:800}
  h1{font-size:20px;margin:0 0 8px;letter-spacing:-.2px}
  .sub{color:#8b98a9;font-size:14px;margin:0 0 20px;line-height:1.55}
  label{display:block;font-size:13px;color:#aeb9c5;margin-bottom:6px}
  input[type=password]{width:100%;padding:12px 14px;border-radius:10px;border:1px solid #2a3441;background:#0f1418;color:#e7edf3;font-size:15px;outline:none}
  input[type=password]:focus{border-color:#10b981}
  .btn{display:flex;align-items:center;justify-content:center;width:100%;padding:12px 16px;border-radius:10px;font-weight:600;font-size:14px;cursor:pointer;border:none;text-decoration:none;background:#10b981;color:#fff;margin-top:14px}
  .btn:hover{filter:brightness(1.08)}
  .note{color:#8b98a9;font-size:12px;margin:16px 0 0;line-height:1.6}
  .err{color:#f87171;font-size:13px;line-height:1.5;margin:0 0 14px;background:#2a1416;border:1px solid #4c1d24;border-radius:10px;padding:10px 12px}
  .ok{color:#34d399;font-size:14px;line-height:1.6;margin:8px 0 0}
"""


def page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{_esc(title)}</title><style>{PAGE_STYLES}</style></head>"
        f"<body><div class=\"card\">{body}</div></body></html>"
    )


def _esc(value) -> str:
    return (
        str(value if value is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def render_authorize_page(params: dict, client_name: str = "", error: str = "") -> str:
    hidden = "".join(
        f"<input type=\"hidden\" name=\"{_esc(k)}\" value=\"{_esc(v)}\">"
        for k, v in params.items()
        if v
    )
    error_html = f"<div class=\"err\">{_esc(error)}</div>" if error else ""
    name = _esc(client_name or "your AI assistant")
    body = (
        "<div class=\"logo\"><span class=\"logo-mark\">V</span>VEKTRA OPEN</div>"
        f"<h1>Connect {name}</h1>"
        "<p class=\"sub\">Enter this bot's MCP password to give the assistant access "
        "to your label's server. The password is set by whoever runs the bot "
        "(<code>MCP_PASSWORD</code> in the bot's environment).</p>"
        f"{error_html}"
        "<form method=\"POST\" action=\"/oauth/authorize\">"
        f"{hidden}"
        "<label for=\"password\">MCP password</label>"
        "<input id=\"password\" name=\"password\" type=\"password\" autocomplete=\"off\" required autofocus>"
        "<button class=\"btn\" type=\"submit\">Connect</button>"
        "</form>"
        "<p class=\"note\">The assistant can read submissions and tickets, decide "
        "demos, and create custom slash commands for your server. You can revoke "
        "access any time by changing the password or deleting tokens from the bot's database.</p>"
    )
    return page("Connect Vektra Open", body)


def render_success_page(client_name: str = "") -> str:
    name = _esc(client_name or "your assistant")
    body = (
        "<div class=\"logo\"><span class=\"logo-mark\">V</span>VEKTRA OPEN</div>"
        "<h1>Connected</h1>"
        f"<p class=\"ok\">Authorization complete. You can close this window — {name} will finish connecting on its own.</p>"
    )
    return page("Connected — Vektra Open", body)


def render_error_page(message: str) -> str:
    body = (
        "<div class=\"logo\"><span class=\"logo-mark\">V</span>VEKTRA OPEN</div>"
        "<h1>Can't connect</h1>"
        f"<div class=\"err\">{_esc(message)}</div>"
        "<p class=\"note\">Close this window and try adding the connector again.</p>"
    )
    return page("Connect Vektra Open", body)


def server_version() -> tuple[str, str]:
    return MCP_NAME, MCP_VERSION


def now_ts() -> int:
    return int(time.time())
