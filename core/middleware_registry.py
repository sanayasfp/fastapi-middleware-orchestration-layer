from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.gzip import GZipMiddleware

# Map middleware "name" to import path or class
NAMED_MIDDLEWARES = {
    "cors": CORSMiddleware,
    "trusted_host": TrustedHostMiddleware,
    "gzip": GZipMiddleware,
    # You can also use import paths as strings:
    "custom_middleware": "core.custom_middlewares.custom_middleware",
    "simple-logger": "core.custom_middlewares.SimpleLogger",
}
