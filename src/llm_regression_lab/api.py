import json
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID, uuid4

import asyncpg
from fastapi import Depends, FastAPI, Header, Path, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException

from .artifacts import FileArtifacts
from .database import check_schema, job_document, pool_for
from .errors import ProblemError
from .models import (
    Dataset,
    Digest,
    EvaluationConfig,
    Gate,
    Health,
    Job,
    JobRequest,
    Problem,
    Report,
    Version,
    VersionDocument,
)
from .service import JobService
from .settings import Settings

log = logging.getLogger(__name__)
bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")


def require(scope):
    async def dependency(
        request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
    ):
        identity = None
        if credentials:
            supplied = credentials.credentials.encode("utf-8")
            for token, candidate in request.app.state.settings.tokens.items():
                if secrets.compare_digest(supplied, token.encode("utf-8")):
                    identity = candidate
        if identity is None:
            raise ProblemError(401, "UNAUTHENTICATED", "A configured local bearer token is required.")
        if scope not in identity.scopes:
            raise ProblemError(403, "FORBIDDEN", "Token lacks the required scope.")
        return identity

    return dependency


def pairs_unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


class RequestBoundary:
    """Bound memory before framework parsing, reject ambiguous JSON, normalize errors."""

    def __init__(self, app, max_bytes):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        sent = False

        async def tracked_send(message):
            nonlocal sent
            if message["type"] == "http.response.start":
                sent = True
                headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() not in {b"x-request-id", b"cache-control"}
                ]
                message["headers"] = headers + [(b"x-request-id", request_id.encode()), (b"cache-control", b"no-store")]
            await send(message)

        try:
            data = bytearray()
            while True:
                event = await receive()
                if event["type"] == "http.disconnect":
                    return
                data.extend(event.get("body", b""))
                if len(data) > self.max_bytes:
                    raise ProblemError(413, "PAYLOAD_TOO_LARGE", "Request body exceeds 1 MiB.")
                if not event.get("more_body", False):
                    break
            if data:
                if scope["path"].endswith("/cancel"):
                    raise ProblemError(422, "VALIDATION_ERROR", "Cancellation takes no body.")
                content_type = dict(scope["headers"]).get(b"content-type", b"").split(b";")[0].strip().lower()
                if content_type != b"application/json":
                    raise ProblemError(422, "VALIDATION_ERROR", "Use application/json.")
                try:
                    parsed = json.loads(
                        data.decode("utf-8"),
                        object_pairs_hook=pairs_unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite number")),
                    )
                    # Escaped lone surrogates are not valid stored UTF-8 content.
                    json.dumps(parsed, ensure_ascii=False, allow_nan=False).encode("utf-8")
                except (ValueError, UnicodeError, RecursionError):
                    raise ProblemError(
                        400, "INVALID_JSON", "Malformed, duplicate-key or non-finite JSON is not accepted."
                    ) from None
            replayed = False

            async def replay():
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": bytes(data), "more_body": False}
                return await receive()

            await self.app(scope, replay, tracked_send)
        except Exception as error:
            if sent:
                raise
            if isinstance(error, ProblemError):
                problem = error
            elif isinstance(error, (asyncpg.PostgresError, OSError, TimeoutError)):
                problem = ProblemError(503, "DEPENDENCY_UNAVAILABLE", "A local dependency is unavailable.", True)
            else:
                log.error("Request failed: request_id=%s type=%s", request_id, type(error).__name__)
                problem = ProblemError(500, "INTERNAL_ERROR", "An internal error occurred.")
            await problem.response(request_id)(scope, receive, tracked_send)


def create_app(settings=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        pool = await pool_for(settings)
        try:
            async with pool.acquire() as db:
                if not await check_schema(db):
                    raise RuntimeError("Run python -m llm_regression_lab.database before starting the API")
            app.state.service = JobService(pool, FileArtifacts(settings.artifact_root))
            yield
        finally:
            await pool.close()

    app = FastAPI(
        separate_input_output_schemas=False,
        title="LLM Regression Lab — local fake-provider service",
        version="0.1.0",
        lifespan=lifespan,
        responses={
            "default": {
                "model": Problem,
                "description": "Problem envelope",
                "content": {"application/problem+json": {}},
            }
        },
    )
    app.state.settings = settings
    app.add_middleware(RequestBoundary, max_bytes=settings.max_body_bytes)

    @app.exception_handler(ProblemError)
    async def problem_handler(request, error):
        return error.response(request.state.request_id)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request, error):
        return ProblemError(422, "VALIDATION_ERROR", "Request fields do not match the contract.").response(
            request.state.request_id
        )

    @app.exception_handler(HTTPException)
    async def http_handler(request, error):
        code = "NOT_FOUND" if error.status_code == 404 else "VALIDATION_ERROR"
        return ProblemError(error.status_code, code, "Unsupported route or request.").response(request.state.request_id)

    def service(request: Request):
        return request.app.state.service

    Service = Annotated[JobService, Depends(service)]

    for kind, model, name in (("dataset", Dataset, "Dataset"), ("config", EvaluationConfig, "EvaluationConfig")):

        def register_routes(kind=kind, model=model, name=name):
            async def register(
                body: model, response: Response, svc: Service, identity=Depends(require("versions:write"))
            ):
                result, created = await svc.register(identity.project_id, kind, body.model_dump())
                response.status_code = 201 if created else 200
                response.headers["Location"] = f"/v1/{kind}-versions/{result['version_id']}"
                return result

            async def get_version(version_id: Digest, svc: Service, identity=Depends(require("versions:read"))):
                return await svc.version(identity.project_id, kind, version_id)

            app.post(
                f"/v1/{kind}-versions",
                response_model=Version,
                status_code=201,
                responses={200: {"model": Version}},
                operation_id=f"register{name}",
                openapi_extra={"x-required-scope": "versions:write"},
            )(register)
            app.get(
                f"/v1/{kind}-versions/{{version_id}}",
                response_model=VersionDocument,
                operation_id=f"get{name}",
                openapi_extra={"x-required-scope": "versions:read"},
            )(get_version)

        register_routes()

    @app.post(
        "/v1/jobs",
        response_model=Job,
        status_code=202,
        responses={200: {"model": Job}},
        operation_id="submitJob",
        openapi_extra={"x-required-scope": "jobs:write"},
    )
    async def submit(
        body: JobRequest,
        response: Response,
        svc: Service,
        idempotency_key: Annotated[str, Header(min_length=8, max_length=128, pattern=r"^[\x20-\x7e]+$")],
        identity=Depends(require("jobs:write")),
    ):
        result, created = await svc.submit(identity.project_id, idempotency_key, body.model_dump())
        response.status_code = 202 if created else 200
        response.headers["Location"] = result["links"]["self"]
        return result

    JobID = Annotated[UUID, Path()]

    @app.get(
        "/v1/jobs/{job_id}", response_model=Job, operation_id="getJob", openapi_extra={"x-required-scope": "jobs:read"}
    )
    async def get_job(job_id: JobID, svc: Service, identity=Depends(require("jobs:read"))):
        return job_document(await svc.row(identity.project_id, str(job_id)))

    @app.post(
        "/v1/jobs/{job_id}/cancel",
        response_model=Job,
        responses={202: {"model": Job}},
        operation_id="cancelJob",
        openapi_extra={"x-required-scope": "jobs:write"},
    )
    async def cancel(job_id: JobID, response: Response, svc: Service, identity=Depends(require("jobs:write"))):
        result, response.status_code = await svc.cancel(identity.project_id, str(job_id))
        response.headers["Location"] = result["links"]["self"]
        return result

    @app.get(
        "/v1/jobs/{job_id}/report",
        response_model=Report,
        operation_id="getReport",
        openapi_extra={"x-required-scope": "reports:read"},
    )
    async def report(job_id: JobID, response: Response, svc: Service, identity=Depends(require("reports:read"))):
        result = await svc.report(identity.project_id, str(job_id))
        response.headers["ETag"] = f'"{result["artifact_digest"]}"'
        return result

    @app.get(
        "/v1/jobs/{job_id}/gate",
        response_model=Gate,
        operation_id="getGate",
        openapi_extra={"x-required-scope": "reports:read"},
    )
    async def gate(job_id: JobID, svc: Service, identity=Depends(require("reports:read"))):
        return await svc.gate(identity.project_id, str(job_id))

    @app.get("/health/live", response_model=Health, operation_id="healthLive")
    async def live():
        return {"status": "ok"}

    @app.get("/health/ready", response_model=Health, responses={503: {"model": Health}}, operation_id="healthReady")
    async def ready(response: Response, svc: Service):
        try:
            async with svc.pool.acquire() as db:
                healthy = await check_schema(db)
        except (asyncpg.PostgresError, OSError, TimeoutError):
            healthy = False
        response.status_code = 200 if healthy else 503
        return {"status": "ok" if healthy else "unavailable"}

    generated_openapi = app.openapi

    def openapi():
        schema = generated_openapi()
        for operations in schema["paths"].values():
            for operation in operations.values():
                errors = operation["responses"]
                problem_content = {"application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}}
                errors["default"]["content"] = problem_content
                if "422" in errors:
                    errors["422"] = {"description": "Request validation failed", "content": problem_content}
        return schema

    app.openapi = openapi
    return app
