import importlib
import inspect
from functools import wraps
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type, Union

from fastapi import FastAPI, Request
from starlette.middleware import Middleware as StarletteMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import contextvars

MiddlewareRef = Union[
    str,  # name or import path
    Callable[[Request, Callable], Awaitable[Any]],  # middleware function
    Type[BaseHTTPMiddleware],  # BaseHTTPMiddleware-based middleware class
    Type[Any],  # ASGI middleware class (with callable __call__)
]

# Constants defining module paths for named middlewares and middleware stack.
NAMED_MIDDLEWARES_MODULE = "core.middleware_registry.NAMED_MIDDLEWARES"
MIDDLEWARE_STACK_MODULE = "core.middlewares.middlewares"

# Global registry to store named middleware references.
MIDDLEWARE_REGISTRY: Dict[str, MiddlewareRef] = {}

# Global variable to hold the FastAPI application instance.
_internal_app: Optional[FastAPI] = None

# Context variable to store the current request object for access within middleware.
_request_var = contextvars.ContextVar("request_var")


def _import_string(path: str) -> Any:
    """
    Import a Python object from a dotted string path.

    Args:
        path: A string representing the import path (e.g., "module.submodule.Class").

    Returns:
        The imported object (class, function, or other callable).

    Raises:
        ImportError: If the path cannot be resolved or the object cannot be imported.
    """
    try:
        module_path, attr = path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, attr)
    except (ImportError, AttributeError, ValueError) as e:
        raise ImportError(f"Could not import '{path}': {e}") from e


def _is_asgi_middleware(cls: Any) -> bool:
    """
    Check if a class is an ASGI middleware (has a callable __call__ method
    and does not inherit from BaseHTTPMiddleware).

    Args:
        cls: The class to check.

    Returns:
        bool: True if the class is an ASGI middleware, False otherwise.
    """
    return (
        inspect.isclass(cls)
        and callable(getattr(cls, "__call__", None))
        and not issubclass(cls, BaseHTTPMiddleware)
    )


def _resolve_middleware(
    ref: MiddlewareRef,
) -> Union[Callable, Type[BaseHTTPMiddleware], Type[Any]]:
    """
    Resolve a MiddlewareRef into a usable middleware object for Starlette.

    This function converts a middleware reference (string, function, or class)
    into a form that can be used by Starlette's middleware system. Functions are
    wrapped in a BaseHTTPMiddleware subclass, while classes are validated as either
    BaseHTTPMiddleware or ASGI middleware.

    Args:
        ref: The middleware reference (string path, function, or class).

    Returns:
        A middleware class (BaseHTTPMiddleware or ASGI) or a wrapped function.

    Raises:
        ValueError: If the middleware reference is invalid or unsupported.
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
        # Wrap a middleware function in a BaseHTTPMiddleware subclass
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

    # Raise an error for invalid middleware references
    raise ValueError(f"MiddlewareRef invalide : {ref} (type={type(ref)})")


def register_named_middleware(name: str, ref: MiddlewareRef, *, override: bool = False):
    """
    Register a middleware class or import path under a given name in the registry.

    Args:
        name: The name to associate with the middleware.
        ref: The middleware reference (string path, function, or class).
        override: If True, allows overwriting an existing middleware with the same name.

    Raises:
        ValueError: If the name is already registered and override is False.
    """
    if name in MIDDLEWARE_REGISTRY and not override:
        raise ValueError(f"Middleware '{name}' already registered.")
    MIDDLEWARE_REGISTRY[name] = ref


def _get_awaitable_fn(fn) -> Awaitable[Any]:
    """
    Wrap a function to ensure it is awaitable, supporting both sync and async functions.

    Args:
        fn: The function to wrap.

    Returns:
        A wrapped function that is awaitable.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        if inspect.iscoroutinefunction(fn):
            return fn(*args, **kwargs)
        else:
            return fn(*args, **kwargs)

    return wrapper


def route_middleware(ref: MiddlewareRef, **kwargs: Any):
    """
    Decorator to apply a middleware to a specific FastAPI route.

    The middleware can be a function, a BaseHTTPMiddleware subclass, or an ASGI middleware.
    This decorator wraps the route handler to apply the middleware logic only to that route.

    Args:
        ref: The middleware reference (string path, function, or class).
        **kwargs: Additional keyword arguments to pass to the middleware.

    Returns:
        A decorator function that wraps the route handler.

    Raises:
        RuntimeError: If the FastAPI app is not initialized or RequestContextMiddleware is missing.
        ValueError: If the middleware is invalid or unsupported for route-level application.
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
    """
    Check if a middleware class is already registered in the FastAPI app.

    Args:
        app: The FastAPI application instance.
        middleware_class: The middleware class to check.

    Returns:
        bool: True if the middleware is registered, False otherwise.
    """
    return any(middleware.cls == middleware_class for middleware in app.user_middleware)


def register_middlewares(app: FastAPI, group: Optional[str] = None):
    """
    Register a stack of middlewares to a FastAPI application.

    This function loads a middleware stack from the MIDDLEWARE_STACK_MODULE and applies
    the middlewares to the FastAPI app. It ensures RequestContextMiddleware is always
    registered first and supports middleware groups for conditional registration.

    Args:
        app: The FastAPI application instance.
        group: Optional group name to filter middlewares (only those in the group are applied).

    Raises:
        ValueError: If an invalid middleware type is encountered.
    """
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
    """
    A wrapper class for Starlette middleware with additional group and naming support.

    This class extends Starlette's Middleware to support middleware groups and named
    registration. It resolves middleware references and allows associating middlewares
    with specific groups for conditional application.

    Attributes:
        groups: List of group names this middleware belongs to.
        ref: The original middleware reference (string, function, or class).
    """

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
    """
    Middleware to store the current request in a context variable.

    This middleware ensures that the current request is available in a context variable
    (_request_var) for use by other middlewares or route handlers. It sets the request
    at the start of processing and clears it afterward.

    Methods:
        dispatch: Handles storing and clearing the request context.
    """

    async def dispatch(self, request: Request, call_next):
        token = _request_var.set(request)
        try:
            response = await call_next(request)
        finally:
            _request_var.reset(token)
        return response


# Auto-load all named middlewares from the registry module
NAMED_MIDDLEWARES = _import_string(NAMED_MIDDLEWARES_MODULE)
for name, ref in NAMED_MIDDLEWARES.items():
    register_named_middleware(name, ref)
