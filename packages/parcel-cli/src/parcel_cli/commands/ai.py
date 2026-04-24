"""`parcel ai` subcommand group — Claude-backed module generator."""

from __future__ import annotations

import asyncio

import typer

from parcel_cli._shell import with_shell

app = typer.Typer(
    name="ai",
    help="Parcel AI — Claude-backed module generator.",
    no_args_is_help=True,
)


@app.command("generate")
def generate(
    prompt: str = typer.Argument(
        ..., help="Natural-language description of the module to generate."
    ),
) -> None:
    """Generate a module draft via the configured provider and sandbox it."""
    asyncio.run(_run(prompt))


async def _run(prompt: str) -> None:
    from parcel_shell.ai.generator import GenerationFailure, generate_module

    async with with_shell() as fast_app:
        provider = getattr(fast_app.state, "ai_provider", None)
        if provider is None:
            typer.echo(
                "error: AI provider not configured. Set ANTHROPIC_API_KEY "
                "or PARCEL_AI_PROVIDER=cli and ensure `claude` is on PATH.",
                err=True,
            )
            raise typer.Exit(2)
        sessionmaker = fast_app.state.sessionmaker
        settings = fast_app.state.settings
        async with sessionmaker() as db:
            result = await generate_module(
                prompt,
                provider=provider,
                db=db,
                app=fast_app,
                settings=settings,
            )
            await db.commit()

    if isinstance(result, GenerationFailure):
        typer.echo(f"✗ generation failed ({result.kind}): {result.message}", err=True)
        if result.gate_report is not None:
            errors = [f for f in result.gate_report["findings"] if f["severity"] == "error"]
            for f in errors[:10]:
                typer.echo(
                    f"  [{f['check']}] {f['path']}:{f['line']} " f"{f['rule']}: {f['message']}",
                    err=True,
                )
        raise typer.Exit(1)
    typer.echo(f"✓ sandbox {result.id} at {result.url_prefix}")
