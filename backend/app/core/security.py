import hashlib
import hmac
import secrets


def generate_otp() -> str:
    """Generate a cryptographically secure 6-digit numeric OTP."""
    code = secrets.randbelow(1_000_000)
    return f"{code:06d}"


def hash_otp(otp: str, salt_bytes: bytes | None = None) -> tuple[str, str]:
    """Hash OTP using PBKDF2-HMAC-SHA256 with a random 16-byte salt.

    Returns (salt_hex, hash_hex).
    """
    salt = salt_bytes or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", otp.encode("utf-8"), salt, 10_000)
    return salt.hex(), derived.hex()


def verify_otp(otp: str, salt_hex: str, hash_hex: str) -> bool:
    """Verify OTP against salted PBKDF2-HMAC-SHA256 hash in constant time."""
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        derived = hashlib.pbkdf2_hmac("sha256", otp.encode("utf-8"), salt, 10_000)
        return hmac.compare_digest(derived, expected)
    except Exception:
        return False


def generate_session_token() -> tuple[str, str]:
    """Generate a high-entropy session token and its SHA-256 storage hash.

    Returns (raw_token, token_hash).
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return raw_token, token_hash


def hash_session_token(raw_token: str) -> str:
    """Hash raw session token using SHA-256 for lookup."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def hash_password(password: str, salt_bytes: bytes | None = None) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with 100,000 iterations.

    Returns formatted string: 'pbkdf2:sha256:100000$<salt_hex>$<hash_hex>'
    """
    salt = salt_bytes or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"pbkdf2:sha256:100000${salt.hex()}${derived.hex()}"


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    """Verify plain password against PBKDF2-HMAC-SHA256 hash in constant time."""
    if not hashed_password or not isinstance(hashed_password, str):
        return False
    try:
        parts = hashed_password.split("$")
        if len(parts) != 3:
            return False
        algo_iter, salt_hex, expected_hex = parts
        _, _, iterations_str = algo_iter.split(":")
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(expected_hex)
        derived = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(derived, expected)
    except Exception:
        return False

