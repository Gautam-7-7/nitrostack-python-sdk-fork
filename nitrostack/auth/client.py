import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error
import re
import base64
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse, urlunparse

from nitrostack.auth.pkce import generate_pkce_params, validate_pkce_support

def get_well_known_metadata_uris(resource_url: str) -> List[str]:
    parsed = urlparse(resource_url)
    urls = []
    if parsed.path and parsed.path != "/":
        urls.append(f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-protected-resource{parsed.path}")
    urls.append(f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-protected-resource")
    return urls

def parse_www_authenticate_header(header_value: str) -> Optional[Dict[str, str]]:
    if not header_value:
        return None
    
    bearer_match = re.match(r"Bearer\s+(.+)", header_value, re.IGNORECASE)
    if not bearer_match:
        return None
    
    params = bearer_match.group(1)
    result = {"scheme": "Bearer"}
    
    param_matches = re.findall(r'(\w+)="([^"]+)"', params)
    for key, value in param_matches:
        if key == "realm":
            result["realm"] = value
        elif key == "scope":
            result["scope"] = value
        elif key == "resource_metadata":
            result["resourceMetadata"] = value
        elif key == "error":
            result["error"] = value
        elif key == "error_description":
            result["errorDescription"] = value
            
    return result

class OAuth2Client:
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def _fetch_metadata(self, url: str) -> Any:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"Failed to fetch metadata from {url}: {e}")

    async def discoverProtectedResourceMetadata(self, resource_url: str) -> Dict[str, Any]:
        try:
            req = urllib.request.Request(resource_url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req) as resp:
                pass
        except urllib.error.HTTPError as e:
            if e.code == 401:
                www_auth = e.headers.get("WWW-Authenticate")
                if www_auth:
                    parsed = parse_www_authenticate_header(www_auth)
                    if parsed and parsed.get("resourceMetadata"):
                        return self._fetch_metadata(parsed["resourceMetadata"])
        except Exception:
            pass

        well_knowns = get_well_known_metadata_uris(resource_url)
        for uri in well_knowns:
            try:
                return self._fetch_metadata(uri)
            except Exception:
                continue

        raise RuntimeError(
            f"Failed to discover protected resource metadata for {resource_url}. "
            "Server must implement RFC 9728 (Protected Resource Metadata)."
        )

    async def discoverAuthorizationServerMetadata(self, issuer: str) -> Dict[str, Any]:
        parsed = urlparse(issuer)
        well_knowns = []
        if parsed.path and parsed.path != "/":
            well_knowns.append(f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-authorization-server{parsed.path}")
            well_knowns.append(f"{parsed.scheme}://{parsed.netloc}/.well-known/openid-configuration{parsed.path}")
            well_knowns.append(f"{issuer.rstrip('/')}/.well-known/openid-configuration")
        else:
            well_knowns.append(f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-authorization-server")
            well_knowns.append(f"{parsed.scheme}://{parsed.netloc}/.well-known/openid-configuration")

        for url in well_knowns:
            try:
                metadata = self._fetch_metadata(url)
                if not validate_pkce_support(metadata.get("code_challenge_methods_supported")):
                    raise RuntimeError(
                        "Authorization server does not support PKCE (S256). "
                        "OAuth 2.1 requires PKCE support. Cannot proceed."
                    )
                return metadata
            except Exception:
                continue

        raise RuntimeError(
            f"Failed to discover authorization server metadata for {issuer}. "
            "Server must implement RFC 8414 or OpenID Connect Discovery."
        )

    async def registerClient(self, registration_endpoint: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(metadata).encode("utf-8")
        req = urllib.request.Request(
            registration_endpoint,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            try:
                err_json = json.loads(err_body)
                err_desc = err_json.get("error_description") or err_json.get("error") or "Unknown error"
            except Exception:
                err_desc = err_body or str(e)
            raise RuntimeError(f"Client registration failed: {e.code} - {err_desc}")

    async def startAuthorizationFlow(self, options: Dict[str, Any]) -> Dict[str, Any]:
        pkce = generate_pkce_params("S256")
        state = options.get("state") or base64.b32encode(os.urandom(10)).decode("ascii").lower()

        params = {
            "response_type": "code",
            "client_id": options["clientId"],
            "redirect_uri": options["redirectUri"],
            "state": state,
            "code_challenge": pkce["code_challenge"],
            "code_challenge_method": pkce["code_challenge_method"],
        }
        if options.get("scope"):
            params["scope"] = options["scope"]
        if options.get("resource"):
            params["resource"] = options["resource"]

        query = urllib.parse.urlencode(params)
        auth_url = f"{options['authorizationEndpoint']}?{query}"
        return {"authUrl": auth_url, "state": state, "pkce": pkce}

    def _token_request(self, endpoint: str, params: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        body = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            try:
                err_json = json.loads(err_body)
                err_desc = err_json.get("error_description") or err_json.get("error") or "Unknown error"
            except Exception:
                err_desc = err_body or str(e)
            raise RuntimeError(f"Token request failed: {err_desc}")

    async def exchangeCodeForToken(self, options: Dict[str, Any]) -> Dict[str, Any]:
        params = {
            "grant_type": "authorization_code",
            "code": options["code"],
            "redirect_uri": options["redirectUri"],
            "client_id": options["clientId"],
            "code_verifier": options["pkce"]["code_verifier"],
        }
        if options.get("resource"):
            params["resource"] = options["resource"]

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        if options.get("clientSecret"):
            creds = f"{options['clientId']}:{options['clientSecret']}"
            basic = base64.b64encode(creds.encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {basic}"

        return self._token_request(options["tokenEndpoint"], params, headers)

    async def refreshToken(self, options: Dict[str, Any]) -> Dict[str, Any]:
        params = {
            "grant_type": "refresh_token",
            "refresh_token": options["refreshToken"],
            "client_id": options["clientId"],
        }
        if options.get("scope"):
            params["scope"] = options["scope"]
        if options.get("resource"):
            params["resource"] = options["resource"]

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }

        if options.get("clientSecret"):
            creds = f"{options['clientId']}:{options['clientSecret']}"
            basic = base64.b64encode(creds.encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {basic}"

        return self._token_request(options["tokenEndpoint"], params, headers)

    async def getClientCredentialsToken(self, options: Dict[str, Any]) -> Dict[str, Any]:
        params = {
            "grant_type": "client_credentials",
            "client_id": options["clientId"],
        }
        if options.get("scope"):
            params["scope"] = options["scope"]
        if options.get("resource"):
            params["resource"] = options["resource"]

        creds = f"{options['clientId']}:{options['clientSecret']}"
        basic = base64.b64encode(creds.encode("utf-8")).decode("ascii")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Authorization": f"Basic {basic}"
        }

        return self._token_request(options["tokenEndpoint"], params, headers)

    async def revokeToken(self, options: Dict[str, Any]) -> None:
        params = {
            "token": options["token"],
            "client_id": options["clientId"],
        }
        if options.get("tokenTypeHint"):
            params["token_type_hint"] = options["tokenTypeHint"]

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        if options.get("clientSecret"):
            creds = f"{options['clientId']}:{options['clientSecret']}"
            basic = base64.b64encode(creds.encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {basic}"

        body = urllib.parse.urlencode(params).encode("utf-8")
        req = urllib.request.Request(options["revocationEndpoint"], data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                pass
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Token revocation failed: {e.code} {e.reason}")
