"""Public Sign in with ChatGPT OAuth, with per-installation protected storage.

Protocol: https://developers.openai.com/siwc/token-sharing-open-source/sign-in
No Codex credentials, private endpoints, passwords, or client secrets are used.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import tempfile
import threading
import time
import uuid
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt
import requests
from filelock import FileLock

from .app_config import data_dir

ISSUER = "https://auth.openai.com"
AUTHORIZE_URL = ISSUER + "/api/accounts/authorize"
TOKEN_URL = ISSUER + "/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
SCOPES = "openid profile email offline_access resource.invoke " + PLAN_SCOPE
USAGE_URL = "https://chatgpt.com/settings/usage"
_TOKEN_FIELDS = ("access_token", "refresh_token", "id_token", "expires_at", "scope")


class ChatGPTError(RuntimeError):
    """Safe-to-display error; never contains credentials or raw OAuth responses."""


class ReauthenticationRequired(ChatGPTError):
    pass


class CredentialStore:
    def __init__(self, directory: Path | None = None):
        directory = directory or data_dir() / "chatgpt"
        directory.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            directory.chmod(0o700)
        self.path = directory / "credentials.dat"
        self.lock = FileLock(str(directory / "credentials.lock"), timeout=120)

    def load(self) -> dict:
        if not self.path.exists():
            return {"host_id": "urn:uuid:" + str(uuid.uuid4()), "profiles": [], "active_profile_id": None}
        try:
            blob = self.path.read_bytes()
            if os.name == "nt":
                import win32crypt
                blob = win32crypt.CryptUnprotectData(blob, None, None, None, 1)[1]
            return json.loads(blob)
        except Exception:
            raise ChatGPTError("Cannot read protected ChatGPT credentials for this OS user. No credentials were overwritten.") from None

    def save(self, data: dict) -> None:
        blob = json.dumps(data, ensure_ascii=False).encode("utf-8")
        if os.name == "nt":
            import win32crypt
            blob = win32crypt.CryptProtectData(blob, "Proper Thinking AI ChatGPT", None, None, None, 1)
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=".credentials-")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(blob)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)


def token_request(form: dict) -> dict:
    try:
        response = requests.post(TOKEN_URL, data=form, timeout=(10, 45), allow_redirects=False)
        data = response.json()
    except (requests.RequestException, ValueError):
        raise ChatGPTError("Could not reach ChatGPT sign-in. Check your connection and try again.") from None
    if not isinstance(data, dict):
        raise ChatGPTError("ChatGPT returned an invalid token response. Please try again.")
    if response.status_code != 200:
        if data.get("error") in ("invalid_grant", "invalid_token"):
            raise ReauthenticationRequired("Your ChatGPT session expired or was revoked. Continue with ChatGPT again.")
        raise ChatGPTError(f"ChatGPT sign-in failed (HTTP {response.status_code}). Please try again.")
    if not data.get("access_token") or str(data.get("token_type", "")).lower() != "bearer":
        raise ChatGPTError("ChatGPT returned an incomplete token response. Please sign in again.")
    return data


def verify_identity(id_token: str, client_id: str, nonce: str) -> dict:
    try:
        key = jwt.PyJWKClient(ISSUER + "/.well-known/jwks.json").get_signing_key_from_jwt(id_token)
        identity = jwt.decode(id_token, key.key, algorithms=["RS256"], audience=client_id,
                              issuer=ISSUER, options={"require": ["exp", "iat", "sub", "nonce"]})
        if not secrets.compare_digest(str(identity["nonce"]), nonce):
            raise ValueError("Nonce mismatch")
        return identity
    except Exception:
        raise ChatGPTError("Could not verify the ChatGPT account identity. No session was saved.") from None


def revoke_token(profile: dict) -> bool:
    if not profile.get("refresh_token"):
        return True
    for delay in (0, 1, 2):
        if delay:
            time.sleep(delay)
        try:
            discovery = requests.get(ISSUER + "/.well-known/openid-configuration", timeout=(5, 10), allow_redirects=False)
            discovery.raise_for_status()
            endpoint = discovery.json()["revocation_endpoint"]
            if not endpoint.startswith(ISSUER + "/"):
                return False
            response = requests.post(endpoint, data={"token": profile["refresh_token"],
                                     "token_type_hint": "refresh_token", "client_id": profile["client_id"]},
                                     timeout=(5, 10), allow_redirects=False)
            if response.status_code == 200:
                return True
            if response.status_code < 500:
                return False
        except (requests.RequestException, ValueError, KeyError):
            continue
    return False


@dataclass
class AuthAttempt:
    profile_id: str
    host_id: str
    client_id: str
    subject: str = ""
    email: str = ""
    id_token: str = ""
    state: str = ""
    nonce: str = ""
    verifier: str = ""

    def authorize_url(self, redirect_uri: str) -> str:
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        query = dict(client_id=self.client_id, response_type="code", redirect_uri=redirect_uri,
                     scope=SCOPES, resource=RESOURCE, state=self.state, nonce=self.nonce,
                     code_challenge=challenge, code_challenge_method="S256", ext_agent_host_id=self.host_id)
        if self.client_id == "dynamic_agent_client":
            query["agent_name_hint"] = "Proper Thinking AI"
        else:
            if self.id_token:
                query["id_token_hint"] = self.id_token
            if self.email:
                query["login_hint"] = self.email
        return AUTHORIZE_URL + "?" + urlencode(query)

    def parse_callback(self, query: dict) -> tuple[str, str]:
        def one(name):
            values = query.get(name, [])
            return values[0] if len(values) == 1 else ""
        if not secrets.compare_digest(one("state"), self.state):
            raise ChatGPTError("Invalid sign-in state. Please return to the original browser sign-in.")
        if one("error"):
            raise ChatGPTError("ChatGPT sign-in was declined or cancelled. No new session was saved.")
        client_id = one("client_id")
        if self.client_id != "dynamic_agent_client":
            if client_id and client_id != self.client_id:
                raise ChatGPTError("ChatGPT returned a different account registration. Please try again.")
            client_id = self.client_id
        if not one("code") or not client_id or client_id == "dynamic_agent_client":
            raise ChatGPTError("Incomplete ChatGPT sign-in callback. Please try again.")
        return one("code"), client_id


class ChatGPTAuth:
    def __init__(self, store: CredentialStore | None = None):
        self.store = store or CredentialStore()

    @staticmethod
    def _profile(data: dict, profile_id: str | None = None) -> dict:
        target = profile_id or data.get("active_profile_id")
        return next((p for p in data["profiles"] if p["id"] == target), {})

    def status(self) -> dict:
        with self.store.lock:
            data = self.store.load()
            active = self._profile(data)
            profiles = [{"id": p["id"], "email": p.get("email", ""),
                         "label": f"{p.get('email') or 'ChatGPT account'} · {p['id'][:8]}",
                         "connected": bool(p.get("access_token")),
                         "sharing": bool(p.get("access_token")) and PLAN_SCOPE in p.get("scope", "").split()}
                        for p in data["profiles"] if p.get("sub")]
            return {"profiles": profiles, "active_profile_id": data.get("active_profile_id"),
                    "connected": bool(active.get("access_token")),
                    "sharing": bool(active.get("access_token")) and PLAN_SCOPE in active.get("scope", "").split()}

    def select_profile(self, profile_id: str) -> None:
        with self.store.lock:
            data = self.store.load()
            if not self._profile(data, profile_id).get("sub"):
                raise ChatGPTError("That ChatGPT account is not saved on this device.")
            data["active_profile_id"] = profile_id
            self.store.save(data)

    def prepare_sign_in(self, profile_id: str | None = None, new_profile: bool = False) -> AuthAttempt:
        with self.store.lock:
            data = self.store.load()
            pending = self._profile(data, data.get("pending_profile_id")) if data.get("pending_profile_id") else {}
            profile = pending if new_profile else (self._profile(data, profile_id) or pending)
            self.store.save(data)  # Persist installation ID before opening the browser.
        return AuthAttempt(profile_id=profile.get("id") or str(uuid.uuid4()), host_id=data["host_id"],
                           client_id=profile.get("client_id", "dynamic_agent_client"),
                           subject=profile.get("sub", ""), email=profile.get("email", ""),
                           id_token=profile.get("id_token", ""), state=secrets.token_urlsafe(32),
                           nonce=secrets.token_urlsafe(32), verifier=secrets.token_urlsafe(64))

    def sign_in(self, profile_id: str | None = None, new_profile: bool = False,
                cancel: threading.Event | None = None) -> dict:
        cancel = cancel or threading.Event()
        if cancel.is_set():
            raise ChatGPTError("ChatGPT sign-in cancelled.")
        attempt = self.prepare_sign_in(profile_id, new_profile)
        result = {}

        class CallbackServer(HTTPServer):
            def get_request(self):
                connection, address = super().get_request()
                connection.settimeout(2)
                return connection, address

        class CallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass  # Callback URLs contain single-use credentials.

            def do_GET(self):
                parsed = urlsplit(self.path)
                query = parse_qs(parsed.query)
                if parsed.path != "/auth/callback":
                    self.send_error(404)
                    return
                valid_state = query.get("state") == [attempt.state]
                try:
                    result["callback"] = attempt.parse_callback(query)
                    message, status = "Sign-in received. You may close this tab and return to Proper Thinking AI.", 200
                except ChatGPTError as error:
                    message, status = str(error), 400
                    if valid_state:
                        result["error"] = error
                body = message.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        with CallbackServer(("127.0.0.1", 0), CallbackHandler) as server:
            server.timeout = 0.25
            redirect_uri = f"http://127.0.0.1:{server.server_port}/auth/callback"
            if not webbrowser.open(attempt.authorize_url(redirect_uri)):
                raise ChatGPTError("Could not open your browser. Set a default browser and try again.")
            deadline = time.monotonic() + 300
            while not result and not cancel.is_set() and time.monotonic() < deadline:
                server.handle_request()
        if cancel.is_set():
            raise ChatGPTError("ChatGPT sign-in cancelled.")
        if not result:
            raise ChatGPTError("ChatGPT sign-in timed out. Please try again.")
        if "error" in result:
            raise result["error"]
        code, client_id = result["callback"]
        return self.complete_sign_in(attempt, code, client_id, redirect_uri, cancel)

    def complete_sign_in(self, attempt: AuthAttempt, code: str, client_id: str,
                         redirect_uri: str, cancel: threading.Event) -> dict:
        with self.store.lock:
            data = self.store.load()
            profile = self._profile(data, attempt.profile_id)
            if not profile:
                profile = {"id": attempt.profile_id, "client_id": client_id}
                data["profiles"].append(profile)
            if not profile.get("sub"):
                data["pending_profile_id"] = profile["id"]
            self.store.save(data)  # Retain issued client even if the exchange needs a retry.
        tokens = token_request(dict(grant_type="authorization_code", client_id=client_id, code=code,
                                    code_verifier=attempt.verifier, redirect_uri=redirect_uri, resource=RESOURCE))
        try:
            identity = verify_identity(tokens.get("id_token", ""), client_id, attempt.nonce)
            if attempt.subject and identity["sub"] != attempt.subject:
                raise ChatGPTError("The returned account differs from this saved registration. Use Add account instead.")
            if cancel.is_set():
                raise ChatGPTError("ChatGPT sign-in cancelled.")
            with self.store.lock:
                data = self.store.load()
                profile = self._profile(data, attempt.profile_id)
                profile.update(sub=identity["sub"], email=identity.get("email", ""), client_id=client_id)
                # A fresh authorization replaces the grant, unlike a refresh.
                for key in _TOKEN_FIELDS:
                    profile.pop(key, None)
                self._apply_tokens(profile, tokens)
                data["active_profile_id"] = profile["id"]
                if data.get("pending_profile_id") == profile["id"]:
                    data.pop("pending_profile_id", None)
                self.store.save(data)
        except Exception:
            revoke_token({**tokens, "client_id": client_id})
            raise
        return self.status()

    @staticmethod
    def _apply_tokens(profile: dict, tokens: dict) -> None:
        for key in ("access_token", "refresh_token", "id_token", "scope"):
            if key in tokens:
                profile[key] = tokens[key]
        profile["expires_at"] = time.time() + float(tokens.get("expires_in", 3600))

    def access_token(self) -> str:
        with self.store.lock:  # Serialize refresh across GUI, background jobs and MCP.
            data = self.store.load()
            profile = self._profile(data)
            if not profile.get("access_token"):
                raise ReauthenticationRequired("Continue with ChatGPT in Settings to connect your account.")
            if PLAN_SCOPE not in profile.get("scope", "").split():
                raise ChatGPTError("ChatGPT plan permission was not granted. Continue with ChatGPT and enable plan usage.")
            if profile.get("expires_at", 0) <= time.time() + 60:
                try:
                    if not profile.get("refresh_token"):
                        raise ReauthenticationRequired("Continue with ChatGPT again to renew your session.")
                    tokens = token_request(dict(grant_type="refresh_token", client_id=profile["client_id"],
                                                refresh_token=profile["refresh_token"], resource=RESOURCE))
                except ReauthenticationRequired:
                    for key in _TOKEN_FIELDS:
                        profile.pop(key, None)
                    self.store.save(data)
                    raise
                self._apply_tokens(profile, tokens)
                self.store.save(data)
                if PLAN_SCOPE not in profile.get("scope", "").split():
                    raise ChatGPTError("ChatGPT plan permission is disabled. Enable it in ChatGPT Settings.")
            return profile["access_token"]

    def sign_out(self, profile_id: str) -> bool:
        with self.store.lock:
            data = self.store.load()
            profile = self._profile(data, profile_id)
            if not profile:
                return True
            confirmed = revoke_token(profile)
            for key in _TOKEN_FIELDS:
                profile.pop(key, None)
            self.store.save(data)
            return confirmed
