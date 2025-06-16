from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


async def simple_middleware(
    request: Request, call_next: RequestResponseEndpoint, tag: str = "DEFAULT"
) -> Response:
    print(f"[simple_middleware] Before request with tag={tag}")
    response = await call_next(request)
    print("[simple_middleware] After request")
    return response


async def middleware_with_header(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    token = request.headers.get("X-Custom-Token", "No-Token")
    print(f"[middleware_with_header] Token: {token}")
    response = await call_next(request)
    return response


class CustomClassMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, name="Anonymous"):
        super().__init__(app)
        self.name = name

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        print(f"[CustomClassMiddleware] Hello from {self.name}")
        response = await call_next(request)
        print(f"[CustomClassMiddleware] Bye from {self.name}")
        return response


class RawASGIMiddleware:
    def __init__(self, app, label="raw"):
        self.app = app
        self.label = label

    async def __call__(self, scope, receive, send):
        print(
            f"[RawASGIMiddleware] Request path: {scope['path']} - label: {self.label}"
        )
        await self.app(scope, receive, send)
