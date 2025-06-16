import importlib
import inspect
from functools import wraps
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type, Union

from fastapi import FastAPI, Request
from starlette.middleware import Middleware as StarletteMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import contextvars

MiddlewareRef = Union[
    str,  # nom ou chemin d'import
    Callable[[Request, Callable], Awaitable[Any]],  # fonction middleware
    Type[BaseHTTPMiddleware],  # classe middleware basée sur BaseHTTPMiddleware
    Type[Any],  # classe ASGI middleware (callable __call__)
]


NAMED_MIDDLEWARES_MODULE = "core.middleware_registry.NAMED_MIDDLEWARES"
MIDDLEWARE_STACK_MODULE = "core.middlewares.middlewares"

MIDDLEWARE_REGISTRY: Dict[str, MiddlewareRef] = {}

_internal_app: Optional[FastAPI] = None
_request_var = contextvars.ContextVar("request_var")


def _import_string(path: str) -> Any:
    """Importe un objet Python à partir d'un chemin string."""
    try:
        module_path, attr = path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, attr)
    except (ImportError, AttributeError, ValueError) as e:
        raise ImportError(f"Could not import '{path}': {e}") from e


def _is_asgi_middleware(cls: Any) -> bool:
    """Détecte si une classe est un middleware ASGI, autrement dit callable __call__ sans hériter de BaseHTTPMiddleware."""
    return (
        inspect.isclass(cls)
        and callable(getattr(cls, "__call__", None))
        and not issubclass(cls, BaseHTTPMiddleware)
    )


def _resolve_middleware(
    ref: MiddlewareRef,
) -> Union[Callable, Type[BaseHTTPMiddleware], Type[Any]]:
    """
    Résout un MiddlewareRef en un objet utilisable par starlette.middleware.Middleware.
    Retourne soit une classe middleware (BaseHTTPMiddleware ou ASGI), soit une fonction middleware.
    """

    cls_or_func: Union[Callable, Type[BaseHTTPMiddleware], Type[Any]] = ref
    if isinstance(ref, str):
        if ref in MIDDLEWARE_REGISTRY:
            cls_or_func = MIDDLEWARE_REGISTRY.get(ref)
        else:
            cls_or_func = _import_string(ref)

    if isinstance(cls_or_func, str):
        cls_or_func = _import_string(cls_or_func)

    if inspect.isfunction(cls_or_func):
        # transforme fonction en classe middleware
        class FuncMiddleware(BaseHTTPMiddleware):
            def __init__(self, app, **kwargs):
                super().__init__(app)
                self.kwargs = kwargs

            async def dispatch(self, request, call_next):
                return await cls_or_func(request, call_next, **self.kwargs)

        return FuncMiddleware
    elif inspect.isclass(cls_or_func):
        print(
            f"Resolving middleware: {cls_or_func.__name__} (type={type(cls_or_func)})"
        )
        if issubclass(cls_or_func, BaseHTTPMiddleware) or _is_asgi_middleware(
            cls_or_func
        ):
            return cls_or_func
        else:
            raise ValueError(
                "Middleware class must be BaseHTTPMiddleware subclass or ASGI middleware"
            )

    # Sinon erreur
    raise ValueError(f"MiddlewareRef invalide : {ref} (type={type(ref)})")


def register_named_middleware(name: str, ref: MiddlewareRef, *, override: bool = False):
    """Register a middleware class or import path under a name."""
    if name in MIDDLEWARE_REGISTRY and not override:
        raise ValueError(f"Middleware '{name}' already registered.")
    MIDDLEWARE_REGISTRY[name] = ref


def _get_awaitable_fn(fn) -> Awaitable[Any]:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if inspect.iscoroutinefunction(fn):
            return fn(*args, **kwargs)
        else:
            return fn(*args, **kwargs)

    return wrapper


def route_middleware(ref: MiddlewareRef, **kwargs: Any):
    """
    Decorator to apply a middleware to a specific route.
    The middleware can be a function or a subclass of BaseHTTPMiddleware or ASGI middleware.
    """
    global _internal_app
    cls = _resolve_middleware(ref)

    def decorator(route_handler: Callable):
        if not _internal_app:
            raise RuntimeError(
                "Middleware can only be applied after the FastAPI app is created."
            )

        awaitable_route_handler = _get_awaitable_fn(route_handler)
        mw_kwargs = kwargs.copy()

        @wraps(route_handler)
        async def wrapped_handler(*args, **route_kwargs):
            request = _request_var.get(None)

            if request is None:
                raise RuntimeError(
                    "Request context not found. Ensure RequestContextMiddleware is registered."
                )

            async def call_next(request: Request):
                return await awaitable_route_handler(*args, **route_kwargs)

            if issubclass(cls, BaseHTTPMiddleware):
                instance = cls(_internal_app, **mw_kwargs)
                return await instance.dispatch(request, call_next)
            elif _is_asgi_middleware(cls):
                raise ValueError(
                    "ASGI middleware cannot be applied directly to routes. Use BaseHTTPMiddleware instead."
                )
            else:
                raise ValueError(
                    "Middleware must be a subclass of BaseHTTPMiddleware or an ASGI middleware."
                )

        return wrapped_handler

    return decorator


def _is_middleware_registered(app: FastAPI, middleware_class):
    return any(middleware.cls == middleware_class for middleware in app.user_middleware)


def register_middlewares(app: FastAPI, group: Optional[str] = None):
    global _internal_app
    _internal_app = app
    stack: List["Middleware"] = _import_string(MIDDLEWARE_STACK_MODULE)

    if not _is_middleware_registered(app, RequestContextMiddleware):
        # Always register RequestContextMiddleware first
        app.add_middleware(RequestContextMiddleware)

    for middleware in stack:
        if isinstance(middleware, Middleware):
            if group is None or group in middleware.groups:
                app.add_middleware(
                    middleware.cls,
                    **middleware.kwargs,
                )
        elif isinstance(middleware, (str, Callable, type)):
            # Handle direct middleware references
            cls = _resolve_middleware(middleware)
            app.add_middleware(cls)
        else:
            raise ValueError(f"Invalid middleware type: {type(middleware)}")


class Middleware(StarletteMiddleware):
    def __init__(
        self,
        ref: MiddlewareRef,
        *,
        middleware_groups: Optional[List[str]] = None,
        middleware_name: Optional[str] = None,
        **kwargs: Any,
    ):
        cls = _resolve_middleware(ref)
        super().__init__(cls, **kwargs)
        self.groups = middleware_groups or []
        self.ref = ref
        
        if middleware_name:
            register_named_middleware(middleware_name, ref)

    def __repr__(self):
        return (
            f"<Middleware ref={self.ref} cls={self.cls.__name__} groups={self.groups}>"
        )


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        token = _request_var.set(request)
        try:
            response = await call_next(request)
        finally:
            _request_var.reset(token)
        return response


# Auto-load all named middlewares from registry
NAMED_MIDDLEWARES = _import_string(NAMED_MIDDLEWARES_MODULE)
for name, ref in NAMED_MIDDLEWARES.items():
    register_named_middleware(name, ref)
