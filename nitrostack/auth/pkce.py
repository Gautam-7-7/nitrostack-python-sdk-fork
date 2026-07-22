import os
import base64
import hashlib
import re
from typing import Dict, Optional, Union

def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

def generate_code_verifier() -> str:
    # 32 random bytes (256 bits of entropy)
    random_bytes = os.urandom(32)
    return base64url_encode(random_bytes)

def generateCodeVerifier() -> str:
    return generate_code_verifier()

def generate_code_challenge(code_verifier: str, method: str = "S256") -> str:
    if method == "plain":
        return code_verifier
    
    # S256 method
    # code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
    hash_obj = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64url_encode(hash_obj)

def generateCodeChallenge(code_verifier: str, method: str = "S256") -> str:
    return generate_code_challenge(code_verifier, method)

def generate_pkce_params(method: str = "S256") -> Dict[str, str]:
    verifier = generate_code_verifier()
    challenge = generate_code_challenge(verifier, method)
    return {
        "code_verifier": verifier,
        "code_challenge": challenge,
        "code_challenge_method": method,
    }

def generatePKCEParams(method: str = "S256") -> Dict[str, str]:
    return generate_pkce_params(method)

def verify_pkce(code_verifier: str, code_challenge: str, method: str) -> bool:
    computed = generate_code_challenge(code_verifier, method)
    return computed == code_challenge

def verifyPKCE(code_verifier: str, code_challenge: str, method: str) -> bool:
    return verify_pkce(code_verifier, code_challenge, method)

def is_valid_code_verifier(verifier: str) -> bool:
    if len(verifier) < 43 or len(verifier) > 128:
        return False
    # Only A-Z, a-z, 0-9, -, ., _, ~
    return bool(re.match(r"^[A-Za-z0-9\-._~]+$", verifier))

def isValidCodeVerifier(verifier: str) -> bool:
    return is_valid_code_verifier(verifier)

def validate_pkce_support(supported_methods: Optional[list]) -> bool:
    if not supported_methods:
        return False
    return "S256" in supported_methods

def validatePKCESupport(supported_methods: Optional[list]) -> bool:
    return validate_pkce_support(supported_methods)
