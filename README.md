# 🧠 FMOL - FastAPI Middleware Orchestration Layer

```plaintext
__/\\\\\\\\\\\\\\\__/\\\\____________/\\\\_______/\\\\\________/\\\_____________
 _\/\\\///////////__\/\\\\\\________/\\\\\\_____/\\\///\\\_____\/\\\_____________
  _\/\\\_____________\/\\\//\\\____/\\\//\\\___/\\\/__\///\\\___\/\\\_____________
   _\/\\\\\\\\\\\_____\/\\\\///\\\/\\\/_\/\\\__/\\\______\//\\\__\/\\\_____________
    _\/\\\///////______\/\\\__\///\\\/___\/\\\_\/\\\_______\/\\\__\/\\\_____________
     _\/\\\_____________\/\\\____\///_____\/\\\_\//\\\______/\\\___\/\\\_____________
      _\/\\\_____________\/\\\_____________\/\\\__\///\\\__/\\\_____\/\\\_____________
       _\/\\\_____________\/\\\_____________\/\\\____\///\\\\\/______\/\\\\\\\\\\\\\\\_
        _\///______________\///______________\///_______\/////________\///////////////__
        FastAPI             Middleware             Orchestration       Layer

        (Generated with https://www.asciiart.eu/text-to-ascii-art#google_vignette)
        Font: Slant Relief
```

A powerful and extensible **middleware orchestration layer** for FastAPI. This kernel provides:

✅ Named middleware registration  
✅ Group-based middleware loading  
✅ Route-level middleware via decorators/dependencies  
✅ Middleware applied to entire `APIRouter` instances  
✅ Import-string resolution with caching  
✅ ASGI middleware support

---

## 📁 Project Structure

To use this system, structure your project like this:

```plaintext
.
├── main.py
├── core/
│   ├── kernel.py               # Middleware logic (this file)
│   ├── middlewares.py          # List of middleware to register
│   ├── middleware_registry.py  # Map of named middlewares
```

This structure is recommended for clarity and a Laravel-like organization, but you can adapt it to your needs—as long as everything remains functional.

---

## ⚙️ 1. Global Middleware Registration

In `core/middlewares.py`, define your middleware:

```python
from core.kernel import Middleware
from starlette.middleware.cors import CORSMiddleware

middlewares = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        middleware_groups=["api"]
    ),
    Middleware("my-logging-middleware", middleware_groups=["api"]),
]
```

In `core/middleware_registry.py`:

```python
NAMED_MIDDLEWARES = {
    "my-logging-middleware": "logging.middleware.LoggingMiddleware",
}
```

In `main.py`:

```python
from fastapi import FastAPI
from core.kernel import register_middlewares

app = FastAPI()
register_middlewares(app, group="api")
```

---

## 🔗 2. Route-Specific Middleware

Use the `@route_middleware` decorator:

```python
from core.kernel import route_middleware
from accountability.middleware import AccountabilityMiddleware

@router.get("/secure")
@route_middleware(AccountabilityMiddleware)
async def secure_data():
    return {"status": "ok"}
```

Or as a dependency:

```python
from core.kernel import use_middleware_dependency

@router.get("/secure", dependencies=[use_middleware_dependency(AccountabilityMiddleware)])
async def secure_data():
    return {"status": "ok"}
```

---

## 🌀 3. Middleware for an Entire APIRouter

Use route dependencies or a helper:

```python
api_router = APIRouter(
    prefix="/api",
    dependencies=[use_middleware_dependency(AccountabilityMiddleware)]
)
```

Or create a helper to auto-wrap all routes in a router:

```python
def apply_router_middleware(router: APIRouter, middleware):
    from core.kernel import route_middleware
    for route in router.routes:
        route.endpoint = route_middleware(middleware)(route.endpoint)
```

---

## 🔌 4. ASGI Middleware Support

This system now supports **pure ASGI middleware**, i.e. classes that implement `__call__` without subclassing `BaseHTTPMiddleware`.

### ✅ Example

```python
# myapp/middleware.py
class SimpleLogger:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        print(f"[LOG] {scope['method']} {scope['path']}")
        await self.app(scope, receive, send)
```

Register it via import string or name:

```python
# core/middleware_registry.py
NAMED_MIDDLEWARES = {
    "simple-logger": "myapp.middleware.SimpleLogger"
}

# core/middlewares.py
middlewares = [
    Middleware("simple-logger", middleware_groups=["api"]),
]
```

✅ Works just like other middleware  
⛔ Cannot be used for per-route or dependency-based injection (ASGI spec limitation)

## 📦 Install & 🚀 Test

1. **Clone the repository**:

   ```bash
   git clone https://github.com/sanayasfp/fastapi-middleware-orchestration-layer.git
   cd fastapi-middleware-orchestration-layer
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Run the app**:

   ```bash
   uvicorn main:app --reload
   ```

4. **Call the root route**:

   Open your browser or use:

   ```bash
   curl http://localhost:8080/
   ```

5. **Expected console output**:

   When you hit `/`, you should see something like this in your terminal:

   ```plaintext
   CustomMiddleware: Before request
   CustomMiddleware: with_args=example_arg
   New request: /
   Before request
   Welcome to the FastAPI Middleware Kernel!
   After request
   CustomMiddleware: After request
   ```

   And in the response:

   ```json
   {
     "message": "Welcome to the FastAPI Middleware Kernel!"
   }
   ```

## 🚀 Performance Consideration

This system adds flexibility with **minimal runtime overhead**:

| Feature               | Cost                                          |
| --------------------- | --------------------------------------------- |
| Named middleware      | Only resolves on app boot                     |
| Import string caching | In-memory `_import_cache` avoids re-importing |
| Route decorators      | Minor runtime wrapping                        |
| Group filtering       | Simple list check during startup              |
| ASGI middleware       | Directly supported as-is                      |

**Recommendation:** Avoid excessive per-route decorators for high-throughput routes; prefer app-level or router-level where possible.

---

## 🔧 Middleware Internals (for Contributors)

- All middleware entries are wrapped in `core.kernel.Middleware`, a subclass of Starlette's `Middleware`
- Middleware can be referenced:
  - Directly (as a class or function)
  - Via import path (`"myapp.middleware.MyMiddleware"`)
  - By name (`"simple-logger"`) if registered in `NAMED_MIDDLEWARES`
- ASGI middleware classes are supported directly
- Registered via `register_named_middleware(name, cls_or_path)`

---

## 💬 Contribution Ideas

- [ ] Add support for middleware order priorities
- [ ] Integrate `APIRoute`-level true middleware logic (via subclassing)
- [ ] Create a CLI to scaffold new middlewares
- [ ] Build tooling to visualize middleware tree and active groups
- [ ] Better error handling for import failures
- [ ] Add tests for dynamic loading and group filtering
