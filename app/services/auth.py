import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone, timedelta

SECRET_KEY_ENV = "DOCUDEX_JWT_SECRET"
DEFAULT_EXPIRY_HOURS = 1


def _get_secret():
    secret = os.environ.get(SECRET_KEY_ENV)
    if not secret:
        secret = secrets.token_hex(32)
        os.environ[SECRET_KEY_ENV] = secret
        print(f"[docudex] Generated new JWT secret. Set {SECRET_KEY_ENV} to persist across restarts.")
    return secret


def _b64url_encode(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64url_decode(s):
    s = s + "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def generate_nonce():
    return secrets.token_hex(16)


def generate_pairing_token():
    return "dpx_" + secrets.token_hex(32)


def generate_jwt(agent_id, secret=None):
    if secret is None:
        secret = _get_secret()
    now = int(datetime.now(timezone.utc).timestamp())
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}))
    payload = _b64url_encode(json.dumps({
        "sub": agent_id,
        "iat": now,
        "exp": now + (DEFAULT_EXPIRY_HOURS * 3600),
        "jti": secrets.token_hex(8),
    }))
    signing_input = f"{header}.{payload}"
    signature = _b64url_encode(
        hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    )
    return f"{signing_input}.{signature}"


def decode_jwt(token, secret=None):
    if secret is None:
        secret = _get_secret()
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, signature = parts
        signing_input = f"{header}.{payload}"
        expected_sig = _b64url_encode(
            hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected_sig):
            return None
        decoded = json.loads(_b64url_decode(payload))
        now = int(datetime.now(timezone.utc).timestamp())
        if decoded.get("exp", 0) < now:
            return None
        return decoded
    except Exception:
        return None


def verify_token(token):
    if not token:
        return None
    if not token.startswith("Bearer "):
        return None
    actual_token = token[7:]
    return decode_jwt(actual_token)
