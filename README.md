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

## Supported Document Types

- PDF files
- Microsoft Word documents (.docx)
- Plain text files (.txt)
- Email files (.eml)

# Steps of processing (processing pipeline)
- Step 1
- Step 2
will be updated.

# Note to the evaluators / testers
1. most of our global settings can be configured in the .env file.
2. we use multiple gemini, groq, pinecone and groq API keys by cycling through the primary service's keys one by one and using the secondary service's keys if the primary fails. we do this to distribute the workload of the API calls among multiple API providers and to avoid hitting the free tier rate limits.
3. the repo was original hosted on hugging face @ https://huggingface.com/couldbeharshith/insurance-agent but we have moved it to github for your convinience. all previous commits can be found on the hugging face repo along with the working endpoint URL that is hosted on hugging face spaces below

our API endpoint URL - https://couldbeharshith-insurance-agent.hf.space/api/v1/hackrx/run

Check out the configuration reference at https://huggingface.co/docs/hub/spaces-config-reference
