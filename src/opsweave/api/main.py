"""FastAPI application entry point."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import health, retrieval, chat, config, knowledge


def create_app() -> FastAPI:
    app = FastAPI(
        title="OpsWeave API",
        version="0.1.0",
        description="Agentic RAG system for operations",
    )

    # CORS for Vue frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api/health", tags=["health"])
    app.include_router(retrieval.router, prefix="/api/retrieval", tags=["retrieval"])
    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "opsweave.api.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "false").lower() == "true",
    )
