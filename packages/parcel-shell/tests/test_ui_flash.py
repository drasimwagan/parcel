from __future__ import annotations

from parcel_shell.ui.flash import COOKIE_NAME, Flash, pack, unpack


def test_pack_unpack_roundtrip() -> None:
    token = pack(Flash(kind="success", msg="done"), secret="a" * 32)
    got = unpack(token, secret="a" * 32)
    assert got == Flash(kind="success", msg="done")


def test_unpack_tampered_returns_none() -> None:
    token = pack(Flash(kind="error", msg="oops"), secret="a" * 32)
    tampered = token[:-2] + ("zz" if not token.endswith("zz") else "aa")
    assert unpack(tampered, secret="a" * 32) is None


def test_unpack_wrong_secret_returns_none() -> None:
    token = pack(Flash(kind="info", msg="hi"), secret="a" * 32)
    assert unpack(token, secret="b" * 32) is None


def test_unpack_garbage_returns_none() -> None:
    assert unpack("", secret="a" * 32) is None
    assert unpack("not-a-token", secret="a" * 32) is None


def test_cookie_name_constant() -> None:
    assert COOKIE_NAME == "parcel_flash"
