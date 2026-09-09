"""HTTP layer for the Vektra Open MCP server: routing, OAuth password flow
(authorize + token), and the stateless MCP JSON-RPC endpoint.

All of this is served from the bot's existing HTTP server under /mcp,
/oauth/authorize, /oauth/token and /.well-known/oauth-authorization-server.
The handlers are plain functions so the bot's ThreadingHTTPServer can call
them synchronously; anything that touches the bot/loop is funneled through
the helper passed via mcp_tools.bind_bot().
"""

from __future__ import annotations

import json
import time
from urllib.parse import parse_qs, urlencode, urlparse

from core import database as store
from core.config import MCP_PASSWORD

from . import common, tools

# Valid redirect targets for the connector flow: https, localhost http, and
# non-http custom app schemes (e.g. claude-desktop://callback). Plain http to
# a remote host is refused so codes can't leak over an unencrypted wire.
_DISALLOWED_SCHEMES = {"javascript", "data", "file", "vbscript"}


def valid_redirect_uri(value: str) -> bool:
    try:
        url = urlparse(str(value))
    except ValueError:
        return False
    scheme = (url.scheme or "").lower()
    if scheme == "https":
        return True
    if scheme == "http" and url.hostname in {"127.0.0.1", "localhost"}:
        return True
    if scheme and scheme not in {"http", "https"} and scheme not in _DISALLOWED_SCHEMES:
        return True
    return False


def oauth_params(source: dict) -> dict:
    return {
        "response_type": str(source.get("response_type") or "").strip(),
        "client_id": str(source.get("client_id") or "").strip(),
        "redirect_uri": str(source.get("redirect_uri") or "").strip(),
        "code_challenge": str(source.get("code_challenge") or "").strip(),
        "code_challenge_method": str(source.get("code_challenge_method") or "S256").strip().upper(),
        "state": str(source.get("state") or "").strip(),
        "scope": str(source.get("scope") or "").strip(),
    }


def validate_params(p: dict) -> str | None:
    if p["response_type"] != "code":
        return "Invalid response_type - expected 'code'."
    if not valid_redirect_uri(p["redirect_uri"]):
        return "Invalid redirect_uri - must be an https address (or localhost)."
    if not (43 <= len(p["code_challenge"]) <= 128):
        return "Missing or invalid code_challenge (PKCE is required)."
    if p["code_challenge_method"] != "S256":
        return "code_challenge_method must be S256."
    return None


# ── raw response helpers (match BaseHTTPRequestHandler's interface) ──────────


def send_json(handler, status: int, payload: dict, extra_headers: dict | None = None) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    for key, value in (extra_headers or {}).items():
        handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


def send_html(handler, status: int, html: str) -> None:
    body = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_redirect(handler, location: str) -> None:
    handler.send_response(302)
    handler.send_header("Location", location)
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def _auth_failure(handler, base_url: str, message: str) -> None:
    send_json(
        handler,
        401,
        {"error": message},
        extra_headers={
            "WWW-Authenticate": f'Bearer resource_metadata="{base_url}/.well-known/oauth-authorization-server"'
        },
    )


def _base_url(handler) -> str:
    host = handler.headers.get("X-Forwarded-Host") or handler.headers.get("Host") or "localhost"
    proto = handler.headers.get("X-Forwarded-Proto") or ("http" if "localhost" in host or "127.0.0.1" in host else "https")
    return f"{proto}://{host}"


# ── route entry points ───────────────────────────────────────────────────────


def handle_mcp_well_known(handler) -> None:
    send_json(handler, 200, common.oauth_metadata(_base_url(handler)))


def handle_authorize_get(handler, query: dict) -> None:
    params = oauth_params(query)
    if not MCP_PASSWORD:
        send_html(handler, 503, common.render_error_page("The MCP server is disabled on this bot (MCP_PASSWORD is not set)."))
        return

    client_name = params["client_id"]
    error = validate_params(params)
    if error:
        send_html(handler, 400, common.render_error_page(error))
        return
    send_html(handler, 200, common.render_authorize_page(params, client_name))


def handle_authorize_post(handler, form: dict) -> None:
    params = oauth_params(form)
    client_name = params["client_id"]
    if not MCP_PASSWORD:
        send_html(handler, 503, common.render_error_page("The MCP server is disabled on this bot (MCP_PASSWORD is not set)."))
        return

    error = validate_params(params)
    if error:
        send_html(handler, 400, common.render_error_page(error))
        return

    password = str(form.get("password") or "")
    if not common.password_matches(password, MCP_PASSWORD):
        # Slow brute force down without leaking timing information.
        time.sleep(1.5)
        send_html(handler, 200, common.render_authorize_page(params, client_name, error="Wrong password. Check MCP_PASSWORD in the bot's environment and try again."))
        return

    code = common.create_auth_code(params["redirect_uri"], params["code_challenge"])
    target = params["redirect_uri"]
    separator = "&" if "?" in target else "?"
    location = f"{target}{separator}code={code}"
    if params["state"]:
        location += f"&state={params['state']}"
    send_redirect(handler, location)


def handle_token_post(handler, form: dict) -> None:
    grant_type = str(form.get("grant_type") or "").strip()

    if grant_type == "authorization_code":
        code = str(form.get("code") or "").strip()
        redirect_uri = str(form.get("redirect_uri") or "").strip()
        verifier = str(form.get("code_verifier") or "").strip()
        if not code:
            send_json(handler, 400, {"error": "invalid_request", "error_description": "code is required."})
            return
        if not common.consume_auth_code(code, redirect_uri, verifier):
            send_json(handler, 400, {"error": "invalid_grant", "error_description": "Authorization code is invalid, expired, or PKCE verification failed."})
            return
        send_json(handler, 200, common.issue_token_pair())
        return

    if grant_type == "refresh_token":
        refresh = str(form.get("refresh_token") or "").strip()
        if not refresh:
            send_json(handler, 400, {"error": "invalid_request", "error_description": "refresh_token is required."})
            return
        pair = common.rotate_token_pair(refresh)
        if not pair:
            send_json(handler, 400, {"error": "invalid_grant", "error_description": "Refresh token is invalid or has expired."})
            return
        send_json(handler, 200, pair)
        return

    send_json(handler, 400, {"error": "unsupported_grant_type", "error_description": "grant_type must be authorization_code or refresh_token."})


def handle_revoke_post(handler, form: dict) -> None:
    refresh = str(form.get("refresh_token") or "").strip()
    if refresh:
        store.delete_mcp_token_by_refresh(common.sha256_hex(refresh))
    send_json(handler, 200, {})


def _read_body_json(handler) -> dict:
    try:
        length = int(handler.headers.get("Content-Length") or 0)
    except ValueError:
        length = 0
    if length <= 0:
        return {}
    raw = handler.rfile.read(min(length, 2_000_000)).decode("utf-8", "replace")
    try:
        data = json.loads(raw) if raw else {}
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def handle_mcp_post(handler) -> None:
    """Stateless MCP endpoint: authenticate, dispatch one JSON-RPC request."""
    base_url = _base_url(handler)
    auth = handler.headers.get("Authorization") or ""
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not common.bearer_is_valid(token):
        _auth_failure(handler, base_url, "Missing or expired MCP token. Connect through the OAuth connector flow, or reconnect.")
        return

    request = _read_body_json(handler)
    method = str(request.get("method") or "")
    request_id = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        send_json(handler, 200, {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": str(params.get("protocolVersion") or "2025-03-26"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": common.MCP_NAME, "version": common.MCP_VERSION},
            },
        })
        return

    if method == "notifications/initialized":
        # A notification: no id, nothing to answer.
        handler.send_response(202)
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return

    if method == "ping":
        send_json(handler, 200, {"jsonrpc": "2.0", "id": request_id, "result": {}})
        return

    if method == "tools/list":
        send_json(handler, 200, {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools.TOOL_SPECS}})
        return

    if method == "tools/call":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        result = tools.call_tool(name, arguments)
        send_json(handler, 200, {"jsonrpc": "2.0", "id": request_id, "result": {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            "isError": isinstance(result, dict) and bool(result.get("error")),
        }})
        return

    if method in {"prompts/list", "resources/list"}:
        key = method.split("/")[0]
        send_json(handler, 200, {"jsonrpc": "2.0", "id": request_id, "result": {key: []}})
        return

    send_json(handler, 200, {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not supported: {method}"}})


def handle_mcp_get(handler) -> None:
    """GET /mcp — point clients at the OAuth metadata (stateless server: no SSE)."""
    base_url = _base_url(handler)
    auth = handler.headers.get("Authorization") or ""
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if token and not common.bearer_is_valid(token):
        _auth_failure(handler, base_url, "Expired MCP token. Reconnect through the connector flow.")
        return
    send_json(handler, 200, {
        "name": common.MCP_NAME,
        "version": common.MCP_VERSION,
        "transport": "stateless-json",
        "oauth": common.oauth_metadata(base_url),
        "note": "POST JSON-RPC messages here with a Bearer token obtained from the OAuth connector flow.",
    })


# Re-export for the bot's HTTP server dispatcher.
parse_qs = parse_qs
urlencode = urlencode
urlparse = urlparse
