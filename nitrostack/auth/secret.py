import os
import sys
import warnings
from typing import Any, Optional, Union

class SecretValue:
    def __init__(self, value: str, source: str = "env"):
        if not value:
            raise ValueError("Secret value cannot be empty")
        
        if len(value) < 16:
            warnings.warn(
                "[SecretValue] Warning: Secret is less than 16 characters. "
                "Consider using a longer secret for better security.",
                UserWarning
            )
        self._value = value
        self.source = source

    @classmethod
    def from_env(cls, env_var_name: str, required: bool = True) -> "SecretValue":
        value = os.environ.get(env_var_name)
        if not value:
            if required:
                raise ValueError(
                    f"Environment variable {env_var_name} is not set. "
                    "Please set it in your environment or .env file."
                )
            raise ValueError(f"Environment variable {env_var_name} is not set.")
        return cls(value, "env")

    @classmethod
    def fromEnv(cls, env_var_name: str, required: bool = True) -> "SecretValue":
        return cls.from_env(env_var_name, required)

    @classmethod
    def from_value(cls, value: str, allow_hardcoded: bool = False, reason: Optional[str] = None) -> "SecretValue":
        if not allow_hardcoded:
            raise ValueError(
                "Hardcoded secrets are not allowed. "
                "Use SecretValue.from_env() to load secrets from environment variables. "
                "If you must use a hardcoded value (e.g., for testing), "
                "set allow_hardcoded=True explicitly."
            )
        
        node_env = os.environ.get("NODE_ENV", "development").lower()
        if node_env != "test":
            sys.stderr.write(
                f"[SecretValue] Warning: Using hardcoded secret value. "
                f"Reason: {reason or 'Not specified'}. "
                "This should not be used in production.\n"
            )
        return cls(value, "explicit")

    @classmethod
    def fromValue(cls, value: str, options: Optional[dict] = None) -> "SecretValue":
        options = options or {}
        allow_hardcoded = options.get("allowHardcoded", False)
        reason = options.get("reason")
        return cls.from_value(value, allow_hardcoded=allow_hardcoded, reason=reason)

    @classmethod
    def from_env_optional(cls, env_var_name: str) -> Optional["SecretValue"]:
        value = os.environ.get(env_var_name)
        if not value:
            return None
        return cls(value, "env")

    @classmethod
    def fromEnvOptional(cls, env_var_name: str) -> Optional["SecretValue"]:
        return cls.from_env_optional(env_var_name)

    def unwrap(self) -> str:
        return self._value

    def getValue(self) -> str:
        return self._value

    def is_from_environment(self) -> bool:
        return self.source == "env"

    def isFromEnvironment(self) -> bool:
        return self.is_from_environment()

    def __str__(self) -> str:
        return "[SecretValue: REDACTED]"

    def __repr__(self) -> str:
        return f"SecretValue(source='{self.source}', value=[REDACTED])"

def is_secret_value(value: Any) -> bool:
    return isinstance(value, SecretValue)

def unwrap_secret(secret: Union[SecretValue, str]) -> str:
    if isinstance(secret, SecretValue):
        return secret.unwrap()
    
    node_env = os.environ.get("NODE_ENV", "development").lower()
    if node_env == "production":
        sys.stderr.write(
            "[SecretValue] Warning: Using raw string as secret. "
            "Consider migrating to SecretValue.from_env() for better security.\n"
        )
    return secret
