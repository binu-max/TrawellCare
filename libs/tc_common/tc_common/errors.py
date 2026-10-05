class AppError(Exception):
    code = "INTERNAL"
    status = 500
    title = "Internal error"

    def __init__(self, detail: str | None = None, *, code: str | None = None, status: int | None = None):
        self.detail = detail or self.title
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status
        super().__init__(self.detail)


class ValidationFailed(AppError):
    code = "VALIDATION_FAILED"
    status = 400
    title = "Validation failed"


class Unauthenticated(AppError):
    code = "UNAUTHENTICATED"
    status = 401
    title = "Unauthenticated"


class Forbidden(AppError):
    code = "FORBIDDEN"
    status = 403
    title = "Forbidden"


class NotFound(AppError):
    code = "NOT_FOUND"
    status = 404
    title = "Not found"


class Conflict(AppError):
    code = "CONFLICT"
    status = 409
    title = "Conflict"


class RuleFailed(AppError):
    code = "RULE_FAILED"
    status = 422
    title = "Rule failed"


class UpstreamError(AppError):
    code = "UPSTREAM_ERROR"
    status = 502
    title = "Upstream error"


class UpstreamUnavailable(AppError):
    code = "UPSTREAM_UNAVAILABLE"
    status = 503
    title = "Upstream unavailable"
