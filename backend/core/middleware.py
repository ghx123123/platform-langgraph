import json
import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


logger = logging.getLogger("multi_agent_platform.http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        response.headers["x-content-type-options"] = "nosniff"
        # Document previews are embedded by the same-origin teacher workspace.
        response.headers["x-frame-options"] = "SAMEORIGIN"
        response.headers["content-security-policy"] = "frame-ancestors 'self'"
        response.headers["referrer-policy"] = "same-origin"
        logger.info(
            json.dumps(
                {
                    "event": "request.completed",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
                ensure_ascii=True,
            )
        )
        return response
