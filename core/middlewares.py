from core.custom_middlewares import CustomClassMiddleware, simple_middleware
from core.kernel import Middleware


def debug_logger(request, call_next):
    print(f"[DEBUG] Request path: {request.url.path}")
    response = call_next(request)
    return response


middlewares = [
    Middleware(
        simple_middleware,
        tag="TestTag",
        middleware_groups=["api"],
        middleware_name="simple_middleware",
    ),
    Middleware(
        CustomClassMiddleware,
        name="Sana",
        # middleware_groups=["api"],
        middleware_name="custom_class",
    ),
    Middleware(
        "raw_asgi",
        label="LoggerRaw",
        middleware_groups=["api"],
    ),
    Middleware(
        debug_logger,
        middleware_groups=["debug", "api"],
        middleware_name="debug_logger",
    ),
]
