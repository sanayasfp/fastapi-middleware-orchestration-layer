from fastapi import FastAPI, Request
from core.kernel import register_middlewares, route_middleware

app = FastAPI()

register_middlewares(app, group="api")

@app.get("/")
@route_middleware("simple_middleware", tag="🔥 HelloTag")
async def root():
    return {"message": "Basic route with functional middleware"}


@app.get("/header")
@route_middleware("debug_logger")
@route_middleware("with_header")
async def read_with_header(request: Request):
    return {"message": "Middleware reads custom header"}


@app.get("/class")
@route_middleware("custom_class", name="Ovarion")
async def with_class_middleware():
    print("This route uses a class-based middleware")
    return {"message": "Class-based middleware used"}


@app.post("/asgi")
@route_middleware("raw_asgi", label="📦 RawMode")
async def raw_asgi_middleware_test(whois: str = "Anonymous"):
    return {"message": "This route uses raw ASGI middleware", "whois": whois}

async def direct_middleware(request: Request, call_next):
    print(f"[Direct Middleware] Processing request for {request.url.path}")
    response = await call_next(request)
    print("[Direct Middleware] Response processed")
    return response

@app.post("/direct")
@route_middleware(direct_middleware)
async def direct_middleware_test():
    print("This route uses a direct middleware function")
    return {"message": "This route uses a direct middleware function"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
