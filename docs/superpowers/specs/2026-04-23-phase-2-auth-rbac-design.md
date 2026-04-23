# Phase 2 — Auth + RBAC Design

**Date:** 2026-04-23
**Phase:** 2 (next after Phase 1 — shell foundation)
**Goal (from `CLAUDE.md`):** Auth + RBAC — users, sessions, Argon2, roles, permissions registry.

## Scope

Phase 2 delivers an API-only authentication and authorization layer on top of the Phase 1 shell:

- User accounts (email + Argon2id password hash)
- Server-side sessions keyed by a signed cookie
- Roles + permissions with a registry seam that modules will use in Phase 3
- JSON `/auth/*` and `/admin/*` endpoints
- A `python -m parcel_shell.bootstrap create-admin` command to seed the first admin user
- Full pytest coverage against the existing testcontainers Postgres

Phase 2 does **not** deliver: any HTML/login UI (Phase 4), module-driven permission registration (Phase 3), a `parcel` CLI proper (Phase 6), OIDC/SAML/API-keys (locked out per CLAUDE.md), rate limiting, password reset, email verification, or multi-tenancy.

## Locked decisions from brainstorming

| Question | Decision |
|---|---|
| UI surface | API-only. HTML login lands in Phase 4. |
| Session storage | Signed-cookie carrying a server-side session ID; sessions row in `shell.sessions`. |
| Password hashing | Argon2id via `argon2-cffi` with library defaults. Min length 12. |
| Rate limiting / lockout | Out of scope. Failed logins logged as structured events. |
| DELETE user semantics | Soft (deactivate + revoke sessions). Hard delete deferred. |
| First admin | `python -m parcel_shell.bootstrap create-admin ...` |
| Built-in admin role | Seeded in `0002_auth_rbac` migration, holds every shell permission, cannot be deleted. |

## Package layout additions

```
packages/parcel-shell/src/parcel_shell/
  auth/
    __init__.py
    hashing.py              # Argon2id wrappers + rehash detection
    cookies.py              # sign/verify the session-id cookie
    sessions.py             # create/validate/revoke/bump session helpers
    dependencies.py         # current_user, require_permission FastAPI deps
    router.py               # /auth/* endpoints
  rbac/
    __init__.py
    registry.py             # PermissionRegistry + shell-permissions registration
    models.py               # SQLAlchemy models: User, Session, Role, Permission + association tables
    service.py              # pure service functions over AsyncSession
    router_admin.py         # /admin/* endpoints
  bootstrap.py              # python -m parcel_shell.bootstrap ...
  alembic/versions/
    0002_auth_rbac.py       # new migration
```

Test file additions:

```
packages/parcel-shell/tests/
  test_hashing.py
  test_cookies.py
  test_sessions.py
  test_registry.py
  test_rbac_service.py
  test_auth_router.py
  test_admin_users_router.py
  test_admin_roles_router.py
  test_admin_sessions_router.py
  test_bootstrap.py
  test_auth_integration.py
```

### Module boundaries

- **`auth/hashing.py`** — pure: wraps `PasswordHasher`, exposes `hash_password`, `verify_password`, `needs_rehash`. No I/O, no DB.
- **`auth/cookies.py`** — pure: `sign(session_id)` / `verify(value) -> session_id | None`. HMAC-SHA256 with `settings.session_secret`. No I/O, no DB.
- **`auth/sessions.py`** — takes an `AsyncSession`: `create_session(user_id, ip, ua) -> Session`, `lookup(session_id) -> Session | None`, `bump(session) -> None`, `revoke(session) -> None`. Enforces absolute + idle TTLs.
- **`auth/dependencies.py`** — `current_user` reads cookie → decodes via `cookies.verify` → calls `sessions.lookup` → bumps last_seen → returns the `User` or raises 401. `require_permission(name)` factory returns a dep that calls `current_user` then checks permission membership; 403 if missing.
- **`auth/router.py`** — FastAPI router registered at `/auth`. Thin: parses input, calls service functions.
- **`rbac/registry.py`** — `PermissionRegistry` singleton (module-level `registry`). `register(name, description, module="shell")`, `all()`, `async sync_to_db(session)`. Shell calls `register_shell_permissions()` at import-time so the registry is populated before lifespan starts.
- **`rbac/models.py`** — SQLAlchemy 2.0 declarative models against `shell_metadata`. One `DeclarativeBase` subclass (`ShellBase`) tied to shell metadata so autogenerate-driven migrations later see these tables.
- **`rbac/service.py`** — all business logic operating on `AsyncSession`: `create_user`, `authenticate`, `change_password`, `list_users`, `update_user`, `deactivate_user`, `create_role`, `list_roles`, `update_role`, `delete_role` (rejects builtin), `assign_permission_to_role`, `unassign_permission_from_role`, `assign_role_to_user`, `unassign_role_from_user`, `effective_permissions(user)`, `list_sessions(user_id)`, `revoke_all_user_sessions(user_id)`.
- **`rbac/router_admin.py`** — FastAPI router at `/admin`. Every route uses `require_permission(...)`. Thin: parse, call service, serialize.
- **`bootstrap.py`** — argparse-driven CLI with a `create-admin` subcommand. Validates password length, creates user, assigns the seeded admin role. Idempotency: refuses if email exists unless `--force`.

## Runtime behavior

### Lifespan additions

On `create_app` startup, after config + engine are wired:

1. `register_shell_permissions(registry)` — populates the in-memory registry.
2. After engine is attached to state: run `async with sessionmaker() as s: await registry.sync_to_db(s); await s.commit()`. Idempotent upsert: insert-if-missing by primary key `name`, update `description` and `module` on conflict.
3. Routers included: `auth.router`, `rbac.router_admin`.

### Cookie

- Name: `parcel_session`
- Value: `<session_uuid>.<HMAC-SHA256 of session_uuid, hex-lowercase>`
- `HttpOnly=true`, `SameSite=Lax`, `Path=/`
- `Secure=true` when `settings.env in ("staging", "prod")`; `false` in `dev`.
- Cookie `Max-Age` mirrors `sessions.expires_at - now()` when issued. Server also stamps a response `Set-Cookie` on logout with `Max-Age=0` to clear.

### Session TTLs

- **Absolute:** 7 days from `created_at`. After that, lookup returns `None` regardless of `last_seen_at`.
- **Idle:** 24 hours from `last_seen_at`. After that, lookup returns `None` and the session is marked revoked (`revoked_at = now()`).
- Each successful `current_user` lookup updates `last_seen_at`.

### Password rules

- Plaintext min length 12. Validated on create, update, and bootstrap.
- Argon2id library defaults on initial hash.
- After a successful verify, `needs_rehash(hash)` is checked; if true, the hash is replaced in the same request with a fresh one and committed.

### Failed-login logging

On any 401 from `/auth/login`:

```python
log.warning(
    "auth.login_failed",
    email=payload.email,          # echoed as-is; lowercased before lookup
    reason="no_user" | "bad_password" | "inactive",
    request_id=<contextvar>,
)
```

No rate limiting beyond this.

## Data model

All tables in the `shell` schema (extending Phase 1's empty baseline).

### `shell.users`

| column | type | notes |
|---|---|---|
| `id` | `uuid` PK | generated server-side (`uuid4`) |
| `email` | `text` NOT NULL UNIQUE | always stored lowercased |
| `password_hash` | `text` NOT NULL | Argon2id string |
| `is_active` | `boolean` NOT NULL DEFAULT `true` | |
| `created_at` | `timestamptz` NOT NULL DEFAULT `now()` | |
| `updated_at` | `timestamptz` NOT NULL DEFAULT `now()` | trigger not needed — bumped in service |

### `shell.sessions`

| column | type | notes |
|---|---|---|
| `id` | `uuid` PK | generated server-side |
| `user_id` | `uuid` NOT NULL | FK → `users(id)` ON DELETE CASCADE |
| `created_at` | `timestamptz` NOT NULL DEFAULT `now()` | |
| `last_seen_at` | `timestamptz` NOT NULL DEFAULT `now()` | |
| `expires_at` | `timestamptz` NOT NULL | `created_at + 7 days` |
| `revoked_at` | `timestamptz` | nullable |
| `ip_address` | `inet` | nullable |
| `user_agent` | `text` | nullable, truncated to 500 chars |

Index on `user_id` (for listing) and on `(expires_at)` (for future cleanup job).

### `shell.permissions`

| column | type | notes |
|---|---|---|
| `name` | `text` PK | e.g. `"users.write"` |
| `description` | `text` NOT NULL | |
| `module` | `text` NOT NULL DEFAULT `'shell'` | for Phase 3 module attribution |

### `shell.roles`

| column | type | notes |
|---|---|---|
| `id` | `uuid` PK | |
| `name` | `text` NOT NULL UNIQUE | |
| `description` | `text` | nullable |
| `is_builtin` | `boolean` NOT NULL DEFAULT `false` | |

### `shell.user_roles` (association)

| column | type | notes |
|---|---|---|
| `user_id` | `uuid` | FK → `users(id)` ON DELETE CASCADE |
| `role_id` | `uuid` | FK → `roles(id)` ON DELETE CASCADE |
| **PK** | `(user_id, role_id)` | |

### `shell.role_permissions` (association)

| column | type | notes |
|---|---|---|
| `role_id` | `uuid` | FK → `roles(id)` ON DELETE CASCADE |
| `permission_name` | `text` | FK → `permissions(name)` ON DELETE CASCADE |
| **PK** | `(role_id, permission_name)` | |

### Migration: `0002_auth_rbac`

Creates all six tables above. Seeds:

- The shell permissions (see "Shell-owned permissions" below) into `permissions`.
- An `admin` role with `is_builtin=true` and every shell permission attached.

`downgrade()` drops all six tables (`CASCADE` on the association tables is handled by the FK).

## Shell-owned permissions (Phase 2)

Registered in `register_shell_permissions()` and seeded by the migration:

| name | description |
|---|---|
| `users.read` | List and view user accounts |
| `users.write` | Create, update, and deactivate user accounts |
| `roles.read` | List and view roles |
| `roles.write` | Create, update, and delete roles; assign permissions to roles |
| `users.roles.assign` | Assign and unassign roles on users |
| `sessions.read` | List another user's sessions |
| `sessions.revoke` | Revoke another user's sessions |
| `permissions.read` | List registered permissions |

The `admin` role holds all eight.

## API endpoints

All responses JSON. All request bodies JSON. All auth failures 401; permission failures 403. Validation errors return FastAPI's default 422.

### `/auth` (public or self)

| Method | Path | Body | Auth | Returns |
|---|---|---|---|---|
| POST | `/auth/login` | `{email, password}` | public | 200 `{user, roles, permissions}` + Set-Cookie; 401 on bad creds or inactive user |
| POST | `/auth/logout` | — | session cookie | 204 + clear cookie. 204 even if no cookie (idempotent). |
| GET | `/auth/me` | — | session cookie | 200 `{user, roles, permissions}`; 401 if unauthenticated |
| POST | `/auth/change-password` | `{current_password, new_password}` | session cookie | 204; 400 if `current_password` wrong; 422 if new < 12 chars |

### `/admin` (all require a permission)

| Method | Path | Permission | Notes |
|---|---|---|---|
| GET | `/admin/users` | `users.read` | Paginated list (offset/limit, default 50, max 200) |
| POST | `/admin/users` | `users.write` | Body: `{email, password, role_ids: [uuid]}` |
| GET | `/admin/users/{id}` | `users.read` | |
| PATCH | `/admin/users/{id}` | `users.write` | Body may include `email`, `is_active` |
| DELETE | `/admin/users/{id}` | `users.write` | Soft delete: sets `is_active=false`, revokes all sessions |
| POST | `/admin/users/{id}/roles` | `users.roles.assign` | Body: `{role_id}`. Idempotent. |
| DELETE | `/admin/users/{id}/roles/{role_id}` | `users.roles.assign` | Idempotent (204 even if not assigned). |
| GET | `/admin/roles` | `roles.read` | |
| POST | `/admin/roles` | `roles.write` | Body: `{name, description}` |
| GET | `/admin/roles/{id}` | `roles.read` | |
| PATCH | `/admin/roles/{id}` | `roles.write` | Body may include `name`, `description`. 403 if `is_builtin`. |
| DELETE | `/admin/roles/{id}` | `roles.write` | 403 if `is_builtin`. |
| POST | `/admin/roles/{id}/permissions` | `roles.write` | Body: `{permission_name}`. 404 if permission name isn't registered. |
| DELETE | `/admin/roles/{id}/permissions/{permission_name}` | `roles.write` | Idempotent. |
| GET | `/admin/permissions` | `permissions.read` | Returns the DB-synced permissions list. |
| GET | `/admin/users/{id}/sessions` | `sessions.read` | Lists non-expired, non-revoked sessions. |
| POST | `/admin/users/{id}/sessions/revoke` | `sessions.revoke` | Revokes **all** sessions for that user. Body optional. |

### Response shapes

```python
# GET /auth/me, POST /auth/login
{
  "user": {"id": "uuid", "email": "str", "is_active": true, "created_at": "iso8601"},
  "roles": [{"id": "uuid", "name": "str"}],
  "permissions": ["users.read", ...]
}

# GET /admin/users/{id}
{
  "id": "uuid",
  "email": "str",
  "is_active": true,
  "created_at": "iso8601",
  "updated_at": "iso8601",
  "roles": [{"id": "uuid", "name": "str"}]
}

# GET /admin/users
{"items": [UserSummary], "total": 42, "offset": 0, "limit": 50}

# GET /admin/roles/{id}
{
  "id": "uuid",
  "name": "str",
  "description": "str | null",
  "is_builtin": false,
  "permissions": ["users.read", ...]
}
```

## FastAPI dependencies

```python
# parcel_shell/auth/dependencies.py

async def current_session(request: Request, db: AsyncSession = Depends(get_session)) -> Session: ...
async def current_user(session: Session = Depends(current_session), db: AsyncSession = Depends(get_session)) -> User: ...

def require_permission(name: str) -> Callable[..., Awaitable[User]]:
    async def dep(
        user: User = Depends(current_user),
        db: AsyncSession = Depends(get_session),
    ) -> User:
        perms = await service.effective_permissions(db, user.id)
        if name not in perms:
            raise HTTPException(403, "permission_denied")
        return user
    return dep
```

`effective_permissions` is one query: join `user_roles → role_permissions`.

## Testing strategy

### New fixtures in `conftest.py`

- `migrated_engine` (session-scoped) — `engine` after `alembic upgrade head`. Avoids per-test migration cost.
- `db_session` (function-scoped) — connection + nested savepoint + rollback. Each test sees a clean DB.
- `settings` (function-scoped) — like Phase 1's test_app_factory.
- `app` (function-scoped) — `create_app(settings)` with its DB state overridden via `dependency_overrides[get_session]` to the `db_session` fixture.
- `client` (function-scoped) — `AsyncClient(ASGITransport(app=app, raise_app_exceptions=False))`. Lifespan is managed via `asgi_lifespan.LifespanManager` around it.
- `user_factory(email="u@x.com", password="x"*12, roles=(), active=True)` — creates a user via service calls and returns it.
- `role_factory(name="editor", permissions=())` — creates a role and attaches given permissions.
- `admin_user` — user fixture holding the builtin `admin` role.
- `authed_client(user)` — calls `/auth/login` once and returns the `AsyncClient` with the cookie jar primed.

### Test inventory

1. **test_hashing.py**
   - Hash + verify roundtrip.
   - Verify rejects wrong password.
   - `needs_rehash` returns False on freshly-hashed value, True when library defaults change (monkeypatch `PasswordHasher.check_needs_rehash` to simulate).

2. **test_cookies.py**
   - Sign → verify returns the same session id.
   - Tampered payload → verify returns None.
   - Malformed value → verify returns None.
   - Wrong secret → verify returns None.

3. **test_sessions.py**
   - `create_session` inserts a row with correct TTL fields.
   - `lookup` returns the session, or None if not found / revoked / expired (absolute) / idle-expired.
   - `bump` advances `last_seen_at`.
   - `revoke` sets `revoked_at` and makes lookup return None.
   - `revoke_all_for_user` affects only that user.

4. **test_registry.py**
   - `register` adds; duplicate same name + description is a no-op; different description raises.
   - `sync_to_db` upserts; re-run is a no-op.

5. **test_rbac_service.py**
   - `create_user` lowercases email, hashes password.
   - `authenticate` success + bad password + inactive user.
   - `change_password` success + wrong current.
   - Role CRUD happy path; `delete_role` on `is_builtin=true` raises.
   - Permission assignment + unassignment; double-assign is no-op.
   - `effective_permissions` returns the union from all assigned roles.

6. **test_auth_router.py**
   - POST /auth/login success → 200 + cookie, body has user+roles+permissions.
   - POST /auth/login bad password → 401; log record captured with `auth.login_failed reason=bad_password`.
   - POST /auth/login inactive user → 401; log record with `reason=inactive`.
   - POST /auth/login unknown email → 401; log record with `reason=no_user`.
   - GET /auth/me without cookie → 401; with valid cookie → 200.
   - POST /auth/logout → 204, subsequent /auth/me → 401.
   - POST /auth/change-password wrong current → 400; success → 204, old cookie still valid (policy: changing password does not auto-revoke sessions).

7. **test_admin_users_router.py**
   - GET /admin/users without session → 401.
   - GET /admin/users as user without `users.read` → 403.
   - Full CRUD happy path as admin.
   - DELETE deactivates + revokes sessions.
   - POST `/admin/users/{id}/roles` requires `users.roles.assign`, not just `users.write`.

8. **test_admin_roles_router.py**
   - CRUD happy path.
   - DELETE on builtin `admin` role → 403.
   - PATCH on builtin `admin` role → 403.
   - POST `/admin/roles/{id}/permissions` with unregistered name → 404.

9. **test_admin_sessions_router.py**
   - GET sessions lists only non-expired, non-revoked.
   - POST revoke revokes them all; a client with a pre-existing cookie then gets 401.

10. **test_bootstrap.py**
    - `create-admin --email x --password <12+>` creates user + assigns admin role.
    - Re-run without `--force` → exits non-zero with a clear message.
    - Re-run with `--force` → rehashes password, preserves role assignments.
    - Password too short → exits non-zero.

11. **test_auth_integration.py**
    - Full flow: bootstrap (via service call) → login → call an admin endpoint → logout → same admin endpoint → 401.

Target: ~45 tests total. All should complete within ~20s locally.

## Dependency additions

`packages/parcel-shell/pyproject.toml` `dependencies`:

- `argon2-cffi>=23.1`
- `itsdangerous>=2.2` — signed-cookie HMAC helper. (Alternative: write HMAC by hand; not worth it.)

No workspace-root additions.

## Definition of done

1. `docker compose run --rm shell migrate` runs the new migration cleanly; `shell.users`, `shell.sessions`, `shell.roles`, `shell.permissions`, `shell.user_roles`, `shell.role_permissions` exist.
2. `docker compose run --rm shell python -m parcel_shell.bootstrap create-admin --email me@x.com --password 'changeme-at-least-12'` succeeds and prints the new user id.
3. `curl -c /tmp/c -X POST -H 'content-type: application/json' -d '{"email":"me@x.com","password":"..."}' http://localhost:8000/auth/login` returns 200 and writes a cookie.
4. `curl -b /tmp/c http://localhost:8000/auth/me` returns the user with `admin` role and all shell permissions.
5. `curl -b /tmp/c http://localhost:8000/admin/users` returns 200; with cookies cleared returns 401.
6. Creating a non-admin user, logging in as them, and hitting `/admin/users` returns 403.
7. `uv run pytest` green, including all Phase 1 tests still passing.
8. `uv run ruff check` + `uv run pyright packages/parcel-shell` clean.
9. CLAUDE.md updated: Phase 2 row `✅ done`, Phase 3 row `⏭ next`; new deps noted in the Locked-in decisions table.

## Out of scope (deferred)

- HTML login form / admin UI — Phase 4.
- Module-driven permission registration (real `Module` object w/ `permissions=[...]` attribute discovery) — Phase 3.
- `parcel` CLI as an entry-point — Phase 6.
- Rate limiting / IP-based throttling / account lockout — deferred until we have real users.
- Password reset, email verification, 2FA — deferred.
- Hard-delete of users, audit logs, login history — deferred.
- OIDC, SAML, API keys — locked out per CLAUDE.md.
