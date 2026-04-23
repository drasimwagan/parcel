from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.rbac.models import Permission


@dataclass(frozen=True)
class RegisteredPermission:
    name: str
    description: str
    module: str = "shell"


class PermissionRegistry:
    def __init__(self) -> None:
        self._items: dict[str, RegisteredPermission] = {}

    def register(self, name: str, description: str, module: str = "shell") -> None:
        existing = self._items.get(name)
        if existing is None:
            self._items[name] = RegisteredPermission(name=name, description=description, module=module)
            return
        if existing.description != description or existing.module != module:
            raise ValueError(f"permission {name!r} re-registered with different attributes")

    def all(self) -> list[RegisteredPermission]:
        return list(self._items.values())

    async def sync_to_db(self, session: AsyncSession) -> None:
        if not self._items:
            return
        payload = [
            {"name": p.name, "description": p.description, "module": p.module}
            for p in self._items.values()
        ]
        stmt = insert(Permission).values(payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Permission.name],
            set_={
                "description": stmt.excluded.description,
                "module": stmt.excluded.module,
            },
        )
        await session.execute(stmt)


SHELL_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("users.read", "List and view user accounts"),
    ("users.write", "Create, update, and deactivate user accounts"),
    ("roles.read", "List and view roles"),
    ("roles.write", "Create, update, and delete roles; assign permissions to roles"),
    ("users.roles.assign", "Assign and unassign roles on users"),
    ("sessions.read", "List another user's sessions"),
    ("sessions.revoke", "Revoke another user's sessions"),
    ("permissions.read", "List registered permissions"),
)


def register_shell_permissions(registry: PermissionRegistry) -> None:
    for name, description in SHELL_PERMISSIONS:
        registry.register(name, description, module="shell")


# Global singleton. Shell registers into this at import time (below); modules
# register into the same instance in Phase 3 before lifespan startup.
registry = PermissionRegistry()
register_shell_permissions(registry)
