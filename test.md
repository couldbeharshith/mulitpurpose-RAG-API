# RAG Pipeline — concise, professional overview

I’m passionate about this hackathon project — below is a crisp, copy-ready overview for your `README.md`.

## Steps

1. **Receive request**  
   FastAPI accepts incoming requests at the configured endpoint.

2. **Fetch document**  
   Download the document from the provided URL if it’s under the size limit (default `1GB`, configurable via `.env`) and not a `.zip` or `.bin`.

3. **Classify document**  
   Classify the file by type and size to determine the processing path.

4. **Direct multimodal handling (fast path)**  
   If the file is an image, or is ≤ `0.5MB` (configurable) and is a `pdf`, `txt`/`eml`, or audio/video, send it directly to Gemini’s multimodal API to answer the query without chunking, embedding, or retrieval — this significantly reduces latency.

5. **Process PDF**  
   Extract text and tables from PDFs using `pymupdf4LLM` and convert output to Markdown. Processing is parallelized by batching pages across worker processes.

6. **Process DOCX**  
   Extract content from `.docx` files using `pymupdf` and convert to Markdown.

7. **Process PPTX**  
   Extract slides and text from `.pptx` via `python-pptx` and apply Tesseract OCR where needed; output is converted to Markdown.

8. **Process XLSX**  
   Parse Excel workbooks with `openpyxl`, exporting each worksheet’s contents to Markdown.

9. **Chunking**  
   Split extracted text into chunks using `tiktoken` with chunk size and overlap controlled via `.env`.

10. **Embed & store**  
    Generate embeddings for each chunk (Llama Embed v2) and store vectors and plain-text chunks in Pinecone.

11. **Relevance filtering (optional)**  
    If enabled in `.env`, compute similarity between the query embedding and chunk embeddings. Mark queries as irrelevant when the top similarity is below the configured threshold (recommended: disable for multilingual tasks). Irrelevant queries are not processed further and return a suitable API response.

12. **Query expansion (multi-query)**  
    Expand each incoming query into three rephrased queries using an LLM (primary: Groq, fallback: Gemini) to improve retrieval recall.

13. **Retrieve & deduplicate**  
    Vector-query Pinecone for the `top_k` results (configurable) for each rephrased query, merge results, and deduplicate candidate chunks.

14. **Rerank**  
    Rerank the deduplicated chunks against the original query (primary: BGE, fallback: Cohere) and select the top `n` chunks (configurable).

15. **Final LLM call**  
    Send the top `n` chunks as context to the final LLM (primary: Gemini, fallback: Groq) using prompt templates in `prompts.json`. Provide a tool/function for the LLM to make external API calls when needed.

16. **Return & store response**  
    Collect the final LLM output, store it, and return the consolidated answer to the API caller.

---

## Notes & operational details

- **Configuration:** Most global settings (size limits, thresholds, `top_k`, `top_n`, model preferences, etc.) are configurable in `.env`.  
- **API key rotation:** We rotate API keys across multiple Gemini, Groq, and Pinecone keys (primary pool, then secondary) to distribute load and avoid free-tier rate limits.  
- **Repo history:** The repo was originally hosted on Hugging Face: `https://huggingface.com/couldbeharshith/insurance-agent`. We migrated to GitHub for convenience; prior commits and the working HF endpoint are still available there.  
- **Live endpoint (Hugging Face Spaces):**  
  `https://couldbeharshith-insurance-agent.hf.space/api/v1/hackrx/run`

---
