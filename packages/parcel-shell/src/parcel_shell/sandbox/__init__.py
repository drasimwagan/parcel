"""Parcel sandbox — gated installs at ``mod_sandbox_<uuid>`` schemas.

A candidate module is dropped into ``var/sandbox/<uuid>/``, run through the
static gate (:mod:`parcel_gate`), migrated into ``mod_sandbox_<uuid>``, and
mounted at ``/mod-sandbox/<uuid>``. Admins promote (copy files → real install)
or dismiss (drop schema + files).
"""
