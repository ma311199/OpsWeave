# OpsWeave

OpsWeave is an agentic retrieval-augmented generation (RAG) service for operations teams. It combines a FastAPI backend, Vue frontend, Milvus vector storage, document review workflows, and an MCP-enabled LangGraph agent.

## Quick Start

Requirements: Python 3.11+, `uv`, Node.js, and npm. A running Milvus instance and OpenAI-compatible LLM/embedding services are needed for end-to-end use.

1. Configure `.env` with `LLM_API_KEY`, `EMBEDDING_API_KEY`, `MILVUS_URI`, `MILVUS_USER`, `MILVUS_PASSWORD`, and `ADMIN_INITIAL_PASSWORD`. Set `DATA_DIR` to a writable persistent directory. See `docs/deployment.md` for configuration details.
2. Install backend dependencies with `uv sync --dev`.
3. Install frontend dependencies from `frontend` with `npm install`.
4. Start both services using `start.bat` on Windows, or start them separately:

   ```powershell
   uv run python -m uvicorn opsweave.api.main:app --host 127.0.0.1 --port 8000
   npm --prefix frontend run dev -- --host 127.0.0.1
   ```

The frontend is available at `http://127.0.0.1:5173`; the API health endpoint is `http://127.0.0.1:8000/api/health/ping`.

## Development Checks

```powershell
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest tests/
npm --prefix frontend run build
```

## Documentation

- `docs/architecture.md`: system architecture and component boundaries
- `docs/api.md`: REST, WebSocket, and MCP interfaces
- `docs/development.md`: local development workflow
- `docs/deployment.md`: deployment configuration and security guidance
- `docs/roadmap.md`: implementation status and next stages
