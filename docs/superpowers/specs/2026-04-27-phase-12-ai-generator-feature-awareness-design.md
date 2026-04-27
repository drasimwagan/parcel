# Phase 12 — AI generator feature awareness (design)

## Goal

Teach the Claude-backed module generator the SDK surfaces it does not currently know about — dashboards (Phase 8), reports (Phase 9), workflows (Phase 10), and the optional `seed.py` (Phase 11) — so a single user prompt like "CRM with a contacts-by-stage dashboard and a weekly digest email" produces a module that actually uses those features instead of falling back to a Phase-5-style minimal CRUD scaffold.

## Pre-decided context (from `CLAUDE.md`)

- AI provider abstraction: `AnthropicAPIProvider` (default) and `ClaudeCodeCLIProvider`. Selected via `PARCEL_AI_PROVIDER`.
- Tool contract: `write_file(path, content)` repeatedly, then `submit_module()` exactly once. Per-file 64 KiB cap, 1 MiB total cap, 20-iteration tool-use budget. Path safety against absolute / traversal / executable extensions.
- One-shot auto-repair: on Phase-7a gate rejection the generator rebuilds a `PriorAttempt` with the report and retries exactly once. Failure enum: `provider_error` / `no_files` / `gate_rejected` / `exceeded_retries`.
- System prompt lives at `packages/parcel-shell/src/parcel_shell/ai/prompts/generate_module.md`, loaded via `importlib.resources` at provider construction time.
- AI chat is one prompt per turn; no model-context accumulation across turns. (See Phase 7c locked-in decision.)
- Phase 11 follow-up: "AI generator's system prompt does not yet emit `seed.py`." Phase 12 closes this.

## Architecture

### Component impact

Single file changes to `generate_module.md` (~350 → ~750 lines). Three new tests under `packages/parcel-shell/tests/`. No SDK changes, no shell-runtime changes, no provider changes, no migrations, no new dependencies, no new HTTP routes, no new ARQ jobs, no new templates outside the prompt's embedded reference.

```
packages/parcel-shell/
  src/parcel_shell/ai/prompts/generate_module.md  # rewritten
  tests/
    test_ai_prompt_shape.py                       # new — static prompt assertions
    test_ai_prompt_reference_module.py            # new — extract+gate the embedded reference
    test_ai_prompt_live_generation.py             # new — skipped by default, hits live API
```

### Why a single file, not modular loading

The system prompt is delivered with every generation request. A 750-line prompt is ~30 KiB — comfortably below the 64 KiB per-file cap and far below the model's context budget. Modular loading (analyse the user prompt → pick which sections to include) would require an extra AI pre-pass and adds a failure mode. Single big prompt is simpler, cheaper, and the model is already proven to ignore inapplicable sections of the existing prompt (e.g., it doesn't include `templates/` files when the user prompt doesn't mention UI).

### Generation flow stays unchanged

```
admin prompt
    ↓
AnthropicAPIProvider.generate(prompt)
    ├─ system = generate_module.md  ← rewritten in Phase 12
    └─ user = prompt
    ↓
tool-use loop: write_file × N → submit_module
    ↓
zip → create_sandbox  [Phase 7a]
    ↓ (on gate fail)
auto-repair: rebuild prior_attempt with report, retry once
    ↓
sandbox detail page  [Phase 11 previews kick in here]
```

The diagram is identical to the Phase 7b shipped flow. Phase 12 only changes the content of the system-prompt input.

## System prompt structure (rewritten)

The new prompt is divided into eight sections, in this order:

1. **Tool contract** — unchanged from current.
2. **Module layout** — extended with `seed.py`, `dashboards.py`, `reports.py`, `workflows.py` as optional files. The model is told to emit them based on the discipline rules in §6.
3. **Worked reference module — `support_tickets`** — see §5. Contains every feature the model is allowed to emit, in working form. The model pattern-matches against this for structure.
4. **Facade surface** — extended with `shell_api.emit(session, event, subject)` (the workflow event-bus seam, non-obvious from SDK signatures alone).
5. **Capability vocabulary** — unchanged values, but pinned to a stricter rule (§6).
6. **Feature menu (discipline rules)** — see §6. Tells the model when to add each feature.
7. **Hard rules / allowed imports / style / naming** — unchanged from current.
8. **Final instruction** — unchanged ("now read the user's prompt and emit `write_file` calls").

## Worked reference module — `support_tickets`

A complete module embedded inline in the prompt, demonstrating every feature the model is allowed to emit. Chosen because (a) it is a believable business domain every user has informal experience with, (b) it has obvious aggregations for dashboards, (c) it has natural workflow needs (notify on new ticket), (d) it has natural report needs (monthly volume), (e) it is structurally distinct from the existing Contacts module (no risk of the model just copying Contacts).

### Files shown

| File | Shown how |
|---|---|
| `pyproject.toml` | Full — exactly the standard manifest, identical to Phase 7b template. |
| `src/parcel_mod_support_tickets/__init__.py` | **Full**. The model must see how `dashboards=`, `reports=`, `workflows=`, `workflow_functions=` all sit on the `Module(...)` call together. This is the load-bearing file for pattern-matching. |
| `src/parcel_mod_support_tickets/models.py` | Full — `Ticket` and `Comment` (2 entities, FK relationship). |
| `src/parcel_mod_support_tickets/router.py` | Full — CRUD with `shell_api.emit(session, "ticket.created", ticket)` on the create endpoint. The explicit-emit pattern (Phase 10a locked-in decision) is non-obvious from SDK signatures alone, so it is shown. |
| `src/parcel_mod_support_tickets/seed.py` | Full — 8 sample tickets, 12 comments, mixed statuses/priorities/dates. |
| `src/parcel_mod_support_tickets/dashboards.py` | Full — 1 `KpiWidget` ("open tickets"), 1 `BarWidget` ("tickets by priority"), with their async data functions using `scalar_query` and `series_query`. |
| `src/parcel_mod_support_tickets/reports.py` | Full — 1 `Report` ("monthly volume") with a Pydantic `Params` model (month + year fields), an async `data` function returning a context dict, and a `template` reference. |
| `src/parcel_mod_support_tickets/workflows.py` | Full — 1 `Workflow` with `OnCreate` trigger + `SendEmail` action; capability `network` declared on the manifest. |
| `src/parcel_mod_support_tickets/templates/support_tickets/index.html` | Full — minimal Jinja extending `_base.html`. |
| `src/parcel_mod_support_tickets/templates/reports/monthly_volume.html` | Full — extends `reports/_report_base.html`. |
| `src/parcel_mod_support_tickets/alembic/...` | Standard layout, abbreviated to a `# unchanged from minimal-module template` comment. |
| `tests/test_smoke.py` | Full — asserts module identity AND `len(module.dashboards) == 2`, `len(module.workflows) == 1`, `len(module.reports) == 1`, `module.workflow_functions == {}`. |

The reference is intentionally small. Each file is the minimum that demonstrates one feature pattern. The model extrapolates: seeing `KpiWidget` and `BarWidget` it can produce `LineWidget` / `TableWidget` / `HeadlineWidget` from the SDK exports list; seeing `OnCreate + SendEmail` it can produce `OnUpdate + EmitAudit` or `Manual + UpdateField` from the SDK exports list.

### What is *not* in the reference

- `Module.preview_routes` — auto-walk handles 95% of modules and the override case is edge. Mentioned in the menu but not demonstrated.
- `OnSchedule` workflow trigger — mentioned in the menu but not demonstrated. The reference module's `OnCreate` is enough to teach the trigger pattern; `OnSchedule` differs only in field names (`hour`, `minute`, `weekday`).
- `RunModuleFunction` action and `Module.workflow_functions` — too niche for a worked example. The model knows the type from the SDK exports; the menu describes when to use it.
- `GenerateReport` action — relies on a report existing first. Same trade-off as `RunModuleFunction`.
- `CallWebhook` action — `SendEmail` already demonstrates the "action that needs `network`" pattern; `CallWebhook` is a parallel.

This trims the reference module by ~30%. The SDK exports list at the top of the prompt already enumerates every available type; the worked example shows the *patterns* the model needs to compose them.

## Feature menu (discipline rules)

```markdown
## Feature menu (decide per user prompt)

ALWAYS include:
- seed.py with 5–10 representative records, written using the module's own
  SQLAlchemy ORM via the AsyncSession argument. The seed runs against the
  sandbox schema before previews are taken; an empty schema produces empty
  preview screenshots, defeating the approval-gate UX.

INCLUDE BY DEFAULT (omit only if the data has no obvious aggregations):
- 1–2 dashboard widgets.
  KpiWidget for "how many active X". BarWidget for "X by category".
  LineWidget for "X over time". Use `scalar_query` / `series_query` /
  `table_query` from parcel_sdk — not raw `text(...)`.

ONLY IF THE USER ASKS:
- Workflows. Trigger words in the user's prompt: "when …", "on each …",
  "every Monday", "email me", "post to webhook", "schedule", "trigger",
  "automate", "notify", "alert".
- Reports. Trigger words: "report", "PDF", "export", "printable",
  "monthly summary", "audit document", "downloadable".

NEVER include unless the user explicitly specifies:
- Module.preview_routes — the auto-walk handles 95% of modules. Override
  only when the user describes routes that need custom path-param values
  the auto-walker cannot infer.

CAPABILITIES:
- Default: capabilities=()
- network: REQUIRED if and only if the module uses SendEmail or
  CallWebhook actions. Add it; do not silently drop the action.
- filesystem / process / raw_sql: NEVER add. If the user's prompt seems
  to require them, write the module *without* that specific feature and
  leave a TODO comment on the relevant line for the human reviewer.
  Do not refuse the prompt entirely.
```

### Why "ALWAYS seed.py"

Closes the open Phase 11 follow-up directly. Today AI-generated modules ship with empty schemas, so the Phase-11 screenshot pipeline produces blank pages and the approval gate loses its value for the AI flow specifically. Making `seed.py` mandatory in AI output is the highest-leverage Phase-12 change.

### Why "default include dashboards" but "only on request reports/workflows"

Dashboards are pure read paths with no side effects — over-inclusion costs the user nothing more than ignoring a tab. Reports involve a Pydantic params model, a Jinja template extending `_report_base.html`, and parameter-form UX — overkill if the user didn't ask. Workflows have *real* side effects (emails sent, scheduled jobs registered, audit rows written) — surprising the user with these is bad.

### Why TODO instead of refuse on `filesystem`/`process`/`raw_sql`

The AI generator has a one-shot retry on gate failure. If the model "refuses" by declining to emit code, the generation fails entirely and the user gets nothing actionable. If the model emits the module-minus-the-blocked-feature with a TODO comment, the human reviewer sees the gap immediately in the sandbox preview, can decide whether to hand-patch the module or rephrase the prompt. The sandbox-preview-gate UX assumes the human is the final authority — refusing breaks that loop.

## `shell_api` surface additions

The current prompt's facade-surface section lists six functions and one dataclass:

> `shell_api.get_session()`, `require_permission(name)`, `effective_permissions(request, user)`, `set_flash(response, flash)`, `get_templates()`, `sidebar_for(request, perms)`, `Flash(kind, msg)`.

Phase 12 adds:

> `shell_api.emit(session, event, subject, *, changed=())` — fire a workflow event from a router endpoint. Call after the row mutation, before the response is returned. The shell's `after_commit` listener picks events up post-commit and dispatches matching workflows. Without an `emit` call, an `OnCreate` / `OnUpdate` workflow declared on the same module will never fire.

This is the load-bearing line. The Phase-10a locked-in decision explicitly chose explicit emit over SQLAlchemy event listeners; without seeing this line in the system prompt, the model will write workflows that silently don't fire.

## Test surface

Three tests under `packages/parcel-shell/tests/`. All use the `importlib.resources` path that the live provider uses, so any drift between the file on disk and what the provider sees is caught.

### `test_ai_prompt_shape.py`

Static assertions on the prompt content. Cheap regression guard against a future edit accidentally dropping a section.

```python
def test_prompt_loads():
    text = (importlib.resources.files("parcel_shell.ai.prompts") /
            "generate_module.md").read_text()
    assert len(text) > 5000  # rough lower bound

def test_prompt_documents_each_feature():
    text = ...
    assert "Module.dashboards" in text
    assert "Module.workflows" in text
    assert "Module.reports" in text
    assert "seed.py" in text
    assert "shell_api.emit" in text

def test_prompt_capability_rule_pins_network_only():
    text = ...
    # The model must be told it can add network but never the others.
    assert "filesystem / process / raw_sql: NEVER add" in text
    assert "network: REQUIRED if" in text
```

### `test_ai_prompt_reference_module.py`

Extracts the embedded `support_tickets` reference module from the prompt to a tempdir and runs it through the existing Phase-7a static-analysis gate. Asserts no gate violations.

The extraction works by parsing fenced code blocks immediately after a `### \`<path>\`` heading. This pattern is already what the prompt uses; the test is a contract that the prompt's reference module continues to be a working module. As the gate evolves, the test will catch any drift.

```python
def test_reference_module_passes_gate(tmp_path):
    text = ...
    files = _extract_reference_files(text, marker="support_tickets")
    for path, content in files.items():
        (tmp_path / path).write_text(content)
    report = run_gate(tmp_path)
    assert report.violations == []
```

### `test_ai_prompt_live_generation.py`

Skipped by default (`@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), ...)`). Runs against the live provider with a known prompt and asserts shape on the output. Cost: real Anthropic-API tokens, ~30 s per run.

```python
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs live key")
async def test_generated_module_uses_dashboard_when_prompted():
    sandbox = await generate_module(
        "CRM for sales leads with a 'leads by stage' dashboard. "
        "Send me an email when a new lead is created.",
        provider=AnthropicAPIProvider(...),
        ...)
    files = _module_files(sandbox)
    assert "seed.py" in files                          # ALWAYS rule
    assert "dashboards" in files["__init__.py"]        # asked for it
    assert "workflows" in files["__init__.py"]         # asked for it
    assert "network" in files["__init__.py"]           # SendEmail → network
```

This test is the only one that exercises the actual model. It is documented as a "run before merge / never in CI" test.

## Failure modes

| Failure mode | Mitigation |
|---|---|
| Prompt grows past per-file cap (64 KiB) | The 750-line target is ~30 KiB. `test_ai_prompt_shape.py` does NOT assert an upper bound — that would create churn — but the live provider already validates inputs against the cap, so a future edit breaching it would surface as a 5xx on the next generation, not a silent regression. |
| Reference module drifts from the gate as the gate evolves | `test_ai_prompt_reference_module.py` runs the reference through the gate every test run. |
| Model adds `filesystem` capability anyway | The gate rejects `import os` / `open()` without the capability, but with the capability it allows them. The discipline rule is enforced by prompt only, not by code. Acceptable: the capability list is part of the sandbox detail page; an admin reviewing the candidate sees `capabilities=("filesystem",)` and can reject. **Phase X follow-up**: gate-time enforcement that AI-generated modules can never declare more than `network`. Out of scope here. |
| Model produces a module that doesn't seed cleanly | Phase 11's seed runner reports the seed error in the preview UI; the screenshot pipeline still tries to render against an empty schema. Documented; nothing to fix in Phase 12. |
| Model invents an SDK type that does not exist | Existing one-shot retry catches gate failures (likely surfaces as an unknown-import warning or runtime error). The reference module's pattern-matching reduces this risk substantially vs. describe-only prompts. |

## Locked-in decisions added by Phase 12

These get committed to `CLAUDE.md` in the same PR:

- **AI generator system prompt.** Includes a worked `support_tickets` reference module and a "Feature menu" discipline section. The generator does NOT do modular prompt loading (single ~750-line prompt loaded for every call).
- **AI feature defaults.** `seed.py` always emitted (5–10 records). Dashboards default-included when data has obvious aggregations. Reports and workflows only on explicit user request.
- **AI capability discipline.** `network` added if and only if `SendEmail` / `CallWebhook` is used. `filesystem` / `process` / `raw_sql` are never added by the AI generator — if the user's prompt seems to require them, the model emits a TODO comment instead of refusing.
- **AI prompt structure.** Embedded `support_tickets` reference module replaces describe-only API docs for dashboards / reports / workflows / seed.py. The model pattern-matches against the worked example rather than synthesising from formal types.

## What ships out of scope (deferred)

- **Phase 13 candidate (B): multi-turn refinement.** "Now add a workflow that emails me on new ticket" as a follow-up turn that knows about the previous draft. Requires accumulated Claude context across turns + a way for the model to read the current sandbox source.
- **Phase 14 candidate (C): mid-turn `ask_user`.** A new tool-call type that pauses generation, asks the user a clarifying question with options, resumes with the answer in context.
- **Static-gate enforcement of the AI capability rule.** Today the discipline rule is prompt-only. A small gate addition that bans `filesystem` / `process` / `raw_sql` capabilities on AI-generated sandbox installs would close the loop. Probably ride it in along with the next gate update.
- **Gate awareness of `seed.py`.** Phase 11 follow-up. Phase 12 makes `seed.py` ubiquitous, which moves this from "nice-to-have" to "noticeable when it bites."

## Test count delta

`~470 → ~473` (three new test files; the live-API test is skipped by default and does not contribute to the green count).

## CLAUDE.md updates

Locked-in decisions table grows by these rows:

- **AI generator system prompt** — embedded `support_tickets` reference module + "Feature menu" discipline section. Single ~750-line prompt; no modular loading.
- **AI feature defaults** — `seed.py` always emitted (5–10 records); dashboards default-on when data has obvious aggregations; reports + workflows only on explicit user request; `Module.preview_routes` never auto-included.
- **AI capability discipline** — `network` added iff `SendEmail` / `CallWebhook` is used; `filesystem` / `process` / `raw_sql` never added by AI generation.

The "Phase 12 — AI generator feature awareness" row in the roadmap flips to `✅ done`. The next row remains the Future row.
