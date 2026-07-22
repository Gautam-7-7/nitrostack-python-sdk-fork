import os
import json
import time
import hashlib
from typing import Dict, List, Optional, Union, Any
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

class StoredToken:
    def __init__(
        self,
        access_token: str,
        token_type: str,
        expires_at: int,
        refresh_token: Optional[str] = None,
        scope: Optional[str] = None,
        resource: Optional[str] = None,
    ):
        self.access_token = access_token
        self.token_type = token_type
        self.expires_at = expires_at
        self.refresh_token = refresh_token
        self.scope = scope
        self.resource = resource

    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_at": self.expires_at,
            "refresh_token": self.refresh_token,
            "scope": self.scope,
            "resource": self.resource,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StoredToken":
        return cls(
            access_token=d["access_token"],
            token_type=d["token_type"],
            expires_at=d["expires_at"],
            refresh_token=d.get("refresh_token"),
            scope=d.get("scope"),
            resource=d.get("resource"),
        )

class MemoryTokenStore:
    def __init__(self):
        self.tokens: Dict[str, StoredToken] = {}

    async def save_token(self, key: str, token: StoredToken) -> None:
        self.tokens[key] = token

    async def saveToken(self, key: str, token: Union[StoredToken, Dict[str, Any]]) -> None:
        if isinstance(token, dict):
            token = StoredToken.from_dict(token)
        await self.save_token(key, token)

    async def get_token(self, key: str) -> Optional[StoredToken]:
        token = self.tokens.get(key)
        if not token:
            return None
        if is_token_expired(token):
            self.tokens.pop(key, None)
            return None
        return token

    async def getToken(self, key: str) -> Optional[Dict[str, Any]]:
        t = await self.get_token(key)
        return t.to_dict() if t else None

    async def delete_token(self, key: str) -> None:
        self.tokens.pop(key, None)

    async def deleteToken(self, key: str) -> None:
        await self.delete_token(key)

    async def list_keys(self) -> List[str]:
        return list(self.tokens.keys())

    async def listKeys(self) -> List[str]:
        return await self.list_keys()

    async def clear(self) -> None:
        self.tokens.clear()

class FileTokenStore:
    def __init__(self, store_path: str, encryption_key: Optional[str] = None):
        self.store_path = store_path
        self.encryption_key = encryption_key

    async def save_token(self, key: str, token: StoredToken) -> None:
        tokens = await self._load_tokens()
        tokens[key] = token.to_dict()
        await self._save_tokens(tokens)

    async def saveToken(self, key: str, token: Union[StoredToken, Dict[str, Any]]) -> None:
        if isinstance(token, dict):
            token = StoredToken.from_dict(token)
        await self.save_token(key, token)

    async def get_token(self, key: str) -> Optional[StoredToken]:
        tokens = await self._load_tokens()
        token_dict = tokens.get(key)
        if not token_dict:
            return None
        token = StoredToken.from_dict(token_dict)
        if is_token_expired(token):
            tokens.pop(key, None)
            await self._save_tokens(tokens)
            return None
        return token

    async def getToken(self, key: str) -> Optional[Dict[str, Any]]:
        t = await self.get_token(key)
        return t.to_dict() if t else None

    async def delete_token(self, key: str) -> None:
        tokens = await self._load_tokens()
        tokens.pop(key, None)
        await self._save_tokens(tokens)

    async def deleteToken(self, key: str) -> None:
        await self.delete_token(key)

    async def list_keys(self) -> List[str]:
        tokens = await self._load_tokens()
        return list(tokens.keys())

    async def listKeys(self) -> List[str]:
        return await self.list_keys()

    async def clear(self) -> None:
        await self._save_tokens({})

    async def _load_tokens(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(self.store_path):
            return {}
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                data = f.read()
            content = self._decrypt(data)
            return json.loads(content)
        except Exception:
            return {}

    async def _save_tokens(self, tokens: Dict[str, Dict[str, Any]]) -> None:
        dir_name = os.path.dirname(self.store_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        content = json.stringify(tokens, indent=2) if hasattr(json, "stringify") else json.dumps(tokens, indent=2)
        data = self._encrypt(content)
        with open(self.store_path, "w", encoding="utf-8") as f:
            f.write(data)
        try:
            os.chmod(self.store_path, 0o600)
        except Exception:
            pass

    def _derive_key(self, password: str) -> bytes:
        salt = b"nitrostack-token-store"
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000, 32)

    def _encrypt(self, data: str) -> str:
        if not self.encryption_key:
            return data
        key = self._derive_key(self.encryption_key)
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(key), modes.GCM(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(data.encode("utf-8")) + encryptor.finalize()
        tag = encryptor.tag
        return f"{iv.hex()}:{tag.hex()}:{ciphertext.hex()}"

    def _decrypt(self, data: str) -> str:
        if not self.encryption_key:
            return data
        key = self._derive_key(self.encryption_key)
        parts = data.split(":")
        if len(parts) != 3:
            raise ValueError("Invalid encrypted data format")
        iv = bytes.fromhex(parts[0])
        tag = bytes.fromhex(parts[1])
        ciphertext = bytes.fromhex(parts[2])
        cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag), backend=default_backend())
        decryptor = cipher.decryptor()
        return (decryptor.update(ciphertext) + decryptor.finalize()).decode("utf-8")

def is_token_expired(token: StoredToken) -> bool:
    return int(time.time() * 1000) > token.expires_at

def calculate_expiration(expires_in: int) -> int:
    return int(time.time() * 1000) + expires_in * 1000

def token_response_to_stored(response: Dict[str, Any], resource: Optional[str] = None) -> StoredToken:
    expires_in = response.get("expires_in")
    expires_at = calculate_expiration(expires_in) if expires_in else int(time.time() * 1000) + 3600000
    return StoredToken(
        access_token=response["access_token"],
        token_type=response.get("token_type", "Bearer"),
        expires_at=expires_at,
        refresh_token=response.get("refresh_token"),
        scope=response.get("scope"),
        resource=resource,
    )

def get_default_store_path() -> str:
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or ""
    return os.path.join(home, ".nitrostack", "tokens.json")

def create_default_token_store(store_path: Optional[str] = None, encryption_key: Optional[str] = None) -> Union[FileTokenStore, MemoryTokenStore]:
    path = store_path or get_default_store_path()
    return FileTokenStore(path, encryption_key)
