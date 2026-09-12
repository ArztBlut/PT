"""Password hashing, session fingerprints and a simple sign-in throttle."""

from __future__ import annotations

import hashlib
import threading
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


def session_fingerprint(password_hash: str) -> str:
    """Stored in the session so a password change signs out other sessions."""
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()[:24]


# Verified against when a username doesn't exist, so response timing doesn't reveal it.
DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password")


class LoginThrottle:
    """Blocks a client/username pair after repeated failures. In-memory, per process."""

    def __init__(self, max_failures: int = 10, window_seconds: int = 900) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        attempts = [t for t in self._failures.get(key, []) if now - t < self.window]
        if attempts:
            self._failures[key] = attempts
        else:
            self._failures.pop(key, None)
        return attempts

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key, time.monotonic())) >= self.max_failures

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._failures[key] = [*self._recent(key, now), now]

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
