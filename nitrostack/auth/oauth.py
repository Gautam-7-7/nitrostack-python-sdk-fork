import os
import sys
import json
import urllib.request
import urllib.parse
from typing import List, Optional, Dict, Any
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from nitrostack.core.module import module
from nitrostack.core.di import DIContainer

class OAuthService:
    def __init__(
        self,
        resource_uri: str,
        authorization_servers: List[str],
        scopes_supported: List[str],
        token_introspection_endpoint: Optional[str] = None,
        token_introspection_client_id: Optional[str] = None,
        token_introspection_client_secret: Optional[str] = None,
        discovery_port: int = 3005,
        jwks_uri: Optional[str] = None,
        audience: Optional[str] = None,
        issuer: Optional[str] = None,
    ):
        self.resource_uri = resource_uri
        self.authorization_servers = authorization_servers
        self.scopes_supported = scopes_supported
        self.token_introspection_endpoint = token_introspection_endpoint
        self.token_introspection_client_id = token_introspection_client_id
        self.token_introspection_client_secret = token_introspection_client_secret
        self.discovery_port = discovery_port
        
        # Environmental fallbacks
        self.jwks_uri = jwks_uri or os.environ.get("JWKS_URI")
        self.audience = audience or os.environ.get("TOKEN_AUDIENCE") or resource_uri
        self.issuer = issuer or os.environ.get("TOKEN_ISSUER")
        
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start_discovery_server(self) -> None:
        """Starts a background HTTP discovery server for OAuth Protected Resource metadata."""
        if self._server is not None:
            return

        service_instance = self

        class DiscoveryHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                # Suppress server logging to stdout/stderr to keep stdio clean
                pass

            def do_GET(self):
                if self.path == "/.well-known/oauth-protected-resource":
                    response_data = {
                        "resource": service_instance.resource_uri,
                        "authorization_servers": service_instance.authorization_servers,
                        "scopes_supported": service_instance.scopes_supported
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(response_data).encode("utf-8"))
                elif self.path == "/.well-known/oauth-authorization-server":
                    # Mock/basic authorization server metadata if query hits this resource
                    response_data = {
                        "issuer": service_instance.authorization_servers[0] if service_instance.authorization_servers else "http://localhost",
                        "token_endpoint": service_instance.token_introspection_endpoint or "",
                        "introspection_endpoint": service_instance.token_introspection_endpoint or ""
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(response_data).encode("utf-8"))
                else:
                    self.send_response(404)
                    self.end_headers()

        def run_server():
            # Try binding to OAUTH_DISCOVERY_PORT
            port = int(os.environ.get("OAUTH_DISCOVERY_PORT", self.discovery_port))
            try:
                self._server = HTTPServer(("localhost", port), DiscoveryHandler)
                # Notify client via stderr
                oauth_metadata = {
                    "port": port,
                    "resource_uri": self.resource_uri,
                    "authorization_servers": self.authorization_servers
                }
                sys.stderr.write(
                    f"[NITROSTACK_OAUTH]{json.dumps(oauth_metadata)}[/NITROSTACK_OAUTH]\n"
                )
                sys.stderr.flush()
                self._server.serve_forever()
            except Exception as e:
                sys.stderr.write(f"Failed to start OAuth Discovery Server on port {port}: {e}\n")
                sys.stderr.flush()

        self._thread = threading.Thread(target=run_server, daemon=True)
        self._thread.start()

    def stop_discovery_server(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    async def introspect_token(self, token: str) -> Dict[str, Any]:
        """
        Validates token using JWKS verification or RFC 7662 token introspection.
        """
        # 1. JWKS Verification if configured
        if self.jwks_uri:
            try:
                import jwt
                # Parse JWT headers to get kid
                unverified_headers = jwt.get_unverified_header(token)
                jwks_client = jwt.PyJWKClient(self.jwks_uri)
                signing_key = jwks_client.get_signing_key_from_jwt(token)
                
                # Verify token signature
                data = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    audience=self.audience,
                    issuer=self.issuer
                )
                return {
                    "active": True,
                    "scope": data.get("scope", ""),
                    "sub": data.get("sub"),
                    "client_id": data.get("client_id")
                }
            except Exception as e:
                # Log signature failure to stderr
                sys.stderr.write(f"OAuth JWKS verification failed: {e}\n")
                sys.stderr.flush()
                return {"active": False}

        if not self.token_introspection_endpoint:
            # If no introspection endpoint is configured, mock active check for local debugging
            # A real deployment must provide an introspection endpoint.
            sys.stderr.write("OAuth Warning: No token_introspection_endpoint configured. Assuming mock active.\n")
            return {"active": True, "scope": " ".join(self.scopes_supported), "sub": "mock-user"}
        import httpx
        
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        auth = None
        if self.token_introspection_client_id and self.token_introspection_client_secret:
            auth = (self.token_introspection_client_id, self.token_introspection_client_secret)
            
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(
                    self.token_introspection_endpoint,
                    data={"token": token},
                    headers=headers,
                    auth=auth
                )
                res.raise_for_status()
                return res.json()
        except Exception as e:
            sys.stderr.write(f"OAuth Introspection Request Failed: {e}\n")
            sys.stderr.flush()
            return {"active": False}
@module(name="OAuthModule")
class OAuthModule:
    @classmethod
    def for_root(
        cls,
        resource_uri: str,
        authorization_servers: List[str],
        scopes_supported: List[str],
        token_introspection_endpoint: Optional[str] = None,
        token_introspection_client_id: Optional[str] = None,
        token_introspection_client_secret: Optional[str] = None,
        discovery_port: int = 3005,
        jwks_uri: Optional[str] = None,
        audience: Optional[str] = None,
        issuer: Optional[str] = None,
    ):
        service = OAuthService(
            resource_uri=resource_uri,
            authorization_servers=authorization_servers,
            scopes_supported=scopes_supported,
            token_introspection_endpoint=token_introspection_endpoint,
            token_introspection_client_id=token_introspection_client_id,
            token_introspection_client_secret=token_introspection_client_secret,
            discovery_port=discovery_port,
            jwks_uri=jwks_uri,
            audience=audience,
            issuer=issuer
        )
        DIContainer.get_instance().register_value(OAuthService, service)
        return cls
