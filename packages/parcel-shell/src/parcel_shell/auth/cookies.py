from __future__ import annotations

import uuid

from itsdangerous import BadSignature, URLSafeSerializer

_SALT = "parcel.session.v1"


def _serializer(secret: str) -> URLSafeSerializer:
    return URLSafeSerializer(secret, salt=_SALT)


def sign_session_id(session_id: uuid.UUID, *, secret: str) -> str:
    return _serializer(secret).dumps(str(session_id))


def verify_session_cookie(token: str, *, secret: str) -> uuid.UUID | None:
    if not token:
        return None
    try:
        raw = _serializer(secret).loads(token)
    except BadSignature:
        return None
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(raw, str):
        return None
    try:
        return uuid.UUID(raw)
    except (ValueError, TypeError):
        return None
