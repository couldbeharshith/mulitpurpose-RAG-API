---
title: Insurance Agent
emoji: 🐨
colorFrom: red
colorTo: red
sdk: docker
pinned: false
short_description: API
---

# Insurance RAG API

A high-accuracy RAG-based API for processing insurance policy queries with URL-based document processing and Pinecone vector storage.

## Features

- **Document Processing**: Supports PDF, DOCX, TXT, and EML files from URLs
- **PyMuPDF Integration**: Fast PDF processing with fallback support
- **Markdown Extraction**: Advanced PDF to markdown conversion with multiprocessing for better structure preservation
- **TikToken Chunking**: Token-aware text chunking for better accuracy
- **Vector Search**: Pinecone-powered semantic search
- **LLM Integration**: Google Gemini for intelligent responses
- **Relevance Filtering**: Pre-filters irrelevant queries to save costs
- **Concurrent Processing**: Handles multiple questions in parallel

## API Endpoints

### POST `/api/v1/hackrx/run`

Process insurance policy documents and answer questions.

**Request Body:**
```json
{
  "documents": "https://example.com/policy.pdf",
  "questions": [
    "What is covered under this policy?",
    "What are the exclusions?"
  ]
}
```

**Response:**
```json
{
  "answers": [
    "This policy covers medical expenses up to ₹5 lakhs (Page 3, Line 15)...",
    "Exclusions include pre-existing conditions (Page 8, Line 22)..."
  ]
}
```

### GET `/health`

Health check endpoint for monitoring.

## Authentication

All API endpoints require Bearer token authentication:

```
Authorization: Bearer YOUR_API_TOKEN
```

## Environment Variables

Required environment variables:

- `GEMINI_API_KEY`: Google Gemini API key
- `PINECONE_API_KEY`: Pinecone API key
- `PINECONE_INDEX_NAME`: Pinecone index name
- `API_TOKEN`: Bearer token for authentication

Optional configuration:

- `USE_MARKDOWN_EXTRACTION`: Enable markdown extraction from PDFs (default: true)

## Usage

1. Set up your environment variables
2. Deploy to Hugging Face Spaces
3. Make API calls with proper authentication

## Response Format

- **Length**: 10-100 words (flexible for complex queries)
- **Language**: Simple, easy-to-understand
- **Citations**: Inline format like (Page 5, Line 12)
- **Decisions**: Includes APPROVED/REJECTED/NEEDS REVIEW for claim queries

## Supported Document Types

- PDF files
- Microsoft Word documents (.docx)
- Plain text files (.txt)
- Email files (.eml)

## Performance

- **Latency**: < 30 seconds for document processing
- **Concurrency**: Supports multiple parallel requests
- **Caching**: Document-level caching for faster repeated queries



Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference
