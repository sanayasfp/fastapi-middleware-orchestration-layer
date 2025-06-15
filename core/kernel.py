import importlib
import inspect
from functools import lru_cache, wraps
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type, Union

from fastapi import Depends, FastAPI, HTTPException, Request
from starlette.middleware import Middleware as StarletteMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from core.middleware_registry import NAMED_MIDDLEWARES

MiddlewareType = Union[
    Callable[[Request], Awaitable[None]],
    Type[BaseHTTPMiddleware],
]

MIDDLEWARE_REGISTRY: Dict[str, Union[str, Type[BaseHTTPMiddleware]]] = {}


@lru_cache(maxsize=128)
def _import_string(path: str) -> Type[BaseHTTPMiddleware]:
    """Import a class or function from a string path."""
    module_path, class_name = path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _get_middleware_fn_or_cls(
    ref: Union[str, Type[BaseHTTPMiddleware]],
) -> Type[BaseHTTPMiddleware]:
    """Resolve a middleware reference, which can be a string path or a class."""
    if isinstance(ref, str):
        return _import_string(ref)
    return ref


class DummyApp:
    """A dummy ASGI app for instantiating middleware classes."""

    async def __call__(self, scope, receive, send):
        pass


def _instantiate_middleware_class(middleware_cls: Type[BaseHTTPMiddleware]) -> Callable:
    """Instantiate a middleware class and return a callable for use in FastAPI."""

    async def middleware_callable(request: Request):
        instance = middleware_cls(app=DummyApp())

        async def dummy_next(_: Request):
            return None

        response = await instance.dispatch(request, dummy_next)
        if response is not None:
            raise HTTPException(
                status_code=response.status_code,
                detail="Request blocked by middleware.",
            )

    return middleware_callable


async def _call_middleware(
    middleware: Callable,
    request: Request,
    call_next: Optional[RequestResponseEndpoint] = None,
):
    """Call a middleware function or class, handling both sync and async cases."""
    if inspect.iscoroutinefunction(middleware):
        return (
            await middleware(request, call_next)
            if call_next
            else await middleware(request)
        )
    else:
        return middleware(request, call_next) if call_next else middleware(request)


def _create_cls_middleware(dispatch_fn: Callable) -> Type[BaseHTTPMiddleware]:
    """Create a middleware class that uses the provided dispatch function."""

    class DummyMiddleware(BaseHTTPMiddleware):
        def __init__(self, app):
            super().__init__(app)

        async def dispatch(self, request: Request, call_next: Callable) -> Any:
            return await dispatch_fn(request, call_next)

    return DummyMiddleware


def _create_dispatch_fn(fn: Callable) -> Callable:
    """Create a dispatch function that wraps the provided middleware function."""
    sig = inspect.signature(fn)
    expects_call_next = "call_next" in sig.parameters

    async def dispatch_fn(request: Request, call_next: Callable):
        result = await _call_middleware(
            fn, request, call_next if expects_call_next else None
        )
        if result is None and expects_call_next:
            return await call_next(request)
        return result or await call_next(request)

    return dispatch_fn


def _is_asgi_middleware(cls: Any) -> bool:
    """Check if a class is an ASGI middleware class."""
    return (
        inspect.isclass(cls)
        and callable(getattr(cls, "__call__", None))
        and not issubclass(cls, BaseHTTPMiddleware)
    )


def use_middleware_dependency(middleware: MiddlewareType):
    """
    Create a FastAPI dependency that applies middleware to a request.
    This is useful for applying middleware logic in route handlers."""
    if isinstance(middleware, type) and issubclass(middleware, BaseHTTPMiddleware):
        middleware = _instantiate_middleware_class(middleware)

    async def dependency(request: Request):
        await _call_middleware(middleware, request)

    return Depends(dependency)


def route_middleware(middleware: MiddlewareType):
    """
    Decorator to apply middleware to a specific route handler.
    This allows middleware to be applied directly to route functions.
    """
    if isinstance(middleware, type) and issubclass(middleware, BaseHTTPMiddleware):
        middleware = _instantiate_middleware_class(middleware)

    def decorator(handler: Callable[..., Awaitable[Any]]):
        @wraps(handler)
        async def wrapper(*args, request: Request, **kwargs):
            await _call_middleware(middleware, request)
            return await handler(*args, request=request, **kwargs)

        return wrapper

    return decorator


def register_named_middleware(
    name: str, cls_or_path: Union[str, Type[BaseHTTPMiddleware]]
):
    """Register a middleware class or import path under a name."""
    MIDDLEWARE_REGISTRY[name] = cls_or_path


def register_middlewares(app: FastAPI, group: Optional[str] = None):
    """
    Register all middlewares defined in the core.middlewares module to the FastAPI app.
    Optionally filter by group if specified.
    """
    from core.middlewares import middlewares

    for middleware in middlewares:
        if group and group not in getattr(middleware, "groups", []):
            continue
        app.add_middleware(middleware.cls, *middleware.args, **middleware.kwargs)


class Middleware(StarletteMiddleware):
    """
    A wrapper class for middleware that can be instantiated with a function, class, or string name.
    This class allows for flexible middleware registration and can be used with FastAPI or Starlette.
    It supports both function-based and class-based middlewares, as well as named middlewares
    registered in the MIDDLEWARE_REGISTRY.
    """

    def __init__(
        self,
        fn_or_cls_or_str_or_name: Union[str, Type[BaseHTTPMiddleware], Callable],
        middleware_groups: Optional[List[str]] = None,
        *args,
        **kwargs: Any,
    ):
        fn_or_cls_or_str = fn_or_cls_or_str_or_name

        if (
            isinstance(fn_or_cls_or_str, str)
            and fn_or_cls_or_str in MIDDLEWARE_REGISTRY
        ):
            fn_or_cls_or_str = MIDDLEWARE_REGISTRY[fn_or_cls_or_str]

        fn_or_cls = _get_middleware_fn_or_cls(fn_or_cls_or_str)
        name = getattr(fn_or_cls, "__name__", None)

        if inspect.isfunction(fn_or_cls):
            dispatch_fn = _create_dispatch_fn(fn_or_cls)
            self.cls = _create_cls_middleware(dispatch_fn)

        elif inspect.isclass(fn_or_cls):
            if issubclass(fn_or_cls, BaseHTTPMiddleware):
                self.cls = fn_or_cls
            elif _is_asgi_middleware(fn_or_cls):
                self.cls = fn_or_cls
            else:
                raise ValueError(f"Invalid middleware class type: {fn_or_cls}")
        else:
            raise ValueError(
                f"Invalid middleware type: {type(fn_or_cls)}. "
                "Must be a function, class, or registered name."
            )

        super().__init__(self.cls, *args, **kwargs)

        self.groups = middleware_groups or []

        if not name:
            import uuid

            name = f"DummyMiddleware-{uuid.uuid4()}"
        self.name = name


# Auto-load all named middlewares from registry
for name, ref in NAMED_MIDDLEWARES.items():
    register_named_middleware(name, ref)
