from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from core.custom_middlewares import middleware_with_header

# Map des middlewares : noms lisibles → chemins importables ou classes directes
NAMED_MIDDLEWARES = {
    "cors": CORSMiddleware,
    "trusted_host": TrustedHostMiddleware,
    "gzip": GZipMiddleware,
    "raw_asgi": "core.custom_middlewares.RawASGIMiddleware",
    "with_header": middleware_with_header,
}
