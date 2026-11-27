---
title: PlexRAG
emoji: 📚
colorFrom: indigo
colorTo: blue
sdk: docker
pinned: false
short_description: A conversational workspace for documents and source files
---

# PlexRAG

Open a source, ask a question, and follow up. PlexRAG pairs a self-hosted Next.js workspace with a FastAPI retrieval API. It works with material from any field, including reports, research papers, presentations, spreadsheets, correspondence, and images.

## Run with Docker

Copy `.env.template` to `.env` and configure the providers below. From the repository root, run:

```sh
docker build -t plexrag .
docker run --rm --env-file .env -p 7860:7860 -v plexrag-history:/app/chat-data plexrag
```

Open [the workspace](http://localhost:7860/workspace/). One container serves the UI, its fonts, and the API.

Use a private instance or put it behind authentication before exposing it publicly. Everyone who can reach the workspace can read and modify its saved conversations. The batch API bearer token protects `/api/v1/hackrx/run` only.

### Provider settings

- Set at least one `GEMINI_API_KEY_n` and one `GROQ_API_KEY_n`. Gemini handles direct files. The retrieval pipeline uses Groq for query expansion and as a text-generation fallback.
- Set `PINECONE_API_KEY`, `PINECONE_HOST_URL`, and `PINECONE_INDEX_NAME`. Create an index with integrated text embeddings and map its input to the `text` field. Startup initializes the vector client even when a file qualifies for direct analysis.
- Optional Pinecone or Cohere reranking uses the numbered reranker keys in the template. A single configured slot per provider is sufficient. The template also includes file-size, relevance, model, and chunking settings.

## Run from source

The Python package lives in `backend/` and the Next.js project in `frontend/`. Use Python 3.11, uv, Node.js 22, and Bun. The following commands run from the repository root after configuring `.env`:

```sh
uv venv --python 3.11
uv pip install -r backend/requirements.txt
bun install --cwd frontend --frozen-lockfile
bun run --cwd frontend build
bun run --cwd frontend start
```

Open [the workspace](http://127.0.0.1:7860/workspace/). The start command serves the frontend build and API from the same FastAPI process. Rebuild after changing frontend code.

For live reload, run `python start.py` from the repository root. The launcher starts the Next.js development server and API on ports 3000 and 7860 by default. Open the frontend URL it prints. Press Ctrl+C to stop both.

## Using the workspace

- Choose a file, drop one into the workspace, paste a direct HTTP(S) link, or open a bundled sample. Processing starts with the first question.
- Each conversation has one source. Open another conversation to explore a different file. Switch between them in the sidebar. Use the question tabs beneath the active source, or **Questions** on mobile, to jump to an earlier exchange.
- Choose **Fast** or **Agentic** under **Answer mode** before sending a question. New conversations and page reloads start in Fast.
- The first successful answer gives the conversation a title. Use its sidebar menu to rename, pin, or delete it. The UI sends one question per turn. The API uses the eight most recent exchanges, with up to 4,000 characters per previous answer, to resolve follow-ups before searching the source.
- The server saves transcripts and uploaded files in the git-ignored `chat-data/` folder. Browsers connected to the same server share this history. Chats and uploads survive a reload or restart. In Docker, keep the history volume mounted across runs. Deleting a conversation removes the local transcript and upload. Content-indexed chunks in Pinecone are shared by identical sources and have a separate lifecycle.

## Sources and processing

| Source | Processing |
| --- | --- |
| PDFs | With Markdown extraction enabled (default), PDFs over 10 pages go through PyMuPDF4LLM even below the direct-upload size threshold. Extraction retains page metadata and falls back to text if conversion fails. Short PDFs remain eligible for direct analysis. Image-only scans may require OCR before upload. |
| Word, presentations, spreadsheets | DOCX uses python-docx. PPTX preserves slide structure and can OCR embedded images with Tesseract, included in Docker. XLSX uses openpyxl to extract worksheet tables. |
| Text, email, and code | Supports plain text, Markdown, CSV, JSON, HTML, EML, and other text files. File type and size determine whether content is analyzed directly or chunked. |
| Images | Supported images use Gemini vision. |
| Audio and video | Small supported clips use direct Gemini analysis under `DIRECT_GEMINI_UPLOAD_THRESHOLD_MB` (default 0.5 MB). For longer recordings, use a transcript. Long-form audio/video indexing and timestamp retrieval are future work. |

For indexed documents, PlexRAG splits extracted content with tiktoken and stores passages in a content-addressed Pinecone namespace. Repeated identical content can reuse the index. Long PDFs have a versioned namespace for Markdown extraction.

## Answer modes

- **Fast (default)** searches an indexed source once with the question, optionally reranks the matches, and generates an answer from the selected passages. The relevance threshold, when enabled, uses scores from that same search. Direct sources use a single answer step.
- **Agentic** starts with the same source search. If the passages are insufficient, it can run up to three targeted searches in one additional round. It checks that cited quotations occur in the source and asks a separate model call to verify the draft against the evidence. Approved answers include passage references and available page, slide, or sheet numbers. For sources analyzed directly, the verifier reviews the full attachment. If the evidence does not support an answer, Agentic reports the gap. Extra searches and verification can take longer.

## API

### Batch questions from a URL

`POST /api/v1/hackrx/run` accepts one HTTP(S) source URL and **1–50 questions** of 3–1,000 characters. Answers follow input order. Both answer endpoints accept optional `rag_mode` values `"fast"` and `"agentic"`. Omitting it selects Fast.

```json
{
  "documents": "https://example.org/materials-report.pdf",
  "rag_mode": "agentic",
  "questions": [
    "Which materials were compared?",
    "How was humidity controlled during the trial?"
  ]
}
```

The response has the form `{"answers": ["First answer", "Second answer"]}`.

### Conversational requests

`POST /api/v1/chat` accepts multipart form data. Include exactly one of `file`, `url`, a previously returned `source_id`, or a saved `conversation_id`, plus a JSON string in the `payload` field.

```sh
curl http://localhost:7860/api/v1/chat \
  -F 'file=@report.pdf' \
  -F 'payload={"questions":["What are the main findings?"],"history":[],"rag_mode":"agentic"}'
```

The response contains `answers` and a nullable `source_id`. Each item in `history` contains a `question` and its `answer`. Indexed sources can reuse their handle. Directly analyzed sources are supplied on each turn. A stale handle returns HTTP 410 and can be replaced by sending the original source again.

For saved conversations, `POST /api/v1/conversations` accepts multipart `name` and either `file` or `url`. Pass its returned `id` as `conversation_id` when asking a question. The chat endpoint uses saved history and returns the updated `conversation` with its `answers`. Use `GET /api/v1/conversations` to list chats and `PATCH` or `DELETE /api/v1/conversations/{id}` to manage one.

`GET /api/v1/workspace` reports upload limits. `GET /health` reports local service configuration. Browsers opening `/` are redirected to the built workspace. API clients requesting JSON receive service information.

The backend logs warnings and errors by default. Set `LOG_LEVEL=INFO` for request summaries and access logs, or `LOG_LEVEL=DEBUG` for detailed processing logs. Setting `DEBUG=true` enables interactive API documentation at `/docs` and defaults the log level to `DEBUG` when `LOG_LEVEL` is unset.

## Project history

The original insurance-focused API was developed on [Hugging Face Spaces](https://huggingface.com/couldbeharshith/insurance-agent). PlexRAG retains its batch endpoint for existing integrations.
