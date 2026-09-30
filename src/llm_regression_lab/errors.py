from fastapi.responses import JSONResponse


class ProblemError(Exception):
    def __init__(self, status, code, detail, retryable=False):
        super().__init__(code)
        self.status, self.code, self.detail, self.retryable = status, code, detail, retryable

    def response(self, request_id):
        headers = {"X-Request-ID": request_id, "Cache-Control": "no-store"}
        if self.status == 401:
            headers["WWW-Authenticate"] = "Bearer"
        if self.retryable:
            headers["Retry-After"] = "5"
        return JSONResponse(
            status_code=self.status,
            media_type="application/problem+json",
            headers=headers,
            content={
                "type": f"urn:llm-regression-lab:error:{self.code}",
                "title": self.code.replace("_", " ").title(),
                "status": self.status,
                "code": self.code,
                "detail": self.detail,
                "request_id": request_id,
                "retryable": self.retryable,
            },
        )


class IntegrityError(Exception):
    """Stored bytes do not match their immutable identity."""


class ExecutionFailure(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code
