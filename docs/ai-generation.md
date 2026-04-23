# AI Module Generation

**Status:** Design notes only. Implementation is Phase 7.

## Goal

An admin types a description ("I need to track customer complaints with status, assignee, and SLA") and Parcel produces a working, reviewable module.

## Pipeline

```
┌──────────────────┐
│  Admin prompt    │  (chat, free-form description)
└────────┬─────────┘
         ▼
┌──────────────────┐
│ LLM generation   │  Claude API — structured output:
│                  │   manifest · models · views · templates
│                  │   · Alembic migration · pytest tests
└────────┬─────────┘
         ▼
┌──────────────────┐
│ Static gate      │  ruff errors · bandit high · AST policy
│                  │  (reject imports of os, subprocess, socket,
│                  │   eval, exec, dynamic __import__ unless
│                  │   manifest declares the capability)
└────────┬─────────┘
         ▼
┌──────────────────┐
│ Sandbox install  │  Schema: mod_<name>_sandbox_<uuid>
│                  │  Seeded synthetic data
└────────┬─────────┘
         ▼
┌──────────────────┐
│ Run tests        │  Generated pytest suite; admin sees results
└────────┬─────────┘
         ▼
┌──────────────────┐
│ Admin preview    │  Clickthrough UI in sandbox
│                  │  See diffs, declared capabilities, test results
└────────┬─────────┘
         ▼
   Approve ─────────► Rename schema, register entry point, reload shell
   Reject  ─────────► Drop schema, discard package
```

## Safety principles

1. **Sandboxed install.** AI-generated code never touches production schemas before admin approval.
2. **Capability manifest.** Any dangerous import (network, subprocess, file I/O outside the module's own data dir) must be declared. Admin sees the list before approving.
3. **Deterministic gate first, probabilistic gate second.** Static analysis runs before the LLM self-review — untrusted code is judged on what it is, not on what it claims to be.
4. **Reversible.** Rejected modules leave zero trace. Approved modules can be uninstalled, dropping their schema (with a confirmation prompt).

## Open questions for Phase 7

- How do we handle partial module generations? (Admin asks to add a field to an existing module.)
- How aggressive should the AST policy be? First pass: strict deny-by-default; admin can allow specific imports with notes.
- Prompt library versioning — prompts that generate working modules are a core asset; version them under `packages/parcel-shell/src/parcel_shell/ai/prompts/`.
