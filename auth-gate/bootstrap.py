"""Generate persistent credentials and a one-time Keycloak realm import."""
import json
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit


def build_realm(domain, mcp_path, redirect, username, secret_values):
    resource = f"https://{domain}{mcp_path}"
    return {
        "realm": "toolhub", "enabled": True, "sslRequired": "external",
        "registrationAllowed": False, "resetPasswordAllowed": False,
        "bruteForceProtected": True, "accessTokenLifespan": 300,
        "revokeRefreshToken": True, "refreshTokenMaxReuse": 0,
        "roles": {"realm": [{"name": "toolhub-access"}]},
        "users": [{
            "username": username, "enabled": True,
            "firstName": "ToolHub", "lastName": "User",
            "email": os.environ.get("EMAIL", "owner@example.com"), "emailVerified": True,
            "realmRoles": ["toolhub-access"],
            "credentials": [{"type": "password", "value": secret_values["user_password"], "temporary": False}],
        }],
        "clientScopes": [{
            "name": "mcp:tools", "protocol": "openid-connect",
            "attributes": {"include.in.token.scope": "true", "display.on.consent.screen": "true"},
            "protocolMappers": [{
                "name": "Subject", "protocol": "openid-connect",
                "protocolMapper": "oidc-sub-mapper",
                "config": {"access.token.claim": "true"},
            }, {
                "name": "ToolHub access roles", "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-realm-role-mapper",
                "config": {"claim.name": "realm_access.roles", "multivalued": "true",
                           "jsonType.label": "String", "access.token.claim": "true",
                           "id.token.claim": "false", "userinfo.token.claim": "false"},
            }],
        }],
        "clients": [
            {"clientId": "toolhub-resource", "enabled": True, "protocol": "openid-connect",
             "bearerOnly": True, "attributes": {"resource_url": resource}},
            {"clientId": "chatgpt-toolhub", "enabled": True, "protocol": "openid-connect",
             "publicClient": False, "clientAuthenticatorType": "client-secret",
             "secret": secret_values["client_secret"],
             "standardFlowEnabled": True, "implicitFlowEnabled": False,
             "directAccessGrantsEnabled": False, "serviceAccountsEnabled": False,
             "redirectUris": [redirect], "webOrigins": [], "fullScopeAllowed": True,
             "attributes": {"pkce.code.challenge.method": "S256", "exclude.issuer.from.auth.response": "false"},
             "defaultClientScopes": ["mcp:tools"], "optionalClientScopes": [],
             "protocolMappers": [{
                 "name": "MCP resource audience", "protocol": "openid-connect",
                 "protocolMapper": "oidc-audience-mapper",
                 "config": {"included.client.audience": "toolhub-resource",
                            "access.token.claim": "true", "id.token.claim": "false"},
             }],
            },
        ],
    }


def write_private(path, text):
    path.write_text(text)
    path.chmod(0o600)


def main():
    domain = os.environ["DOMAIN"]
    mcp_path = os.environ.get("MCP_PATH", "/mcp")
    redirect = os.environ.get("OAUTH_REDIRECT_URI", "https://chatgpt.com/connector_platform_oauth_redirect")
    username = os.environ.get("TOOLHUB_USERNAME", "toolhub-user")
    if not re.fullmatch(r"[a-zA-Z0-9.-]+", domain):
        raise ValueError("Invalid DOMAIN")
    if not re.fullmatch(r"/[a-zA-Z0-9/_-]*", mcp_path):
        raise ValueError("MCP_PATH must be an absolute URL path")
    callback = urlsplit(redirect)
    if (callback.scheme != "https" or callback.hostname != "chatgpt.com" or "*" in redirect
            or callback.fragment or callback.query or callback.username or callback.password):
        raise ValueError("Use the exact HTTPS ChatGPT callback, without wildcards")
    config = Path("/config")
    config.mkdir(parents=True, exist_ok=True)
    config.chmod(0o700)
    secret_file = config / "secrets.json"
    if secret_file.exists():
        values = json.loads(secret_file.read_text())
    else:
        values = {key: secrets.token_urlsafe(32) for key in ["db_password", "admin_password", "client_secret", "user_password"]}
        write_private(secret_file, json.dumps(values, indent=2))
    write_private(config / "postgres.env", "POSTGRES_PASSWORD=" + values["db_password"] + "\n")
    write_private(config / "keycloak.env",
                  "KC_DB_PASSWORD=" + values["db_password"] + "\n"
                  "KC_BOOTSTRAP_ADMIN_USERNAME=admin\n"
                  "KC_BOOTSTRAP_ADMIN_PASSWORD=" + values["admin_password"] + "\n")
    write_private(config / "credentials.txt",
                  f"Login user: {username}\nLogin password: {values['user_password']}\n"
                  f"Client ID: chatgpt-toolhub\nClient Secret: {values['client_secret']}\n"
                  f"Redirect URI: {redirect}\nResource: https://{domain}{mcp_path}\n"
                  f"Keycloak admin: admin\nAdmin password: {values['admin_password']}\n")
    realm_dir = Path("/realm-import")
    realm_dir.mkdir(parents=True, exist_ok=True)
    realm_dir.chmod(0o755)
    realm_file = realm_dir / "toolhub-realm.json"
    realm_file.write_text(json.dumps(build_realm(domain, mcp_path, redirect, username, values), indent=2))
    # Host parent data/ is mode 0700; the mount itself must be readable by KC UID 1000.
    realm_file.chmod(0o644)
    print("OAuth configuration prepared; credentials saved to config/credentials.txt")


if __name__ == "__main__":
    main()
