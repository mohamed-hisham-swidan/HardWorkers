"""API key encryption helpers using Fernet symmetric encryption and JWT token helpers."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

try:
    from jose import JWTError, jwt
except ImportError:
    jwt = None  # type: ignore[assignment]
    JWTError = Exception


# ── Token revocation store (in-memory, for multi-worker use Redis) ────────────
_REVOKED_TOKENS: set[str] = set()


def revoke_token(jti: str) -> None:
    _REVOKED_TOKENS.add(jti)


def is_token_revoked(jti: str) -> bool:
    return jti in _REVOKED_TOKENS


def get_master_key(key_path: Path | None = None) -> bytes:
    """Retrieve the Fernet master key from env var or file on disk.

    The environment variable ``HARDWORKERS_MASTER_KEY`` takes precedence.
    If it is not set the key is read from *key_path* (default
    ``./.master_key``).  If neither exists a new key is generated, written to
    *key_path* and returned.
    """
    env_key = os.environ.get("HARDWORKERS_MASTER_KEY")
    if env_key:
        return env_key.encode("utf-8")
    if key_path is None:
        key_path = Path(".master_key")
    if key_path.exists():
        return key_path.read_bytes()
    key = Fernet.generate_key()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key)
    return key


def rotate_key(old_key: bytes, new_key: bytes, store, batch_size: int = 100) -> int:
    """Re-encrypt all secrets in *store* from *old_key* to *new_key*.

    Returns the number of re-encrypted values.
    """
    count = 0
    for provider in ("openai", "anthropic", "openrouter", "groq", "gemini", "deepseek", "together"):
        cipher = store.get_setting(f"api_key_{provider}")
        if cipher:
            plain = decrypt_value(cipher, old_key)
            if plain:
                new_cipher = encrypt_value(plain, new_key)
                store.set_setting(f"api_key_{provider}", new_cipher)
                count += 1
    return count


def encrypt_value(plaintext: str, key: bytes) -> str:
    if not plaintext:
        return ""
    return Fernet(key).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str, key: bytes) -> str:
    if not ciphertext:
        return ""
    try:
        return Fernet(key).decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception):
        return ciphertext


# ── JWT helpers (used by FastAPI auth) ─────────────────────────────────────────


def create_token(
    payload: dict,
    secret: str,
    expires_delta: timedelta | None = None,
    jti: str | None = None,
) -> str:
    if jwt is None:
        raise ImportError("python-jose is required for JWT support")
    to_encode = payload.copy()
    now = datetime.now(UTC)
    to_encode.update({
        "iat": now,
        "exp": now + (expires_delta or timedelta(hours=24)),
        "jti": jti or os.urandom(16).hex(),
    })
    return jwt.encode(to_encode, secret, algorithm="HS256")


def verify_token(token: str, secret: str) -> dict | None:
    if jwt is None:
        raise ImportError("python-jose is required for JWT support")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        jti = payload.get("jti", "")
        if jti and is_token_revoked(jti):
            return None
        return payload
    except JWTError:
        return None
