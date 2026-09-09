"""Smoke test for the Vektra Open MCP flow — run directly:

    python mcp/_smoke_test.py

Uses an in-memory fake of the database store so no Postgres is needed.
"""
import base64
import hashlib
import io
import json
import os
import secrets
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["MCP_PASSWORD"] = "test-pass-123"

# ── fake store ───────────────────────────────────────────────────────────────
codes = {}
tokens = {}


class FakeResult:
    def __init__(self, row):
        self.row = row

    def __iter__(self):
        return iter([self.row] if self.row else [])


class FakeStore:
    def insert_mcp_auth_code(self, code_hash, redirect_uri, challenge, ttl):
        codes[code_hash] = {"redirect_uri": redirect_uri, "code_challenge": challenge, "used": False}

    def take_mcp_auth_code(self, code_hash):
        row = codes.get(code_hash)
        if not row or row["used"]:
            return None
        row["used"] = True
        return {"redirect_uri": row["redirect_uri"], "code_challenge": row["code_challenge"], "used": True}

    def insert_mcp_tokens(self, token_hash, refresh_hash, access_ttl, refresh_ttl):
        tokens[token_hash] = {"refresh_hash": refresh_hash}

    def get_mcp_token(self, token_hash):
        return {"token_hash": token_hash} if token_hash in tokens else None

    def rotate_mcp_token(self, old_refresh, token_hash, refresh_hash, a, b):
        for data in tokens.values():
            if data["refresh_hash"] == old_refresh:
                tokens.pop([k for k, v in tokens.items() if v["refresh_hash"] == old_refresh][0])
                tokens[token_hash] = {"refresh_hash": refresh_hash}
                return True
        return False

    def delete_mcp_token_by_refresh(self, refresh_hash):
        found = [k for k, v in tokens.items() if v["refresh_hash"] == refresh_hash]
        for k in found:
            tokens.pop(k)
        return bool(found)


fake = FakeStore()

import mcp.common as common
import mcp.http_api as http_api
import mcp.tools as tools

with patch.object(common, "store", fake), patch.object(http_api, "store", fake):
    # ── PKCE + authorize ─────────────────────────────────────────────
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")

    class H:
        def __init__(self):
            self.headers = {"Host": "localhost:7860", "Authorization": ""}
            self.rfile = open(os.devnull, "rb")
            self.wfile = io.BytesIO()
            self.status = None
            self.payload = None
            self.location = None

        def send_response(self, s):
            self.status = s

        def send_header(self, key, value):
            if key == "Location":
                self.location = value

        def end_headers(self):
            pass

        @property
        def body_out(self):
            return self.wfile.getvalue().decode()

    h = H()
    http_api.handle_authorize_post(
        h,
        {
            "response_type": "code",
            "redirect_uri": "http://localhost:54545/callback",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "xyz",
            "password": "WRONG",
        },
    )
    assert h.status == 200, "wrong password should re-render the page"

    h = H()
    http_api.handle_authorize_post(
        h,
        {
            "response_type": "code",
            "redirect_uri": "http://localhost:54545/callback",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "xyz",
            "password": "test-pass-123",
        },
    )
    assert h.status == 302 and "code=" in h.location and "state=xyz" in h.location, h.location
    code = h.location.split("code=")[1].split("&")[0]

    # ── token exchange (code + PKCE) ─────────────────────────────────
    h = H()
    http_api.handle_token_post(
        h,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:54545/callback",
            "code_verifier": verifier,
        },
    )
    assert h.status == 200, "token exchange failed"
    body = json.loads(h.body_out)

    # reuse of the code must fail
    h = H()
    http_api.handle_token_post(
        h,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:54545/callback",
            "code_verifier": verifier,
        },
    )
    assert h.status == 400, "code reuse must be rejected"

    # ── MCP JSON-RPC with the bearer ─────────────────────────────────
    h = H()
    h.headers["Authorization"] = f"Bearer {body['access_token']}"
    h.body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()
    h.headers["Content-Length"] = str(len(h.body))
    h.rfile = type("R", (), {"read": staticmethod(lambda n: h.body)})()
    http_api.handle_mcp_post(h)
    assert h.status == 200 and len(json.loads(h.body_out)["result"]["tools"]) == 10, h.body_out

    # tools/call without bot bound → friendly error, not a crash
    h.wfile = io.BytesIO()
    h.body = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_submissions", "arguments": {}}}).encode()
    h.headers["Content-Length"] = str(len(h.body))
    h.rfile = type("R", (), {"read": staticmethod(lambda n: h.body)})()
    http_api.handle_mcp_post(h)
    assert h.status == 200 and "error" in json.loads(h.body_out)["result"]["content"][0]["text"], h.body_out

    # bad token → 401
    h = H()
    h.headers["Authorization"] = "Bearer nope"
    http_api.handle_mcp_post(h)
    assert h.status == 401

    # ── refresh rotation ─────────────────────────────────────────────
    h = H()
    http_api.handle_token_post(h, {"grant_type": "refresh_token", "refresh_token": body["refresh_token"]})
    assert h.status == 200, "refresh failed"
    new = json.loads(h.body_out)
    assert new["access_token"] != body["access_token"]

    # old refresh must be dead (rotation)
    h = H()
    http_api.handle_token_post(h, {"grant_type": "refresh_token", "refresh_token": body["refresh_token"]})
    assert h.status == 400, "old refresh token must be invalidated"

    # ── revocation ───────────────────────────────────────────────────
    h = H()
    http_api.handle_revoke_post(h, {"refresh_token": new["refresh_token"]})
    h = H()
    h.headers["Authorization"] = f"Bearer {new['access_token']}"
    http_api.handle_mcp_post(h)
    assert h.status == 401, "revoked token must not authenticate"

    # ── manifest validation ──────────────────────────────────────────
    good = {
        "name": "hello_check",
        "description": "Say hello",
        "parameters": [{"name": "user", "type": "user"}],
        "response": {"content": "Hi!"},
        "actions": [{"type": "kick_member", "input": "bye"}],
        "rate_limit": {"max_uses_per_user_hour": 5},
    }
    assert tools.validate_manifest(good) == [], tools.validate_manifest(good)
    bad = dict(good, name="Bad Name!", actions=[{"type": "fly_to_moon"}])
    errs = tools.validate_manifest(bad)
    assert any("name" in e for e in errs) and any("fly_to_moon" in e for e in errs)

    # member action without a user parameter → structural error
    no_user = dict(good, parameters=[])
    assert any("user" in e for e in tools.validate_manifest(no_user))

print("MCP SMOKE TEST OK — oauth, pkce, rotation, revoke, json-rpc, validation all pass")
