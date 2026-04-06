from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
from pathlib import Path

from config import settings
from routers import api
from routers.workflow import routes as workflow_routes
from routers.schema import routes as schema_routes
from routers.createImage import routes as createImage_routes
from routers.models import routes as models_routes
from routers.evaluate import routes as evaluate_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时
    print(f"Starting {settings.app_name} v{settings.app_version}")
    yield
    # 关闭时
    print("Shutting down...")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(api.router, prefix="/api/v1")
app.include_router(workflow_routes.router, prefix="/api/v1/data/workflow")
app.include_router(schema_routes.router, prefix="/api/v1/data/schema")
app.include_router(createImage_routes.router, prefix="/api/v1/createImage")
app.include_router(models_routes.router, prefix="/api/v1/models")
app.include_router(evaluate_routes.router, prefix="/api/v1/evaluate")

# 挂载静态文件
frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.exists():
    @app.get("/static/{path:path}")
    async def serve_static(path: str):
        from fastapi.responses import FileResponse
        file_path = frontend_dir / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return {"detail": "Not found"}

    @app.get("/")
    async def root():
        from fastapi.responses import FileResponse
        return FileResponse(frontend_dir / "index.html")
else:
    @app.get("/")
    async def root():
        return {"message": "Welcome to API", "version": settings.app_version}


@app.get("/health")
async def health():
    return {"status": "healthy"}
