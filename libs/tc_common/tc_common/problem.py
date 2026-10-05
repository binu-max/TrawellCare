import logging
from contextvars import ContextVar
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from tc_common.errors import AppError

logger = logging.getLogger("trawellcare")
correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")

_PROBLEM_SLUG = {
    400: "validation-failed",
    401: "unauthenticated",
    403: "forbidden",
    404: "not-found",
    409: "conflict",
    422: "rule-failed",
    500: "internal",
    502: "upstream-error",
    503: "upstream-unavailable",
}


def current_correlation_id() -> str:
    return correlation_id.get() or ""


def problem(
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    correlation: str,
) -> JSONResponse:
    slug = _PROBLEM_SLUG.get(status, "error")
    return JSONResponse(
        status_code=status,
        content={
            "type": f"https://trawellcare.com/problems/{slug}",
            "title": title,
            "status": status,
            "code": code,
            "correlationId": correlation,
            "detail": detail,
        },
    )


def install_problem_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        incoming = request.headers.get("x-correlation-id") or str(uuid4())
        token = correlation_id.set(incoming)
        request.state.correlation_id = incoming
        try:
            response = await call_next(request)
        finally:
            correlation_id.reset(token)
        response.headers["X-Correlation-Id"] = incoming
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return problem(
            status=exc.status,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            correlation=getattr(request.state, "correlation_id", ""),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        parts: list[str] = []
        for err in exc.errors():
            loc = ".".join(str(item) for item in err.get("loc", []) if item != "body")
            parts.append(f"{loc}: {err.get('msg')}" if loc else str(err.get("msg")))
        return problem(
            status=400,
            code="VALIDATION_FAILED",
            title="Validation failed",
            detail="; ".join(parts) or "Request validation failed",
            correlation=getattr(request.state, "correlation_id", ""),
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error")
        return problem(
            status=500,
            code="INTERNAL",
            title="Internal error",
            detail="Internal error",
            correlation=getattr(request.state, "correlation_id", ""),
        )
