"""
PyMuPDF Markdown Processor

This module provides fast PDF to markdown conversion using PyMuPDF4LLM with multiprocessing
for efficient processing of large documents.
"""

import os
import logging
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor

try:
    from pymupdf4llm import to_markdown
    PYMUPDF4LLM_AVAILABLE = True
except ImportError:
    PYMUPDF4LLM_AVAILABLE = False
    to_markdown = None

from backend.models import DocumentChunk, ChunkMetadata
from backend.config import Config

logger = logging.getLogger(__name__)


@dataclass
class PyMuPDFMarkdownError(Exception):
    """Custom exception for PyMuPDF markdown processing errors"""
    message: str
    error_code: str = "PYMUPDF_MARKDOWN_ERROR"
    original_error: Optional[Exception] = None


def process_batch_to_markdown(batch):
    filename, start, stop = batch
    with fitz.open(filename) as doc:
        pages = to_markdown(doc, pages=list(range(start, stop)), page_chunks=True,
                            margins=(0, 0, 0, 0), show_progress=False)
    return [(number, page["text"].strip()) for number, page in enumerate(pages, start + 1)]


class PyMuPDFMarkdownProcessor:
    """
    Fast PDF to markdown processor using PyMuPDF4LLM with multiprocessing support.

    Provides efficient markdown extraction from PDF documents with proper formatting
    and structure preservation.
    """

    def __init__(self):
        """Initialize PyMuPDF markdown processor."""
        self.supported_formats = ['.pdf']

        if not PYMUPDF4LLM_AVAILABLE:
            logger.warning("pymupdf4llm is not available. Markdown processing will not work.")

        logger.info(f"PyMuPDF markdown processor initialized (pymupdf4llm available: {PYMUPDF4LLM_AVAILABLE})")

    def can_process(self, doc_type: str) -> bool:
        """
        Check if PyMuPDF markdown processor can process the given document type.

        Args:
            doc_type: Document type/extension (with or without dot)

        Returns:
            True if processor can handle this document type
        """
        if not PYMUPDF4LLM_AVAILABLE:
            return False

        if not doc_type:
            return False

        # Normalize extension format
        if not doc_type.startswith('.'):
            doc_type = f'.{doc_type}'

        doc_type = doc_type.lower()

        can_process = doc_type in self.supported_formats
        logger.debug(f"Can process '{doc_type}' for markdown: {can_process}")

        return can_process

    def get_supported_formats(self) -> List[str]:
        """
        Get list of supported document formats for markdown processing.

        Returns:
            List of supported file extensions
        """
        return self.supported_formats.copy()

    def _read_pages(self, file_path: str, parallel: bool):
        if not PYMUPDF4LLM_AVAILABLE:
            raise PyMuPDFMarkdownError("Markdown extraction is unavailable")
        with fitz.open(file_path) as doc:
            count = len(doc)
            if doc.is_encrypted:
                raise PyMuPDFMarkdownError("This PDF is encrypted")
        workers = min(4, os.cpu_count() or 1, (count + 9) // 10) if parallel else 1
        if workers <= 1:
            yield from process_batch_to_markdown((file_path, 0, count))
            return
        size = (count + workers - 1) // workers
        batches = [(file_path, i, min(i + size, count)) for i in range(0, count, size)]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for pages in pool.map(process_batch_to_markdown, batches):
                yield from pages

    def extract_markdown_from_pdf(self, file_path: str, use_multiprocessing: bool = True) -> str:
        text = "\n\n".join(text for _, text in self._read_pages(file_path, use_multiprocessing) if text)
        if not text:
            raise PyMuPDFMarkdownError("No readable Markdown found")
        return text

    def process_document_to_markdown_chunks(self, file_path: str, document_id: str,
                                            use_multiprocessing: bool = True) -> List[DocumentChunk]:
        chunks = [
            DocumentChunk(content=text, metadata=ChunkMetadata(
                document_id=document_id, page_number=page, line_number=1, chunk_number=page,
                document_type="pdf", file_name=Path(file_path).name,
            ))
            for page, text in self._read_pages(file_path, use_multiprocessing) if text
        ]
        if not chunks:
            raise PyMuPDFMarkdownError("No readable Markdown found")
        return chunks

    def get_document_info(self, file_path: str) -> Dict[str, Any]:
        """
        Get document information for markdown processing.

        Args:
            file_path: Path to the PDF file

        Returns:
            Dictionary containing document information
        """
        doc = None
        try:
            doc = fitz.open(file_path)

            info = {
                'page_count': len(doc),
                'is_encrypted': doc.is_encrypted,
                'format': 'PDF',
                'metadata': doc.metadata,
                'file_size': os.path.getsize(file_path),
                'file_name': Path(file_path).name,
                'markdown_supported': PYMUPDF4LLM_AVAILABLE
            }

            # Add page dimensions for first page if available
            if len(doc) > 0:
                first_page = doc[0]
                rect = first_page.rect
                info['page_dimensions'] = {
                    'width': rect.width,
                    'height': rect.height
                }

            return info

        except Exception as e:
            logger.error(f"Failed to get document info for {file_path}: {e}")
            return {
                'error': str(e),
                'file_name': Path(file_path).name,
                'file_size': os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                'markdown_supported': PYMUPDF4LLM_AVAILABLE
            }
        finally:
            if doc:
                try:
                    doc.close()
                except Exception as cleanup_error:
                    logger.warning(f"Failed to close document: {cleanup_error}")

    def validate_document(self, file_path: str) -> Tuple[bool, str]:
        """
        Validate if PDF document can be processed for markdown extraction.

        Args:
            file_path: Path to the PDF file

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            if not PYMUPDF4LLM_AVAILABLE:
                return False, "pymupdf4llm is not available"

            if not os.path.exists(file_path):
                return False, "File does not exist"

            if os.path.getsize(file_path) == 0:
                return False, "File is empty"

            # Try to open the document
            doc = None
            try:
                doc = fitz.open(file_path)

                if doc.is_encrypted:
                    return False, "Document is encrypted"

                if len(doc) == 0:
                    return False, "Document has no pages"

                return True, "Document is valid for markdown processing"

            finally:
                if doc:
                    doc.close()

        except Exception as e:
            return False, f"Document validation failed: {str(e)}"
