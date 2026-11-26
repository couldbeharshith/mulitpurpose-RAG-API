# AGENTS.md

This file provides guidance to all AI Agents when working with code in this repository.

## Project

PlexRAG pairs a Next.js document workspace with a FastAPI service. The legacy batch endpoint accepts one document URL and answers multiple questions in a single request.

- `backend/` contains the FastAPI application, conversation storage, schemas, document processors, retrieval services and model clients.
- `frontend/` contains the Next.js project, package manifest, and Bun lockfile. FastAPI serves the static export at `/workspace/`.
- Root `app.py` launches the API on port 7860 with the Hugging Face platform flag. The Dockerfile builds the frontend and runs Uvicorn on port 7860 with Python 3.11, one worker and a concurrency limit of 8.

## Commands

Run from the repository root in PowerShell. The Dockerfile uses pip with `backend/requirements.txt`. The Python service has no lockfile or `pyproject.toml`.

```powershell
uv venv --python 3.11                         # Create .venv on a fresh checkout
uv pip install -r backend/requirements.txt    # Install API and parser dependencies
if (!(Test-Path .env)) { Copy-Item .env.template .env }  # Populate credentials before startup
bun install --cwd frontend --frozen-lockfile
bun run --cwd frontend build
bun run --cwd frontend start                  # Serve the export and API on port 7860
python start.py                               # Optional local launcher with frontend live reload
docker build -t plexrag .
docker run --rm --env-file .env -p 7860:7860 -v plexrag-history:/app/chat-data plexrag
```

## Runtime Dependencies

- `API_KEY` authenticates `Authorization: Bearer <token>`. Startup also requires at least one populated `GEMINI_API_KEY_n` and one `GROQ_API_KEY_n`. One slot per provider suffices. Gemini handles direct media requests, and Groq handles query expansion and fallback text generation.
- Pinecone needs `PINECONE_API_KEY` and an existing `PINECONE_INDEX_NAME` with integrated embeddings mapped to the `text` field. `Config.validate_required_config` also requires `PINECONE_HOST_URL`, although the clients open the index by name. Importing `backend.main` initializes these clients before lifespan validation, even for direct Gemini requests.
- Optional reranking uses `PINECONE_RERANKER_API_KEY_n` or `COHERE_API_KEY_n`. If rerankers are unavailable, retrieval keeps the first `PINECONE_RERANK_TOP_N` candidates. Tesseract with English language data enables OCR on slide images. Docker installs it.

## Architecture

1. `backend.main.hackrx_run` handles `POST /api/v1/hackrx/run`. `HackRXRequest` requires one HTTP(S) URL in `documents` and an array of 1–50 questions, each 3–1000 characters after trimming. The route checks the bearer token and sanitizes each question.
2. `DocumentService.process_document` downloads bytes, checks size, then classifies by MIME type, filename and content. Images go to Gemini vision. Other eligible files strictly below `DIRECT_GEMINI_UPLOAD_THRESHOLD_MB` (default 0.5) go to Gemini as bytes. Both paths skip indexing.
3. For retrieval, a nonempty Pinecone namespace named `doc_<first 16 hex characters of SHA-256>` counts as a cache hit. On a miss, processors extract content from a temporary file. `DocumentService` stores chunk text and location metadata in batches of 95. Identical bytes reuse the same index entries across URLs and across changes to chunking settings.
4. The route checks relevance when enabled, asks Groq for three query variants, searches Pinecone, deduplicates hits and optionally reranks against the original question. `LLMService.generate_answer` sends the selected context to Gemini with Groq fallback. The route returns one string per question in input order.

### Non-obvious details

- `backend/main.py` refetches image bytes for every question. ZIP rejection, oversized files and some provider failures are returned inside `answers` with HTTP 200. Validation errors use HTTP 422 and invalid credentials use HTTP 401.
- The active key rotation class is `backend.services.LLMKeyManager`. The health-aware implementation in `backend/llm_key_manager.py` is separate. The batch route calls `_generate_with_groq_direct`, which falls back to the original query when an assigned key fails.
- `backend/config.py` reads environment settings at import time and caches templates from `backend/prompts.json`. Restart after changing environment values. `GET /health` reports local configuration without checking provider availability. Interactive API docs require `DEBUG=true`.

## Misc

- `DocumentService._process_docx` uses python-docx. `PyMuPDFProcessor` uses a strict cutoff of fewer than 300 pages for PDF Markdown extraction.
- The batch route returns answers. Workspace conversations save uploads and transcripts under `chat-data/`. All visitors share the conversation store. Deploy the workspace behind access control if the instance is reachable outside a trusted network.
- The configuration sample is `.env.template`. Its `MAX_URL_LENGTH=3096` exceeds the 2048-character limit in `HackRXRequest`. The repository has no test suite, configured linter, formatter or seed command.
- Ask the user before spawning or running subagents. `agent_temp/` is gitignored.

## General Working Rules (User Preferences)

- **Ignore `./temp/` completely.** Never read from it. It is the User's scratchpad.
- **Never `git commit` or `git push`.** The User reviews and commits by hand. `git pull` is fine.
- **Keep it simple.** Treat this as a hobby project unless told it is production. Don't overengineer.
- **No tests** unless the user asks. You may ask before a coding session starts.
- **Minimal comments.** Use descriptive names so the code explains itself.
- **Docs:** don't write a new `.md` per change. Ask first. If yes, update an existing `.md` or this file.
- **Python:** use `uv`, not pip, unless the project already uses pip. Keep `pyproject.toml` complete and current.
- **JS/TS:** use Bun for packages and scripts. Prefer TS over JS unless told otherwise.
- **New frontends:** latest Next.js unless told otherwise. **New backend APIs:** FastAPI.
- **Repo layout:** prefer a monorepo unless told otherwise.
- **CLI scaffolding (`bunx`/`npx`, etc.):** pass every option as flags so nothing prompts interactively. Ask the user about choices first if needed.
- **Docker:** use multi-stage builds and small base images. Multiple containers → Dockerfiles plus a `docker-compose.yml`.
- Keep `.gitignore` and `.env.example` in sync with changes.
- Use `./agent_temp` (gitignored) as a personal scratchpad for yourself or temp scripts/ data etc.
