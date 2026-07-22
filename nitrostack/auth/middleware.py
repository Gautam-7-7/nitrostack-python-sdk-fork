import hashlib
import time
import json
import base64
import urllib.request
import urllib.parse
from typing import Any, Dict, List, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import jwt

class JWTAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, secret: str, audience: Optional[str] = None, issuer: Optional[str] = None):
        super().__init__(app)
        self.secret = secret
        self.audience = audience
        self.issuer = issuer

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/mcp"):
            return await call_next(request)

        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error": "unauthorized", "message": "Missing or invalid Authorization header. Use: Authorization: Bearer <token>"},
                status_code=401
            )

        token = auth_header[7:]
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=["HS256"],
                audience=self.audience,
                issuer=self.issuer
            )
            request.state.auth = {
                "authenticated": True,
                "tokenInfo": {
                    "active": True,
                    "sub": payload.get("sub"),
                    "aud": payload.get("aud"),
                    "iss": payload.get("iss"),
                    "exp": payload.get("exp"),
                    "iat": payload.get("iat"),
                },
                "scopes": payload.get("scopes") or (payload.get("scope", "").split(" ") if payload.get("scope") else []),
                "clientId": payload.get("client_id") or payload.get("sub"),
                "subject": payload.get("sub"),
            }
        except jwt.ExpiredSignatureError:
            return JSONResponse({"error": "token_expired", "message": "JWT has expired"}, status_code=401)
        except jwt.InvalidTokenError as e:
            return JSONResponse({"error": "invalid_token", "message": f"Invalid JWT: {e}"}, status_code=401)
        except Exception:
            return JSONResponse({"error": "server_error", "message": "Token validation failed"}, status_code=500)

        return await call_next(request)

class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        keys: List[str],
        hashed: bool = False,
        header_name: str = "x-api-key",
        allow_query_param: bool = False,
        query_param_name: str = "api_key"
    ):
        super().__init__(app)
        self.keys = keys
        self.hashed = hashed
        self.header_name = header_name.lower()
        self.allow_query_param = allow_query_param
        self.query_param_name = query_param_name

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/mcp"):
            return await call_next(request)

        api_key = request.headers.get(self.header_name)
        if not api_key and self.allow_query_param:
            api_key = request.query_params.get(self.query_param_name)

        if not api_key:
            return JSONResponse(
                {"error": "unauthorized", "message": f"Missing API key. Provide in {self.header_name} header"},
                status_code=401
            )

        is_valid = False
        if self.hashed:
            hashed_input = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
            is_valid = hashed_input in self.keys
        else:
            is_valid = api_key in self.keys

        if not is_valid:
            return JSONResponse({"error": "unauthorized", "message": "Invalid API key"}, status_code=401)

        request.state.auth = {
            "authenticated": True,
            "tokenInfo": {"active": True},
            "scopes": ["*"],
            "clientId": f"apikey_{hashlib.sha256(api_key.encode('utf-8')).hexdigest()[:8]}",
            "subject": None,
        }
        return await call_next(request)

class OAuth2AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, auth_config: Dict[str, Any]):
        super().__init__(app)
        self.auth_config = auth_config

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/mcp"):
            return await call_next(request)

        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse({"error": "unauthorized", "message": "Missing Bearer token"}, status_code=401)

        token = auth_header[7:]
        valid = False
        introspection = None

        introspection_endpoint = self.auth_config.get("tokenIntrospectionEndpoint")
        if introspection_endpoint:
            try:
                params = {"token": token}
                body = urllib.parse.urlencode(params).encode("utf-8")
                headers = {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json"
                }
                client_id = self.auth_config.get("tokenIntrospectionClientId")
                client_secret = self.auth_config.get("tokenIntrospectionClientSecret")
                if client_id and client_secret:
                    from nitrostack.auth.secret import unwrap_secret
                    unwrapped_secret = unwrap_secret(client_secret)
                    creds = f"{client_id}:{unwrapped_secret}"
                    basic = base64.b64encode(creds.encode("utf-8")).decode("ascii")
                    headers["Authorization"] = f"Basic {basic}"

                req = urllib.request.Request(introspection_endpoint, data=body, headers=headers, method="POST")
                with urllib.request.urlopen(req) as resp:
                    res_body = json.loads(resp.read().decode("utf-8"))
                    if res_body.get("active"):
                        valid = True
                        introspection = res_body
            except Exception as e:
                return JSONResponse({"error": "server_error", "message": f"Token introspection failed: {e}"}, status_code=500)

        if not valid or not introspection:
            return JSONResponse({"error": "invalid_token", "message": "Invalid token"}, status_code=401)

        request.state.auth = {
            "authenticated": True,
            "tokenInfo": introspection,
            "scopes": introspection.get("scope", "").split(" ") if introspection.get("scope") else [],
            "clientId": introspection.get("client_id"),
            "subject": introspection.get("sub")
        }
        return await call_next(request)
