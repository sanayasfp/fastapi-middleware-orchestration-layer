from core.kernel import Middleware
from core.custom_middlewares import CustomMiddleware

middlewares = [
    Middleware(
        "cors",
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        middleware_groups=["api"],
    ),
    Middleware("trusted_host", allowed_hosts=["*"], middleware_groups=["api"]),
    Middleware("gzip", minimum_size=1000, middleware_groups=["api"]),
    Middleware(
        "custom_middleware",
        # middleware_groups=["api"],
    ),
    Middleware(
        "simple-logger",
        middleware_groups=["api"],
    ),
    Middleware(CustomMiddleware, with_args="example_arg", middleware_groups=["api"]),
]
