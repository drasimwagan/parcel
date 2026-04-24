from __future__ import annotations

from itsdangerous import BadSignature, URLSafeSerializer

from parcel_sdk.shell_api import Flash, FlashKind

__all__ = ["COOKIE_NAME", "Flash", "FlashKind", "pack", "unpack"]

COOKIE_NAME = "parcel_flash"
_SALT = "parcel.flash.v1"


def _serializer(secret: str) -> URLSafeSerializer:
    return URLSafeSerializer(secret, salt=_SALT)


def pack(flash: Flash, *, secret: str) -> str:
    return _serializer(secret).dumps({"kind": flash.kind, "msg": flash.msg})


def unpack(token: str, *, secret: str) -> Flash | None:
    if not token:
        return None
    try:
        raw = _serializer(secret).loads(token)
    except BadSignature:
        return None
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind")
    msg = raw.get("msg")
    if kind not in ("success", "error", "info") or not isinstance(msg, str):
        return None
    return Flash(kind=kind, msg=msg)
