from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.routes.health import router as health_router
from app.api.routes.analysis import router as analysis_router
from app.api.routes.analysis_jobs import router as jobs_router


def create_application() -> FastAPI:
    """FastAPI Application Factory.

    Configures metadata, CORS middleware, and mounts modular routers.
    """
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="Autonomous Reasoning & Architecture for Decision Intelligence",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Configure CORS for local Next.js frontend communication
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routers
    # GET /health
    app.include_router(health_router)
    # POST /api/analyze
    app.include_router(analysis_router, prefix=settings.API_V1_STR)
    # POST /api/analysis/jobs, GET /api/analysis/jobs/{job_id}, GET /api/analysis/jobs/{job_id}/result
    app.include_router(jobs_router, prefix=settings.API_V1_STR)
    # Also support un-prefixed paths: POST /analysis/jobs, GET /analysis/jobs/{job_id}, etc.
    app.include_router(jobs_router)

    return app


app = create_application()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
