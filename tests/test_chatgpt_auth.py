import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from src.core import chatgpt_auth


class ChatGPTAuthTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = chatgpt_auth.CredentialStore(Path(self.directory.name))
        self.auth = chatgpt_auth.ChatGPTAuth(self.store)

    def profile(self, **changes):
        profile = dict(id="profile-1", client_id="issued-client", sub="subject-1",
                       email="jake@example.test", access_token="access-secret",
                       refresh_token="refresh-secret", id_token="identity-secret",
                       expires_at=time.time() + 3600,
                       scope="openid chatgpt.tokens.use.direct")
        profile.update(changes)
        self.store.save(dict(host_id="urn:uuid:stable-host", active_profile_id="profile-1",
                             profiles=[profile]))
        return profile

    def test_host_survives_restarts_and_credentials_are_not_plaintext_on_windows(self):
        self.profile()
        status = self.auth.status()
        self.assertEqual(status["profiles"][0]["email"], "jake@example.test")
        self.assertNotIn("access-secret", json.dumps(status))
        reloaded = chatgpt_auth.CredentialStore(Path(self.directory.name)).load()
        self.assertEqual(reloaded["host_id"], "urn:uuid:stable-host")
        self.assertEqual(reloaded["profiles"][0]["refresh_token"], "refresh-secret")
        if chatgpt_auth.os.name == "nt":
            self.assertNotIn(b"refresh-secret", self.store.path.read_bytes())

    def test_authorization_uses_pkce_host_and_issued_client_on_reconnect(self):
        self.profile()
        attempt = self.auth.prepare_sign_in("profile-1")
        query = parse_qs(urlsplit(attempt.authorize_url("http://127.0.0.1:5050/auth/callback")).query)
        self.assertEqual(query["client_id"], ["issued-client"])
        self.assertNotIn("agent_name_hint", query)
        self.assertEqual(query["ext_agent_host_id"], ["urn:uuid:stable-host"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertIn("chatgpt.tokens.use.direct", query["scope"][0])
        other = self.auth.prepare_sign_in(new_profile=True)
        other_query = parse_qs(urlsplit(other.authorize_url("http://127.0.0.1:5051/auth/callback")).query)
        self.assertEqual(other_query["client_id"], ["dynamic_agent_client"])
        self.assertEqual(other_query["agent_name_hint"], ["Proper Thinking AI"])
        self.assertNotEqual(attempt.state, other.state)
        self.assertNotEqual(attempt.verifier, other.verifier)

    def test_callback_rejects_wrong_state_and_client_before_code_exchange(self):
        self.profile()
        attempt = self.auth.prepare_sign_in("profile-1")
        with self.assertRaises(chatgpt_auth.ChatGPTError):
            attempt.parse_callback({"state": ["wrong"], "code": ["secret-code"]})
        with self.assertRaises(chatgpt_auth.ChatGPTError):
            attempt.parse_callback({"state": [attempt.state], "code": ["code"], "client_id": ["wrong-client"]})
        self.assertEqual(attempt.parse_callback({"state": [attempt.state], "code": ["code"]}),
                         ("code", "issued-client"))

    def test_identity_only_grant_cannot_make_inference_requests(self):
        self.profile(scope="openid email profile")
        self.assertFalse(self.auth.status()["sharing"])
        with self.assertRaisesRegex(chatgpt_auth.ChatGPTError, "permission"):
            self.auth.access_token()

    def test_refresh_rotates_tokens_and_keeps_registration(self):
        self.profile(expires_at=0)
        with patch.object(chatgpt_auth, "token_request", return_value={
            "access_token": "replacement-access", "refresh_token": "replacement-refresh",
            "expires_in": 3600, "token_type": "Bearer",
        }) as request:
            self.assertEqual(self.auth.access_token(), "replacement-access")
        saved = self.store.load()["profiles"][0]
        self.assertEqual(saved["refresh_token"], "replacement-refresh")
        self.assertEqual(saved["client_id"], "issued-client")
        self.assertNotIn("scope", request.call_args.args[0])

    def test_transient_refresh_failure_preserves_credentials(self):
        self.profile(expires_at=0)
        with patch.object(chatgpt_auth, "token_request", side_effect=chatgpt_auth.ChatGPTError("Network unavailable")):
            with self.assertRaises(chatgpt_auth.ChatGPTError):
                self.auth.access_token()
        self.assertEqual(self.store.load()["profiles"][0]["refresh_token"], "refresh-secret")

    def test_sign_out_clears_tokens_but_retains_host_and_registration(self):
        self.profile()
        with patch.object(chatgpt_auth, "revoke_token", return_value=False):
            self.assertFalse(self.auth.sign_out("profile-1"))
        saved = self.store.load()
        self.assertEqual(saved["host_id"], "urn:uuid:stable-host")
        self.assertEqual(saved["profiles"][0]["client_id"], "issued-client")
        self.assertNotIn("access_token", saved["profiles"][0])
        self.assertNotIn("refresh_token", saved["profiles"][0])
        self.assertNotIn("id_token", saved["profiles"][0])

    def test_cancelled_login_does_not_open_browser(self):
        cancel = threading.Event()
        cancel.set()
        with patch.object(chatgpt_auth.webbrowser, "open") as browser:
            with self.assertRaisesRegex(chatgpt_auth.ChatGPTError, "cancelled"):
                self.auth.sign_in(cancel=cancel)
        browser.assert_not_called()

    def test_revoked_refresh_clears_local_tokens_and_requires_sign_in(self):
        self.profile(expires_at=0)
        with patch.object(chatgpt_auth, "token_request", side_effect=chatgpt_auth.ReauthenticationRequired("Revoked")):
            with self.assertRaises(chatgpt_auth.ReauthenticationRequired):
                self.auth.access_token()
        saved = self.store.load()["profiles"][0]
        self.assertNotIn("refresh_token", saved)
        self.assertEqual(saved["client_id"], "issued-client")

    def test_real_loopback_sign_in_validates_state_and_saves_granted_identity(self):
        import requests
        from urllib.parse import urlencode
        completed = threading.Event()
        failures = []

        def open_browser(url):
            query = parse_qs(urlsplit(url).query)
            def callback():
                try:
                    redirect = query["redirect_uri"][0]
                    bad = requests.get(redirect, params={"state": "bad", "code": "ignored"}, timeout=5)
                    self.assertEqual(bad.status_code, 400)
                    good = requests.get(redirect, params={"state": query["state"][0],
                                                        "code": "test-code", "client_id": "new-client"}, timeout=5)
                    self.assertEqual(good.status_code, 200)
                    self.assertNotIn("test-code", good.text)
                except Exception as error:
                    failures.append(error)
                finally:
                    completed.set()
            threading.Thread(target=callback, daemon=True).start()
            return True

        tokens = {"access_token": "access", "refresh_token": "refresh", "id_token": "identity",
                  "expires_in": 3600, "token_type": "Bearer", "scope": "openid chatgpt.tokens.use.direct"}
        with patch.object(chatgpt_auth.webbrowser, "open", side_effect=open_browser), patch.object(
            chatgpt_auth, "token_request", return_value=tokens
        ) as exchange, patch.object(chatgpt_auth, "verify_identity", return_value={"sub": "new-sub", "email": "test@example.test"}):
            status = self.auth.sign_in()
        self.assertTrue(completed.wait(2))
        self.assertEqual(failures, [])
        self.assertTrue(status["sharing"])
        self.assertEqual(status["profiles"][0]["email"], "test@example.test")
        self.assertEqual(exchange.call_args.args[0]["client_id"], "new-client")
        self.assertEqual(exchange.call_args.args[0]["grant_type"], "authorization_code")

    def test_signed_identity_checks_nonce_audience_issuer_and_expiry(self):
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        claims = {"sub": "subject", "iss": "https://auth.openai.com", "aud": "client",
                  "iat": int(time.time()), "exp": int(time.time()) + 3600, "nonce": "expected"}
        with patch.object(chatgpt_auth.jwt.PyJWKClient, "get_signing_key_from_jwt", return_value=SimpleNamespace(key=key.public_key())):
            token = chatgpt_auth.jwt.encode(claims, key, algorithm="RS256")
            self.assertEqual(chatgpt_auth.verify_identity(token, "client", "expected")["sub"], "subject")
            for changed in ({"nonce": "other"}, {"aud": "other"}, {"iss": "https://wrong.example"}, {"exp": 1}):
                with self.subTest(changed=changed):
                    invalid = chatgpt_auth.jwt.encode({**claims, **changed}, key, algorithm="RS256")
                    with self.assertRaises(chatgpt_auth.ChatGPTError):
                        chatgpt_auth.verify_identity(invalid, "client", "expected")

    def test_same_email_registrations_stay_separate_and_reauth_cannot_replace_identity(self):
        self.profile()
        attempt = self.auth.prepare_sign_in("profile-1")
        tokens = {"access_token": "wrong-access", "refresh_token": "wrong-refresh",
                  "id_token": "wrong-identity", "scope": "openid chatgpt.tokens.use.direct"}
        with patch.object(chatgpt_auth, "token_request", return_value=tokens), patch.object(
            chatgpt_auth, "verify_identity", return_value={"sub": "different-sub", "email": "jake@example.test"}
        ), patch.object(chatgpt_auth, "revoke_token", return_value=True):
            with self.assertRaisesRegex(chatgpt_auth.ChatGPTError, "differs"):
                self.auth.complete_sign_in(attempt, "code", "issued-client", "http://127.0.0.1:5000/auth/callback", threading.Event())
        self.assertEqual(self.store.load()["profiles"][0]["access_token"], "access-secret")
        new_attempt = self.auth.prepare_sign_in(new_profile=True)
        with patch.object(chatgpt_auth, "token_request", return_value=tokens), patch.object(
            chatgpt_auth, "verify_identity", return_value={"sub": "different-sub", "email": "jake@example.test"}
        ):
            self.auth.complete_sign_in(new_attempt, "code", "new-issued-client", "http://127.0.0.1:5000/auth/callback", threading.Event())
        self.assertEqual(len(self.auth.status()["profiles"]), 2)
        self.auth.select_profile("profile-1")
        self.assertEqual(self.auth.access_token(), "access-secret")

    def test_reauthorization_does_not_retain_ungranted_plan_scope(self):
        self.profile()
        attempt = self.auth.prepare_sign_in("profile-1")
        with patch.object(chatgpt_auth, "token_request", return_value={
            "access_token": "new-access", "id_token": "new-id", "expires_in": 3600,
        }), patch.object(chatgpt_auth, "verify_identity", return_value={"sub": "subject-1"}):
            status = self.auth.complete_sign_in(attempt, "code", "issued-client",
                                                "http://127.0.0.1:5000/auth/callback", threading.Event())
        self.assertFalse(status["sharing"])
        self.assertNotIn("refresh_token", self.store.load()["profiles"][0])

    def test_failed_first_exchange_reuses_issued_registration_on_retry(self):
        attempt = self.auth.prepare_sign_in(new_profile=True)
        with patch.object(chatgpt_auth, "token_request", side_effect=chatgpt_auth.ChatGPTError("Network offline")):
            with self.assertRaises(chatgpt_auth.ChatGPTError):
                self.auth.complete_sign_in(attempt, "code", "retained-client",
                                          "http://127.0.0.1:5000/auth/callback", threading.Event())
        retry = self.auth.prepare_sign_in()
        self.assertEqual(retry.client_id, "retained-client")
        self.assertEqual(retry.profile_id, attempt.profile_id)
        retry_new = self.auth.prepare_sign_in(new_profile=True)
        self.assertEqual(retry_new.client_id, "retained-client")
        self.assertIsNone(self.auth.status()["active_profile_id"])


if __name__ == "__main__":
    unittest.main()
