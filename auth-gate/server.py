"""Internal Nginx auth_request service; OAuth is performed by Keycloak."""
import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import jwt
from jwt import PyJWKClient


class TokenVerifier:
    def __init__(self, issuer, resource, jwks_url, client_id="chatgpt-toolhub"):
        self.issuer = issuer
        self.resource = resource
        self.client_id = client_id
        # The trusted URL is configured locally, never taken from token headers.
        self.keys = PyJWKClient(jwks_url, timeout=5, lifespan=300)

    def verify(self, authorization):
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer" or len(parts[1]) > 16384:
            raise jwt.InvalidTokenError("Bearer token required")
        token = parts[1]
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            raise jwt.InvalidTokenError("Unsupported signing key")
        key = self.keys.get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key, algorithms=["RS256"], issuer=self.issuer,
            audience=self.resource, leeway=10,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
        if claims.get("typ") != "Bearer" or claims.get("azp") != self.client_id:
            raise jwt.InvalidTokenError("Not a token from the configured MCP client")
        scopes = claims.get("scope", "")
        roles = claims.get("realm_access", {})
        if not isinstance(scopes, str) or "mcp:tools" not in scopes.split():
            raise PermissionError("Missing mcp:tools scope")
        role_names = roles.get("roles", []) if isinstance(roles, dict) else []
        if not isinstance(role_names, list) or "toolhub-access" not in role_names:
            raise PermissionError("User is not authorized for ToolHub")
        return claims


def make_handler(verifier):
    metadata_url = verifier.resource.split("/", 3)[:3]
    metadata_url = "/".join(metadata_url) + "/.well-known/oauth-protected-resource"
    challenge = f'Bearer resource_metadata="{metadata_url}", scope="mcp:tools"'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Never log authorization headers or request query strings.
            logging.info("auth-gate %s %s", self.command, urlsplit(self.path).path)

        def respond(self, status, value=None, authenticate=None):
            body = json.dumps(value).encode() if value is not None else b""
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            if authenticate:
                self.send_header("WWW-Authenticate", authenticate)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/health":
                return self.respond(200, {"status": "ok"})
            if path == "/resource":
                return self.respond(200, {
                    "resource": verifier.resource,
                    "authorization_servers": [verifier.issuer],
                    "scopes_supported": ["mcp:tools"],
                    "bearer_methods_supported": ["header"],
                })
            if path != "/verify":
                return self.respond(404, {"error": "not_found"})
            if len(self.headers.get_all("Authorization", [])) != 1:
                return self.respond(401, {"error": "invalid_token"}, challenge)
            try:
                verifier.verify(self.headers.get("Authorization", ""))
            except PermissionError:
                return self.respond(403, {"error": "insufficient_scope"})
            except jwt.PyJWKClientConnectionError:
                # Fail closed when Keycloak/JWKS is unavailable.
                return self.respond(503, {"error": "identity_provider_unavailable"})
            except (jwt.PyJWTError, ValueError, TypeError, KeyError):
                return self.respond(401, {"error": "invalid_token"}, challenge)
            return self.respond(204)

        do_HEAD = do_GET

    return Handler


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    verifier = TokenVerifier(os.environ["OAUTH_ISSUER"], os.environ["RESOURCE_URL"], os.environ["JWKS_URL"])
    server = ThreadingHTTPServer(("0.0.0.0", 8080), make_handler(verifier))
    server.daemon_threads = True
    server.serve_forever()
