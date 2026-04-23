from __future__ import annotations

from parcel_shell.auth.hashing import hash_password, needs_rehash, verify_password


def test_hash_password_returns_argon2_string() -> None:
    h = hash_password("correct horse battery staple")
    assert h.startswith("$argon2")
    assert len(h) > 50


def test_verify_roundtrip() -> None:
    h = hash_password("swordfish-123!")
    assert verify_password(h, "swordfish-123!") is True


def test_verify_rejects_wrong_password() -> None:
    h = hash_password("swordfish-123!")
    assert verify_password(h, "something-else") is False


def test_verify_handles_malformed_hash() -> None:
    assert verify_password("not-a-real-hash", "whatever") is False


def test_needs_rehash_false_for_fresh_hash() -> None:
    h = hash_password("pw-twelve-chars")
    assert needs_rehash(h) is False
