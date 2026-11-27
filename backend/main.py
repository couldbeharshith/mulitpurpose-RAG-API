"""FastAPI application for the PlexRAG source workspace and batch API."""

import asyncio
import base64
import hashlib
import json
import logging
import mimetypes
import re
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from backend.config import Config
from backend import conversations
from backend.models import HackRXRequest, HackRXResponse, ErrorResponse, ChatInput, DocumentProcessingResult, RagMode
from backend.services import (
    DocumentService,
    VectorService,
    LLMService,
)
from backend.rag import RagService
from backend.utils import (
    sanitize_input,
    log_performance_metrics,
)

logger = logging.getLogger(__name__)
log_level = logging.getLevelName(Config.LOG_LEVEL.strip().upper())
if not isinstance(log_level, int):
    log_level = logging.DEBUG if Config.DEBUG else logging.WARNING
if not logging.getLogger().handlers:
    log_format = Config.LOG_FORMAT
    try:
        logging.Formatter(log_format)
    except ValueError:
        log_format = Config.DEFAULT_LOG_FORMAT
    logging.basicConfig(level=log_level, format=log_format)
    if log_format != Config.LOG_FORMAT:
        logger.warning("Invalid LOG_FORMAT. Using the default log format.")
logging.getLogger("backend").setLevel(log_level)
logging.getLogger("performance").setLevel(log_level)
logging.getLogger("httpx").setLevel(max(logging.INFO, log_level))
logging.getLogger("httpcore").setLevel(max(logging.WARNING, log_level))

# Get application settings from Config
app_name = Config.APP_NAME
app_version = Config.APP_VERSION
debug_mode = Config.DEBUG

# Initialize services at module level
document_service = DocumentService()
vector_service = VectorService()
llm_service = LLMService()
rag_service = RagService(vector_service, llm_service)


# Define lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for application startup and shutdown
    """
    logging.getLogger("uvicorn.access").setLevel(max(logging.INFO, log_level))
    logger.info(f"Starting {app_name} v{app_version} on {Config.PLATFORM}")

    # Validate required configuration
    missing_configs = Config.validate_required_config()
    if missing_configs:
        logger.error(f"Missing required configuration: {missing_configs}")
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing_configs)}"
        )

    # Log configuration summary (without sensitive data)
    config_summary = Config.get_config_summary()
    logger.debug("Application configuration: %s", config_summary)

    logger.info(
        f"Direct Gemini upload enabled for supported file types < {Config.DIRECT_GEMINI_UPLOAD_THRESHOLD_MB}MB (PDF, text, HTML, images, audio, video)"
    )

    logger.info("Application startup complete and ready to serve requests")

    yield

    logger.info("Application shutdown complete")


# Log startup information
logger.info(f"Starting {app_name} v{app_version}")
logger.info(f"Debug mode: {debug_mode}")

# Create FastAPI app with simplified configuration
app = FastAPI(
    title=app_name,
    description="Source-grounded question answering for documents, spreadsheets, presentations and other sources.",
    version=app_version,
    docs_url="/docs" if debug_mode else None,
    redoc_url="/redoc" if debug_mode else None,
    debug=debug_mode,
    lifespan=lifespan,
    openapi_url="/openapi.json" if debug_mode else None,
)
app.include_router(conversations.router)

workspace_dir = Path(__file__).resolve().parents[1] / "frontend" / "out"
workspace_csp = None
if (workspace_dir / "index.html").is_file():
    html = (workspace_dir / "index.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script\b[^>]*>(.*?)</script>", html, flags=re.DOTALL)
    hashes = ["'sha256-" + base64.b64encode(hashlib.sha256(s.encode()).digest()).decode() + "'"
              for s in scripts if s]
    workspace_csp = "default-src 'self'; script-src 'self' " + " ".join(hashes) + "; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self'"
    app.mount("/workspace", StaticFiles(directory=workspace_dir, html=True), name="workspace")

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,
)


# Add security middleware
@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Security middleware for request validation and headers."""
    start_time = time.time()

    # No request size limits - removed size restrictions
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            content_length = int(content_length)
            logger.debug("Request content length: %d bytes", content_length)
        except ValueError:
            pass  # Invalid content-length header, let it pass

    # Process request
    response = await call_next(request)

    # Add security headers
    for header_name, header_value in Config.SECURITY_HEADERS.items():
        response.headers[header_name] = header_value

    if workspace_csp and request.url.path.startswith("/workspace/"):
        response.headers["Content-Security-Policy"] = workspace_csp

    # Add platform-specific headers
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Platform"] = Config.PLATFORM
    response.headers["X-Serverless"] = str(Config.is_serverless())

    # Log long-running requests for monitoring (no limits enforced)
    if process_time > 60:  # Log requests over 1 minute for monitoring
        logger.info(
            f"Long-running request: {process_time:.2f}s",
            extra={
                "event_type": "long_request",
                "process_time": process_time,
                "path": str(request.url.path),
                "method": request.method,
            },
        )

    return response


# HackRX API endpoint
@app.post("/api/v1/hackrx/run", response_model=HackRXResponse)
async def hackrx_run(request: HackRXRequest):
    try:
        document = await document_service.process_document_from_url(request.documents, vector_service)
    except Exception as exc:
        raise HTTPException(500, detail=ErrorResponse(error_type=type(exc).__name__, message=str(exc),
                            timestamp=datetime.now(timezone.utc).isoformat(), request_id=str(uuid.uuid4())).model_dump()) from exc
    return await answer_document(document, request.questions, request.rag_mode)


async def answer_document(
    document_result: DocumentProcessingResult, questions: list[str], rag_mode: RagMode = "fast",
):
    agentic = rag_mode == "agentic"
    request_id = str(uuid.uuid4())
    start_time = time.time()
    sanitized_questions = [sanitize_input(q) for q in questions]
    try:
        # Check if this is an image document and handle it specially
        if document_result.namespace.startswith("image_") or (
            document_result.chunks
            and len(document_result.chunks) > 0
            and document_result.chunks[0].metadata.document_type == "image"
        ):

            logger.info(
                f"Image document detected, using direct Gemini vision API (no vector storage)"
            )

            # For image documents, process questions directly with Gemini vision API
            async def process_image_question(question: str, question_index: int) -> str:
                """Process a single question about an image using Gemini vision API."""
                try:
                    logger.debug("Processing image question %d", question_index + 1)

                    content = document_result.direct_gemini_content

                    # Save image to temporary file for processing
                    import tempfile

                    with tempfile.NamedTemporaryFile(
                        suffix=".jpg", delete=False
                    ) as temp_file:
                        temp_file.write(content)
                        temp_image_path = temp_file.name

                    try:
                        # Use LLM service for image analysis
                        answer = await llm_service.generate_image_answer(
                            question, temp_image_path, agentic=agentic,
                        )
                        return answer
                    finally:
                        # Clean up temporary file
                        import os

                        try:
                            os.unlink(temp_image_path)
                        except Exception as cleanup_error:
                            logger.warning(
                                f"Failed to cleanup temporary image file: {cleanup_error}"
                            )

                except Exception as e:
                    logger.error(
                        f"Error processing image question {question_index + 1}: {e}"
                    )
                    return f"I apologize, but I encountered an error while analyzing the image: {str(e)}"

            # Process all image questions
            logger.info(f"Processing {len(sanitized_questions)} image questions")

            # Create tasks for parallel execution of image questions
            image_question_tasks = [
                process_image_question(question, i)
                for i, question in enumerate(sanitized_questions)
            ]

            # Execute all image questions in parallel
            processed_answers = await asyncio.gather(
                *image_question_tasks, return_exceptions=True
            )

            # Create final answers array
            final_answers = []
            successful_questions = 0

            # Fill in processed answers
            for i, answer in enumerate(processed_answers):
                if isinstance(answer, Exception):
                    logger.error(
                        f"Image question {i+1} failed with exception: {answer}"
                    )
                    final_answers.append(
                        f"I apologize, but I encountered an error while analyzing the image."
                    )
                else:
                    final_answers.append(answer)
                    successful_questions += 1

            processing_time = time.time() - start_time

            # Log performance metrics
            await log_performance_metrics(
                request_id=request_id,
                endpoint="/api/v1/hackrx/run",
                processing_time=processing_time,
                questions_count=len(questions),
                success=True,
            )

            logger.info(
                f"HackRX image request completed: {request_id} in {processing_time:.2f}s "
                f"({successful_questions}/{len(questions)} questions successful)"
            )


            return HackRXResponse(answers=final_answers)

        # Check if this is a direct Gemini document and handle it specially
        if (
            document_result.namespace.startswith("direct_gemini_")
            and hasattr(document_result, "direct_gemini_content")
            and document_result.direct_gemini_content is not None
        ):

            logger.info(
                f"Direct Gemini document detected, using direct Gemini API (no vector storage)"
            )

            # For direct Gemini documents, process questions directly with Gemini document API
            async def process_direct_gemini_question(
                question: str, question_index: int
            ) -> str:
                """Process a single question about a document using direct Gemini API."""
                try:
                    logger.debug("Processing direct Gemini question %d", question_index + 1)

                    # Get filename from chunks metadata
                    filename = "document"
                    if document_result.chunks and len(document_result.chunks) > 0:
                        filename = document_result.chunks[0].metadata.file_name

                    # Use LLM service for direct document analysis
                    answer = await llm_service.generate_direct_gemini_answer(
                        question,
                        document_result.direct_gemini_content,
                        document_result.direct_gemini_content_type,
                        filename,
                        agentic=agentic,
                    )
                    return answer

                except Exception as e:
                    logger.error(
                        f"Error processing direct Gemini question {question_index + 1}: {e}"
                    )
                    return f"I apologize, but I encountered an error while analyzing the document: {str(e)}"

            # Process all direct Gemini questions
            logger.info(
                f"Processing {len(sanitized_questions)} direct Gemini questions"
            )

            # Create tasks for parallel execution of direct Gemini questions
            direct_gemini_question_tasks = [
                process_direct_gemini_question(question, i)
                for i, question in enumerate(sanitized_questions)
            ]

            # Execute all direct Gemini questions in parallel
            processed_answers = await asyncio.gather(
                *direct_gemini_question_tasks, return_exceptions=True
            )

            # Create final answers array
            final_answers = []
            successful_questions = 0

            for i, answer in enumerate(processed_answers):
                if isinstance(answer, Exception):
                    logger.error(
                        f"Direct Gemini question {i+1} failed with exception: {answer}"
                    )
                    final_answers.append(
                        f"I apologize, but I encountered an error while analyzing the document."
                    )
                else:
                    final_answers.append(answer)
                    successful_questions += 1

            processing_time = time.time() - start_time

            # Log performance metrics
            await log_performance_metrics(
                request_id=request_id,
                endpoint="/api/v1/hackrx/run",
                processing_time=processing_time,
                questions_count=len(questions),
                success=True,
            )

            logger.info(
                f"HackRX direct Gemini request completed: {request_id} in {processing_time:.2f}s "
                f"({successful_questions}/{len(questions)} questions successful)"
            )


            return HackRXResponse(answers=final_answers)

        # Check if this is a ZIP file rejection
        if document_result.document_hash == "zip_rejected":
            logger.info(f"ZIP file rejected, returning standard response")
            zip_rejection_message = "ZIP files cannot be processed using this API."

            # Return ZIP rejection message for all questions
            final_answers = [zip_rejection_message] * len(questions)

            processing_time = time.time() - start_time

            # Log performance metrics
            await log_performance_metrics(
                request_id=request_id,
                endpoint="/api/v1/hackrx/run",
                processing_time=processing_time,
                questions_count=len(questions),
                success=True,
            )

            logger.info(
                f"HackRX request completed (ZIP rejected): {request_id} in {processing_time:.2f}s "
                f"({len(questions)} questions, ZIP file rejected)"
            )

            return HackRXResponse(answers=final_answers)

        # Check if file is too large
        if document_result.document_hash == "file_too_large":
            logger.info(f"File too large, returning error message for all questions")
            file_too_large_message = (
                "The file uploaded is too large and is over the file limit of this API."
            )

            # Return the same error message for ALL questions
            final_answers = [file_too_large_message] * len(questions)

            processing_time = time.time() - start_time

            # Log performance metrics
            await log_performance_metrics(
                request_id=request_id,
                endpoint="/api/v1/hackrx/run",
                processing_time=processing_time,
                questions_count=len(questions),
                success=True,
            )

            logger.info(
                f"HackRX request completed (file too large): {request_id} in {processing_time:.2f}s "
                f"({len(questions)} questions, all answered with file too large message)"
            )

            return HackRXResponse(answers=final_answers)

        answer_question = rag_service.answer_agentic if agentic else rag_service.answer
        question_semaphore = asyncio.Semaphore(Config.MAX_CONCURRENT_REQUESTS)

        async def answer_indexed(question: str) -> str:
            async with question_semaphore:
                try:
                    return await answer_question(question, document_result)
                except Exception:
                    logger.exception("Indexed question failed")
                    return "I apologize, but I encountered an error while processing this question. Please try again."

        unique_questions = dict.fromkeys(sanitized_questions)
        answers = await asyncio.gather(*(answer_indexed(question) for question in unique_questions))
        by_question = dict(zip(unique_questions, answers))
        final_answers = [by_question[question] for question in sanitized_questions]
        successful_questions = sum(not answer.startswith("I apologize, but") for answer in final_answers)

        processing_time = time.time() - start_time

        # Log comprehensive performance metrics
        await log_performance_metrics(
            request_id=request_id,
            endpoint="/api/v1/hackrx/run",
            processing_time=processing_time,
            questions_count=len(questions),
            success=True,
        )

        logger.info(
            f"HackRX request completed: {request_id} in {processing_time:.2f}s "
            f"({successful_questions}/{len(questions)} questions successful, "
            f"document cached: {document_result.cached if document_result else 'N/A'})"
        )


        return HackRXResponse(answers=final_answers)

    except HTTPException:
        # Re-raise HTTP exceptions (like authentication failures)
        raise

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(
            f"HackRX request failed: {request_id} after {processing_time:.2f}s - {e}"
        )

        # Log performance metrics for failed request
        await log_performance_metrics(
            request_id=request_id,
            endpoint="/api/v1/hackrx/run",
            processing_time=processing_time,
            questions_count=len(questions),
            success=False,
        )

        # Return structured error response
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error_type=type(e).__name__,
                message=str(e),
                details={
                    "request_id": request_id,
                    "processing_time": processing_time,
                    "endpoint": "/api/v1/hackrx/run",
                },
                timestamp=datetime.now(timezone.utc).isoformat(),
                request_id=request_id,
            ).model_dump(),
        )


# Small, opaque handles let indexed sources serve follow-ups without another upload.
indexed_sources: OrderedDict[str, tuple[str, str]] = OrderedDict()


@app.get("/api/v1/workspace")
async def workspace_settings():
    return {
        "max_file_mb": Config.MAX_DOCUMENT_SIZE_MB,
        "direct_media_mb": Config.DIRECT_GEMINI_UPLOAD_THRESHOLD_MB,
    }


@app.post("/api/v1/chat")
async def chat(request: Request, payload: str = Form(...), file: Optional[UploadFile] = File(None),
               url: Optional[str] = Form(None), source_id: Optional[str] = Form(None),
               conversation_id: uuid.UUID | None = Form(None)):
    if sum(bool(value) for value in (file, url, source_id, conversation_id)) != 1:
        raise HTTPException(422, "Choose one file or one source link.")
    try:
        chat_input = ChatInput.model_validate_json(payload)
        if url:
            url = HackRXRequest(documents=url, questions=chat_input.questions).documents
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_input=False, include_context=False)[0]["msg"]) from exc

    conversation = None
    if conversation_id:
        conversation = await asyncio.to_thread(conversations.get_conversation, conversation_id)
        url = conversation.source.url
    cache_key = source_id or (f"chat_{conversation_id}" if conversation_id else None)
    stored = indexed_sources.get(cache_key)
    if stored or source_id:
        if not stored:
            raise HTTPException(410, "Reattach the source to continue this conversation.")
        indexed_sources.move_to_end(cache_key)
        doc_hash, namespace = stored
        document = DocumentProcessingResult(document_hash=doc_hash, namespace=namespace,
                                            chunks=[], cached=True, processing_time=0)
    else:
        if conversation and not url:
            content = await asyncio.to_thread(conversations.read_source, conversation_id)
            filename, content_type = conversation.source.name, conversation.source.content_type
        elif file:
            limit = Config.MAX_DOCUMENT_SIZE_MB * 1024 * 1024
            if file.size is not None and file.size > limit:
                raise HTTPException(413, f"Choose a file up to {Config.MAX_DOCUMENT_SIZE_MB} MB.")
            content = await file.read() if file.size is not None else await file.read(limit + 1)
            if len(content) > limit:
                raise HTTPException(413, f"Choose a file up to {Config.MAX_DOCUMENT_SIZE_MB} MB.")
            filename = Path(file.filename or "source").name
            content_type = file.content_type or ""
        else:
            filename = Path(urlparse(url).path).name or "source"
            try:
                content, content_type = await document_service.fetch_document(url)
            except Exception as exc:
                raise HTTPException(422, "Could not open this link. Use a direct file link or upload the file.") from exc
        if content_type == "application/oversized":
            raise HTTPException(413, f"Choose a file up to {Config.MAX_DOCUMENT_SIZE_MB} MB.")
        if not content:
            raise HTTPException(422, "This source is empty. Choose a file with readable content.")
        media_type = content_type.split(";")[0]
        if not media_type.startswith(("audio/", "video/")):
            media_type = mimetypes.guess_type(filename)[0] or media_type
        if media_type.startswith(("audio/", "video/")):
            if len(content) >= Config.DIRECT_GEMINI_UPLOAD_THRESHOLD_MB * 1024**2:
                raise HTTPException(415, "This clip exceeds the direct media limit. Upload its transcript instead.")
            content_type = media_type
        try:
            document = await document_service.process_bytes(content, content_type, filename, vector_service)
        except Exception as exc:
            logger.exception("Could not prepare chat source")
            raise HTTPException(422, "Could not read or index this source. Check the file and the server's provider settings.") from exc
        if document.document_hash == "zip_rejected":
            raise HTTPException(415, "Extract the archive and choose one of its documents.")
        if not document.cached and not document.chunks:
            raise HTTPException(422, "No readable content was found. For a scanned document, try an OCR or text version.")

    questions = chat_input.questions
    past_turns = conversation.turns[-8:] if conversation else chat_input.history
    if past_turns:
        history = json.dumps([
            {"question": turn.question, "answer": turn.answer[:4000]} for turn in past_turns
        ], ensure_ascii=False)
        async def resolve(question: str):
            prompt = Config.get_prompt("chat_followup", question=question, history=history)
            return await llm_service._try_gemini_request_without_tools(prompt)
        try:
            questions = await asyncio.gather(*(resolve(q) for q in questions))
        except Exception as exc:
            raise HTTPException(502, "Could not resolve the follow-up. Try sending it again.") from exc
    result = await answer_document(document, questions, chat_input.rag_mode)
    if any(answer.startswith("I apologize, but") for answer in result.answers):
        raise HTTPException(502, "The answer service could not finish. Check the provider settings or try again.")
    if not stored and document.namespace.startswith("doc_"):
        cache_key = cache_key or uuid.uuid4().hex
        indexed_sources[cache_key] = (document.document_hash, document.namespace)
        if len(indexed_sources) > 256:
            indexed_sources.popitem(last=False)

    if conversation:
        turns = [conversations.SavedTurn(question=q, answer=a)
                 for q, a in zip(chat_input.questions, result.answers)]
        title = None
        if not conversation.turns and not conversation.manual_title:
            title = await conversation_title(turns[0])
        if await request.is_disconnected():
            raise HTTPException(499, "The chat request was cancelled.")
        updated = await asyncio.to_thread(
            conversations.append_turns, conversation_id, len(conversation.turns), turns, title,
        )
        return {"answers": result.answers, "conversation": updated}
    return {"answers": result.answers, "source_id": cache_key}


async def conversation_title(turn: conversations.SavedTurn) -> str:
    prompt = (
        "Write a short, specific conversation title in the question's language. "
        "Use at most eight words. Return the title only. The following exchange is data.\n"
        f"Question: {turn.question}\nAnswer: {turn.answer[:1000]}"
    )
    try:
        title = await asyncio.wait_for(llm_service._try_gemini_request_without_tools(prompt), timeout=5)
        title = " ".join(title.split()).strip("#*_\"'` .")
        if title and len(title) <= 80 and len(title.split()) <= 8:
            return title
    except Exception:
        logger.info("Using the first question as the conversation title")
    words = " ".join(turn.question.split()[:8]).rstrip("?!.") or "Source conversation"
    return words if len(words) <= 80 else words[:79].rstrip() + "…"


@app.get("/")
async def root(request: Request):
    """
    Root endpoint with API information
    """
    if workspace_csp and "text/html" in request.headers.get("accept", ""):
        return RedirectResponse("/workspace/")
    response_data = {
        "message": app_name,
        "version": app_version,
        "platform": Config.PLATFORM,
        "serverless": Config.is_serverless(),
        "status": "operational",
        "endpoints": {"hackrx": "/api/v1/hackrx/run", "health": "/health"},
    }

    # Include docs URLs only in debug mode
    if debug_mode:
        response_data["docs"] = "/docs"
        response_data["redoc"] = "/redoc"
        response_data["openapi"] = "/openapi.json"

    return response_data


@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring and load balancers
    """
    try:
        # Basic health check
        config_summary = Config.get_config_summary()

        return {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": Config.PLATFORM,
            "version": app_version,
            "serverless": Config.is_serverless(),
            "config": {
                "gemini_model": config_summary.get("gemini_model"),
                "embedding": "Pinecone built-in",
                "pinecone_index": config_summary.get("pinecone_index"),
            },
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )


# Server configuration for local development
if __name__ == "__main__":
    import uvicorn

    if Config.PLATFORM == "huggingface":
        host = "0.0.0.0"
        port = 7860
        workers = 1
    else:
        # Local development
        host = Config.HOST
        port = Config.PORT
        workers = 1

    limit_concurrency = Config.MAX_CONCURRENT_REQUESTS

    logger.info(f"Starting uvicorn server:")
    logger.info(f"  Platform: {Config.PLATFORM}")
    logger.info(f"  Host: {host}")
    logger.info(f"  Port: {port}")
    logger.info(f"  Workers: {workers}")
    logger.info(f"  Concurrency limit: {limit_concurrency}")
    logger.info(f"  Debug mode: {debug_mode}")

    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        workers=workers,
        limit_concurrency=limit_concurrency,
        reload=debug_mode,
        access_log=log_level <= logging.INFO,
        log_level="info" if debug_mode else "warning",
    )
