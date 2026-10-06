# 0.3.0

- OAuth authorization-code flow with mandatory PKCE S256 via Keycloak.
- Pre-registered confidential ChatGPT OAuth client; exact redirect allowlist.
- Protected resource discovery and WWW-Authenticate MCP challenge.
- RS256/JWKS JWT validation: issuer, audience, expiry, authorized client, scope and user role.
- Persistent PostgreSQL for Keycloak and automatic credentials generation.
- Internal identity services; no publicly mapped database/auth-gate/Keycloak ports.
- User/client management helpers and OAuth validation tests.
- Existing containerized Certbot renewal and streaming proxy preserved.
