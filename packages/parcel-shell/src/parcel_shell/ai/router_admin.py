from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from parcel_shell.ai.generator import GenerationFailure, generate_module
from parcel_shell.ai.schemas import GenerateFailure, GenerateRequest
from parcel_shell.auth.dependencies import require_permission
from parcel_shell.db import get_session
from parcel_shell.sandbox.schemas import SandboxOut

router = APIRouter(prefix="/admin/ai", tags=["admin", "ai"])


_KIND_TO_STATUS = {
    "provider_error": status.HTTP_502_BAD_GATEWAY,
    "no_files": status.HTTP_400_BAD_REQUEST,
    "gate_rejected": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "exceeded_retries": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


@router.post(
    "/generate",
    response_model=SandboxOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate(
    body: GenerateRequest,
    request: Request,
    _: object = Depends(require_permission("ai.generate")),
    db: AsyncSession = Depends(get_session),
) -> SandboxOut:
    provider = getattr(request.app.state, "ai_provider", None)
    if provider is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI provider not configured — set ANTHROPIC_API_KEY " "or PARCEL_AI_PROVIDER=cli",
        )
    result = await generate_module(
        body.prompt,
        provider=provider,
        db=db,
        app=request.app,
        settings=request.app.state.settings,
    )
    if isinstance(result, GenerationFailure):
        raise HTTPException(
            status_code=_KIND_TO_STATUS.get(result.kind, status.HTTP_502_BAD_GATEWAY),
            detail=GenerateFailure(
                kind=result.kind,
                message=result.message,
                gate_report=result.gate_report,
                transcript=result.transcript,
            ).model_dump(),
        )
    return SandboxOut.model_validate(result)
