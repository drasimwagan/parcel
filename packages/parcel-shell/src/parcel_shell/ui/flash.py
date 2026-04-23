from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from itsdangerous import BadSignature, URLSafeSerializer

COOKIE_NAME = "parcel_flash"
_SALT = "parcel.flash.v1"

FlashKind = Literal["success", "error", "info"]


@dataclass(frozen=True)
class Flash:
    kind: FlashKind
    msg: str


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
