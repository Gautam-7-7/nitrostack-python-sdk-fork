import time
import pytest
import jwt
import os
from nitrostack.auth.jwt import JWTService

def test_jwt_standard_verification():
    # Setup JWTService
    service = JWTService(
        secret_env_var="TEST_JWT_SECRET",
        expires_in="1s",  # expires in 1s for testing
        audience="test-audience",
        issuer="test-issuer"
    )
    os.environ["TEST_JWT_SECRET"] = "my-test-super-secret-key-12345"

    payload = {"sub": "user-456", "scopes": ["read", "write"]}

    # Create token
    token = service.create_token(payload)
    assert token is not None

    # Verify standard PyJWT signature under the hood
    decoded_raw = jwt.decode(
        token,
        "my-test-super-secret-key-12345",
        algorithms=["HS256"],
        audience="test-audience",
        issuer="test-issuer"
    )
    assert decoded_raw["sub"] == "user-456"

    # Verify token through service
    res = service.verify_token(token)
    assert res["sub"] == "user-456"
    assert res["aud"] == "test-audience"
    assert res["iss"] == "test-issuer"

    # Test audience mismatch
    bad_service = JWTService(
        secret_env_var="TEST_JWT_SECRET",
        expires_in="1h",
        audience="mismatch-audience",
        issuer="test-issuer"
    )
    with pytest.raises(ValueError, match="Audience mismatch"):
        bad_service.verify_token(token)

    # Test issuer mismatch
    bad_service_iss = JWTService(
        secret_env_var="TEST_JWT_SECRET",
        expires_in="1h",
        audience="test-audience",
        issuer="mismatch-issuer"
    )
    with pytest.raises(ValueError, match="Issuer mismatch"):
        bad_service_iss.verify_token(token)

    # Test token expiration
    time.sleep(1.2)
    with pytest.raises(ValueError, match="Token has expired"):
        service.verify_token(token)

    # Test invalid signature
    bad_token = token[:-5] + "abcde"
    with pytest.raises(ValueError, match="Invalid signature"):
        service.verify_token(bad_token)


def test_jwt_module_explicit_secret_key_and_aliases():
    from nitrostack import JwtModule, JWTModule, OauthModule, OAuthModule, APIKeyModule, ApiKeyModule

    assert JwtModule is JWTModule
    assert OauthModule is OAuthModule
    assert APIKeyModule is ApiKeyModule

    service = JWTService(secret_key="explicit_secret_key_string_32bytes!")
    token = service.create_token({"sub": "test-user-789"})
    verified = service.verify_token(token)
    assert verified["sub"] == "test-user-789"

