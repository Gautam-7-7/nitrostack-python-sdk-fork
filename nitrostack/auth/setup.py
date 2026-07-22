from starlette.routing import Route
from starlette.responses import JSONResponse
from nitrostack.auth.middleware import JWTAuthMiddleware, ApiKeyAuthMiddleware, OAuth2AuthMiddleware

def setup_jwt_auth(app, config: dict, path: str = "/mcp"):
    secret = config.get("secret")
    from nitrostack.auth.secret import unwrap_secret
    unwrapped_secret = unwrap_secret(secret)
    app.add_middleware(
        JWTAuthMiddleware,
        secret=unwrapped_secret,
        audience=config.get("audience"),
        issuer=config.get("issuer")
    )
    print(f"✅ Simple JWT auth enabled on {path}")

def setupJWTAuth(app, config: dict, path: str = "/mcp"):
    setup_jwt_auth(app, config, path)

def setup_api_key_auth(app, config: dict, path: str = "/mcp"):
    app.add_middleware(
        ApiKeyAuthMiddleware,
        keys=config.get("keys"),
        hashed=config.get("hashed", False),
        header_name=config.get("headerName") or "x-api-key",
        allow_query_param=config.get("allowQueryParam", False),
        query_param_name=config.get("queryParamName") or "api_key"
    )
    print(f"✅ API Key auth enabled on {path}")

def setupAPIKeyAuth(app, config: dict, path: str = "/mcp"):
    setup_api_key_auth(app, config, path)

def setup_oauth_auth(app, config: dict, path: str = "/mcp"):
    app.add_middleware(
        OAuth2AuthMiddleware,
        auth_config=config
    )
    
    async def well_known_auth_metadata(request):
        metadata = {
            "resource": config.get("resourceUri"),
            "authorization_servers": config.get("authorizationServers"),
            "scopes_supported": config.get("scopesSupported"),
            "bearer_methods_supported": ["header"]
        }
        return JSONResponse(metadata)
        
    metadata_path = "/.well-known/oauth-protected-resource"
    app.routes.append(Route(metadata_path, endpoint=well_known_auth_metadata, methods=["GET"]))
    print(f"✅ OAuth 2.1 auth enabled on {path}")

def setupOAuthAuth(app, config: dict, path: str = "/mcp"):
    setup_oauth_auth(app, config, path)
