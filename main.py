from fastapi import FastAPI
from core.kernel import register_middlewares

app = FastAPI()

register_middlewares(app)

@app.get("/")
async def read_root():
    print("Welcome to the FastAPI Middleware Kernel!")
    return {"message": "Welcome to the FastAPI Middleware Kernel!"}


# Replace with proper settings management
class Settings:
    def is_dev(self):
        return True
settings = Settings()

if __name__ == "__main__":
    import uvicorn

    if settings.is_dev():
        # Dev: reload enabled, debug logs, etc.
        uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
    else:
        # Prod: no reload, might change host/port if needed
        uvicorn.run("main:app", host="0.0.0.0", port=80)
