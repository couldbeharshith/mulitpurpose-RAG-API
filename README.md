---
title: Folio
emoji: 📚
colorFrom: indigo
colorTo: blue
sdk: docker
pinned: false
short_description: A conversational workspace for documents and source files
---

# Folio

Open a source, ask a question, and follow up. Folio pairs a self-hosted Next.js workspace with a FastAPI retrieval API. It works with material from any field, including reports, research papers, presentations, spreadsheets, correspondence, and images.

## Run with Docker

Copy `.env.template` to `.env` and configure the providers below. From the repository root, run:

```sh
docker build -t folio .
docker run --rm --env-file .env -p 7860:7860 folio
```

Open [the workspace](http://localhost:7860/workspace/). One container serves the UI, its fonts, and the API.

### Provider settings

- Set at least one `GEMINI_API_KEY_n` and one `GROQ_API_KEY_n`. Gemini handles direct files. The retrieval pipeline uses Groq for query expansion and as a text-generation fallback.
- Set `PINECONE_API_KEY`, `PINECONE_HOST_URL`, and `PINECONE_INDEX_NAME`. Create an index with integrated text embeddings and map its input to the `text` field. Startup initializes the vector client even when a file qualifies for direct analysis.
- Leave `API_KEY` empty for a token-free instance. To restrict access, set it to a secret and restart. Enter the same value under **Access** in Folio or send it as an `Authorization: Bearer <token>` header. Provider keys stay on the server.
- Optional Pinecone or Cohere reranking uses the numbered reranker keys in the template. A single configured slot per provider is sufficient. The template also includes file-size, relevance, model, and chunking settings.

## Run from source

The Python package lives in `backend/` and the Next.js project in `frontend/`. Use Python 3.11, uv, Node.js 22, and Bun. The following commands run from the repository root after configuring `.env`:

```sh
uv venv --python 3.11
uv pip install -r backend/requirements.txt
bun install --cwd frontend --frozen-lockfile
bun run --cwd frontend build
uv run --no-project python -m uvicorn backend.main:app --host 127.0.0.1 --port 7860
```

Open [Folio](http://127.0.0.1:7860/workspace/). In development, run `bun run --cwd frontend dev` in another terminal and open [the live-reloading frontend](http://localhost:3000/workspace/). The dev UI calls the API at `http://127.0.0.1:7860` by default. Set `NEXT_PUBLIC_API_ORIGIN` before starting Next.js to use another API origin in development. The production build uses the same origin as the workspace.

## Using the workspace

- Choose a file, drop one into the workspace, paste a direct HTTP(S) link, or open a bundled sample. Processing starts with the first question.
- Each conversation has one source. Open another conversation to explore a different file. Switch between them in the sidebar. Use the question tabs beneath the active source, or **Questions** on mobile, to jump to an earlier exchange.
- The UI sends one question per turn. It supplies the eight most recent exchanges, with up to 4,000 characters per previous answer, to resolve follow-ups before searching the source. Earlier turns remain readable in the current tab.
- The tab holds the conversations, selected files, and access token in memory. Refreshing clears them. Indexed sources use a bounded server-side lookup so follow-ups can reuse the index without resending the file. The browser resubmits the source if that lookup expires. Document chunks stored in Pinecone persist independently.

## Sources and processing

| Source | Processing |
| --- | --- |
| PDFs | With Markdown extraction enabled (default), PDFs over 10 pages go through PyMuPDF4LLM even below the direct-upload size threshold. Extraction retains page metadata and falls back to text if conversion fails. Short PDFs remain eligible for direct analysis. Image-only scans may require OCR before upload. |
| Word, presentations, spreadsheets | DOCX uses python-docx. PPTX preserves slide structure and can OCR embedded images with Tesseract, included in Docker. XLSX uses openpyxl to extract worksheet tables. |
| Text, email, and code | Supports plain text, Markdown, CSV, JSON, HTML, EML, and other text files. File type and size determine whether content is analyzed directly or chunked. |
| Images | Supported images use Gemini vision. |
| Audio and video | Small supported clips use direct Gemini analysis under `DIRECT_GEMINI_UPLOAD_THRESHOLD_MB` (default 0.5 MB). For longer recordings, use a transcript. Long-form audio/video indexing and timestamp retrieval are future work. |

For indexed documents, Folio splits extracted content with tiktoken, stores records in a content-addressed Pinecone namespace, expands search queries, combines matching chunks, optionally reranks them, and sends the selected context to the answer model. Long PDFs have a versioned namespace so older plain-text indexes do not mask the new extraction. Repeated identical content can reuse an existing index.

## API

### Batch questions from a URL

`POST /api/v1/hackrx/run` accepts one HTTP(S) source URL and **1–50 questions** of 3–1,000 characters. Answers follow input order.

```json
{
  "documents": "https://example.org/materials-report.pdf",
  "questions": [
    "Which materials were compared?",
    "How was humidity controlled during the trial?"
  ]
}
```

The response has the form `{"answers": ["First answer", "Second answer"]}`. The workspace and batch API use the same bearer-token setting.

### Conversational requests

`POST /api/v1/chat` accepts multipart form data. Include exactly one of `file`, `url`, or a previously returned `source_id`, plus a JSON string in the `payload` field.

```sh
curl http://localhost:7860/api/v1/chat \
  -F 'file=@report.pdf' \
  -F 'payload={"questions":["What are the main findings?"],"history":[]}'
```

The response contains `answers` and a nullable `source_id`. Each item in `history` contains a `question` and its `answer`. Indexed sources can reuse their handle. Directly analyzed sources are supplied on each turn. A stale handle returns HTTP 410 and can be replaced by sending the original source again.

`GET /api/v1/workspace` reports upload limits and whether a token is required. `GET /health` reports local service configuration. Browsers opening `/` are redirected to the built workspace. API clients requesting JSON receive service information. Set `DEBUG=true` to enable interactive API documentation at `/docs`.

## Project history

The original insurance-focused API was developed on [Hugging Face Spaces](https://huggingface.com/couldbeharshith/insurance-agent). Folio retains its batch endpoint for existing integrations.
