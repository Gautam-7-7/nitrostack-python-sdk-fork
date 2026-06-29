import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nitrostack import DIContainer, ExecutionContext, OAuthGuard
from nitrostack.auth.oauth import OAuthModule, OAuthService

async def _test_oauth_guard_validation():
    print("Testing OAuthGuard and OAuth 2.1 validation flow...")

    # 1. Setup DIContainer and OAuthModule
    DIContainer.reset()
    OAuthModule.for_root(
        resource_uri="http://localhost:8000/mcp",
        authorization_servers=["http://localhost:3000/oauth"],
        scopes_supported=["flight:read", "flight:write"],
        token_introspection_endpoint="http://localhost:3000/oauth/introspect"
    )

    guard = OAuthGuard()

    # Case A: Missing Authorization Header
    ctx_missing = ExecutionContext(
        request_id="test-req-1",
        tool_name="test-tool",
        logger=MagicMock(),
        metadata={}
    )
    res_missing = await guard.can_activate(ctx_missing)
    print("Missing authorization header check:", res_missing)
    assert res_missing is False

    # Case B: Malformed Authorization Header (no Bearer prefix)
    ctx_malformed = ExecutionContext(
        request_id="test-req-2",
        tool_name="test-tool",
        logger=MagicMock(),
        metadata={"authorization": "Basic abcdef"}
    )
    res_malformed = await guard.can_activate(ctx_malformed)
    print("Malformed authorization header check:", res_malformed)
    assert res_malformed is False

    # Case C: Valid Bearer Token but Introspection returns active = False
    ctx_invalid = ExecutionContext(
        request_id="test-req-3",
        tool_name="test-tool",
        logger=MagicMock(),
        metadata={"authorization": "Bearer invalid-token"}
    )
    
    # Mock introspect_token to return inactive
    oauth_service = DIContainer.get_instance().resolve(OAuthService)
    
    with patch.object(oauth_service, 'introspect_token', return_value={"active": False}) as mock_introspect:
        res_invalid = await guard.can_activate(ctx_invalid)
        print("Invalid token check:", res_invalid)
        assert res_invalid is False
        mock_introspect.assert_called_once_with("invalid-token")

    # Case D: Valid Bearer Token and Introspection returns active = True with scopes
    ctx_valid = ExecutionContext(
        request_id="test-req-4",
        tool_name="test-tool",
        logger=MagicMock(),
        metadata={"authorization": "Bearer valid-token"}
    )

    introspection_payload = {
        "active": True,
        "scope": "flight:read flight:write",
        "sub": "user_12345",
        "client_id": "client_abc",
        "exp": 1900000000
    }

    with patch.object(oauth_service, 'introspect_token', return_value=introspection_payload) as mock_introspect:
        res_valid = await guard.can_activate(ctx_valid)
        print("Valid token check:", res_valid)
        assert res_valid is True
        mock_introspect.assert_called_once_with("valid-token")
        
        # Verify AuthContext properties populated on the context
        assert ctx_valid.auth is not None
        assert ctx_valid.auth.subject == "user_12345"
        assert "flight:read" in ctx_valid.auth.scopes
        assert "flight:write" in ctx_valid.auth.scopes
        assert ctx_valid.auth.client_id == "client_abc"

    print("Success! OAuthGuard and OAuth 2.1 token validations work perfectly.")

def test_oauth_guard_validation():
    asyncio.run(_test_oauth_guard_validation())

if __name__ == "__main__":
    test_oauth_guard_validation()
