from __future__ import annotations

import uuid

from parcel_shell.auth.cookies import sign_session_id, verify_session_cookie


def test_sign_then_verify_roundtrip() -> None:
    sid = uuid.uuid4()
    token = sign_session_id(sid, secret="a" * 32)
    assert verify_session_cookie(token, secret="a" * 32) == sid


def test_verify_rejects_tampered_token() -> None:
    sid = uuid.uuid4()
    token = sign_session_id(sid, secret="a" * 32)
    tampered = token[:-2] + ("zz" if not token.endswith("zz") else "aa")
    assert verify_session_cookie(tampered, secret="a" * 32) is None


def test_verify_rejects_wrong_secret() -> None:
    sid = uuid.uuid4()
    token = sign_session_id(sid, secret="a" * 32)
    assert verify_session_cookie(token, secret="b" * 32) is None


def test_verify_rejects_malformed_token() -> None:
    assert verify_session_cookie("", secret="a" * 32) is None
    assert verify_session_cookie("garbage", secret="a" * 32) is None
    assert verify_session_cookie("only-one-half", secret="a" * 32) is None


def test_verify_rejects_non_uuid_payload() -> None:
    from itsdangerous import URLSafeSerializer

    forged = URLSafeSerializer("a" * 32, salt="parcel.session.v1").dumps("not-a-uuid")
    assert verify_session_cookie(forged, secret="a" * 32) is None
