import importlib.util
import json
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "auth-gate" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load("gate", "server.py")
bootstrap = load("bootstrap", "bootstrap.py")


class OAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.jwk = jwt.algorithms.RSAAlgorithm.to_jwk(cls.private_key.public_key(), as_dict=True)
        cls.jwk.update(kid="trusted", alg="RS256", use="sig")
        cls.issuer = "https://tools.test.net/auth/realms/toolhub"
        cls.resource = "https://tools.test.net/mcp"
        class Keys(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"keys": [cls.jwk]}).encode())
        cls.keys_server = ThreadingHTTPServer(("127.0.0.1", 0), Keys)
        cls.keys_thread = threading.Thread(target=cls.keys_server.serve_forever, daemon=True)
        cls.keys_thread.start()
        cls.verifier = gate.TokenVerifier(cls.issuer, cls.resource, f"http://127.0.0.1:{cls.keys_server.server_port}/keys")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), gate.make_handler(cls.verifier))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        for server in [cls.server, cls.keys_server]:
            server.shutdown()
            server.server_close()

    def token(self, remove=(), key=None, algorithm="RS256", **overrides):
        claims = {"iss": self.issuer, "aud": self.resource, "sub": "user-1", "iat": int(time.time()),
                  "exp": int(time.time()) + 300, "azp": "chatgpt-toolhub", "typ": "Bearer",
                  "scope": "mcp:tools", "realm_access": {"roles": ["toolhub-access"]}}
        claims.update(overrides)
        for name in remove:
            del claims[name]
        return jwt.encode(claims, key or self.private_key, algorithm=algorithm, headers={"kid": "trusted"})

    def request(self, path="/verify", token=None):
        headers = {"Authorization": "Bearer " + token} if token else {}
        try:
            response = urlopen(Request(self.base + path, headers=headers), timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def test_valid_access_token(self):
        self.assertEqual(self.request(token=self.token())[0], 204)

    def test_missing_token_challenges_with_resource_metadata(self):
        status, headers, _ = self.request()
        self.assertEqual(status, 401)
        self.assertIn('resource_metadata="https://tools.test.net/.well-known/oauth-protected-resource"', headers["WWW-Authenticate"])

    def test_public_metadata_matches_token_audience_and_issuer(self):
        status, _, body = self.request("/resource")
        self.assertEqual(status, 200)
        metadata = json.loads(body)
        self.assertEqual(metadata["resource"], self.resource)
        self.assertEqual(metadata["authorization_servers"], [self.issuer])

    def test_wrong_signature(self):
        self.assertEqual(self.request(token=self.token(key=self.other_key))[0], 401)

    def test_expired_token(self):
        self.assertEqual(self.request(token=self.token(exp=int(time.time()) - 60))[0], 401)

    def test_wrong_audience(self):
        self.assertEqual(self.request(token=self.token(aud="another-api"))[0], 401)

    def test_wrong_issuer(self):
        self.assertEqual(self.request(token=self.token(iss="https://attacker.test"))[0], 401)

    def test_id_token_cannot_be_used(self):
        self.assertEqual(self.request(token=self.token(typ="ID"))[0], 401)

    def test_another_oauth_client_cannot_be_used(self):
        self.assertEqual(self.request(token=self.token(azp="another-client"))[0], 401)

    def test_missing_required_claims(self):
        for claim in ["exp", "iat", "iss", "aud", "sub"]:
            with self.subTest(claim=claim):
                self.assertEqual(self.request(token=self.token(remove=[claim]))[0], 401)

    def test_scope_enforced(self):
        self.assertEqual(self.request(token=self.token(scope="openid profile"))[0], 403)

    def test_role_enforced(self):
        self.assertEqual(self.request(token=self.token(realm_access={"roles": ["unrelated"]}))[0], 403)

    def test_malformed_roles_cannot_bypass_check(self):
        self.assertEqual(self.request(token=self.token(realm_access={"roles": "fake-toolhub-access-role"}))[0], 403)

    def test_hmac_algorithm_cannot_substitute_rsa(self):
        self.assertEqual(self.request(token=self.token(key="a-long-untrusted-secret-at-least-32-bytes", algorithm="HS256"))[0], 401)

    def test_malformed_token_rejected(self):
        self.assertEqual(self.request(token="not-a-jwt")[0], 401)

    def test_unavailable_identity_provider_denies_access(self):
        with patch.object(self.verifier, "verify", side_effect=jwt.PyJWKClientConnectionError("offline")):
            self.assertEqual(self.request(token=self.token())[0], 503)

    def test_unknown_signing_key_denies_access(self):
        claims = jwt.decode(self.token(), options={"verify_signature": False})
        token = jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": "unknown"})
        self.assertEqual(self.request(token=token)[0], 401)

    def test_realm_requires_pkce_and_exact_callback(self):
        realm = bootstrap.build_realm("tools.test.net", "/mcp", "https://chatgpt.com/connector_platform_oauth_redirect", "user", {"client_secret":"secret", "user_password":"password"})
        resource, client = realm["clients"]
        self.assertEqual(resource["attributes"]["resource_url"], self.resource)
        self.assertEqual(client["attributes"]["pkce.code.challenge.method"], "S256")
        self.assertFalse(client["directAccessGrantsEnabled"])
        self.assertFalse(client["implicitFlowEnabled"])
        self.assertNotIn("*", client["redirectUris"][0])
        mappers = realm["clientScopes"][0]["protocolMappers"]
        self.assertTrue(any(m["protocolMapper"] == "oidc-sub-mapper" for m in mappers))


if __name__ == "__main__":
    unittest.main()
