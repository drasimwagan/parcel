# parcel-shell

The Parcel shell: FastAPI app that hosts auth, RBAC, the admin UI, the module loader, and the AI authoring pipeline.

**Status:** Phase 0 skeleton. Implementation begins in Phase 1.

This package does not depend on any specific module. It discovers modules at runtime via the `parcel.modules` entry-point group.
