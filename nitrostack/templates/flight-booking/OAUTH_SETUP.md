# OAuth 2.1 Server Setup Guide

To run your flight booking MCP server with OAuth 2.1 protection, you need to configure an OAuth authorization server (like Keycloak, Auth0, Hydra, or a local mock OAuth server).

## 1. Local Configuration

Add the following environment variables to your `.env` file to configure resource protection:

```env
# Introspection endpoint to validate access tokens
OAUTH_INTROSPECTION_ENDPOINT=http://localhost:3000/oauth/introspect

# Or use JWKS (JSON Web Key Sets) to cryptographically verify signatures locally
# JWKS_URI=http://localhost:3000/oauth/jwks
# TOKEN_AUDIENCE=https://mcplocal
# TOKEN_ISSUER=https://dev-5dt0utuk315713tjm.us.auth0.com
```

## 2. Protected Routes

The tools in this server use the `@use_guards(OAuthGuard, create_scope_guard([...]))` decorators to automatically protect endpoints:
* **Public**: No guards (or custom public filters).
* **Read-Protected**: Requires valid access token with `read` scope.
* **Write-Protected**: Requires valid access token with `write` scope.

When calling protected tools, the client must pass a valid Bearer token in the `Authorization` header.
