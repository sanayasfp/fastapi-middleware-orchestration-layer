from fastapi import Request
from starlette.middleware.base import RequestResponseEndpoint, BaseHTTPMiddleware
from starlette.responses import Response


async def custom_middleware(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    print("Before request")
    response = await call_next(request)
    print("After request")
    return response


class CustomMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, with_args):
        super().__init__(app)
        self.app = app
        self.with_args = with_args

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        print("CustomMiddleware: Before request")
        print(f"CustomMiddleware: with_args={self.with_args}")
        response = await call_next(request)
        print("CustomMiddleware: After request")
        return response


class SimpleLogger:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        print("New request:", scope["path"])
        await self.app(scope, receive, send)
