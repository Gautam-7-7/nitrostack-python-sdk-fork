import time
import json
import os
import jwt
from typing import Any, Dict, Optional
from nitrostack.core.module import module
from nitrostack.core.di import DIContainer

class JWTService:
    def __init__(
        self,
        secret_env_var: str = "JWT_SECRET",
        secret_key: Optional[str] = None,
        secret: Optional[str] = None,
        expires_in: str = "24h",
        audience: Optional[str] = None,
        issuer: Optional[str] = None,
    ):
        self.secret_env_var = secret_env_var
        self.secret_key = secret_key or secret
        self.expires_in = expires_in
        self.audience = audience
        self.issuer = issuer

    def get_secret(self) -> str:
        if self.secret_key:
            return self.secret_key
        secret = os.environ.get(self.secret_env_var)
        if not secret:
            # Fallback for dev mode/testing so it doesn't fail hard if not set
            secret = "dev_default_secret_key_nitrostack"
        return secret

    def create_token(self, payload: Dict[str, Any]) -> str:
        # Calculate expiration
        payload_copy = payload.copy()
        if "exp" not in payload_copy:
            # Parse expires_in
            seconds = 86400
            try:
                if self.expires_in.endswith("h"):
                    seconds = int(self.expires_in[:-1]) * 3600
                elif self.expires_in.endswith("m"):
                    seconds = int(self.expires_in[:-1]) * 60
                elif self.expires_in.endswith("s"):
                    seconds = int(self.expires_in[:-1])
                elif self.expires_in.isdigit():
                    seconds = int(self.expires_in)
            except Exception:
                pass
            payload_copy["exp"] = int(time.time()) + seconds
        
        if self.audience and "aud" not in payload_copy:
            payload_copy["aud"] = self.audience
        if self.issuer and "iss" not in payload_copy:
            payload_copy["iss"] = self.issuer
        if "iat" not in payload_copy:
            payload_copy["iat"] = int(time.time())

        secret = self.get_secret()
        return jwt.encode(payload_copy, secret, algorithm="HS256")

    def verify_token(self, token: str) -> Dict[str, Any]:
        secret = self.get_secret()
        try:
            return jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience=self.audience,
                issuer=self.issuer
            )
        except jwt.ExpiredSignatureError as e:
            raise ValueError("Token has expired.") from e
        except jwt.InvalidAudienceError as e:
            raise ValueError("Audience mismatch.") from e
        except jwt.InvalidIssuerError as e:
            raise ValueError("Issuer mismatch.") from e
        except jwt.InvalidTokenError as e:
            raise ValueError("Invalid signature.") from e
        except Exception as e:
            raise ValueError(f"Invalid token: {e}") from e

@module(name="JWTModule")
class JWTModule:
    @classmethod
    def for_root(
        cls,
        secret_env_var: str = "JWT_SECRET",
        secret_key: Optional[str] = None,
        secret: Optional[str] = None,
        expires_in: str = "24h",
        audience: Optional[str] = None,
        issuer: Optional[str] = None,
        algorithms: Optional[Any] = None,
    ):
        service = JWTService(
            secret_env_var=secret_env_var,
            secret_key=secret_key,
            secret=secret,
            expires_in=expires_in,
            audience=audience,
            issuer=issuer
        )
        DIContainer.get_instance().register_value(JWTService, service)
        return cls

JwtModule = JWTModule

