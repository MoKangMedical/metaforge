"""
MetaForge Authentication Module

Provides:
- Password hashing with SHA-256 (lightweight, no bcrypt dependency)
- JWT-like token generation and validation
- API quota checking
"""

import os
import hashlib
import json
import time
import uuid
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict


SECRET_KEY = os.environ.get("META_FORGE_SECRET", "metaforge-secret-key-change-in-production-2026")
TOKEN_EXPIRY_HOURS = 72  # 3 days


def hash_password(password: str) -> str:
    """Hash a password with SHA-256 + salt."""
    salt = "metaforge-salt-2026"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return hash_password(password) == password_hash


def generate_token(user_id: int, username: str) -> str:
    """Generate a simple session token."""
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": (datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)).isoformat(),
        "iat": datetime.utcnow().isoformat(),
        "jti": str(uuid.uuid4()),
    }
    # Simple base64 encoding (not cryptographic, but functional)
    token_data = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    signature = hashlib.sha256(f"{token_data}{SECRET_KEY}".encode()).hexdigest()[:16]
    return f"{token_data}.{signature}"


def validate_token(token: str) -> Optional[Dict]:
    """Validate a token and return the payload."""
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None

        token_data, signature = parts
        expected_sig = hashlib.sha256(f"{token_data}{SECRET_KEY}".encode()).hexdigest()[:16]

        if signature != expected_sig:
            return None

        payload = json.loads(base64.urlsafe_b64decode(token_data))
        exp = datetime.fromisoformat(payload["exp"])
        if datetime.utcnow() > exp:
            return None

        return payload
    except Exception:
        return None


def check_api_quota(user) -> bool:
    """Check if user has remaining API quota."""
    if user.api_calls_limit == -1:  # Unlimited
        return True
    return user.api_calls_today < user.api_calls_limit


def increment_api_usage(user, db):
    """Increment user's API call counter."""
    user.api_calls_today += 1
    db.commit()
