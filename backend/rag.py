"""Retrieval and answering for indexed sources."""

import asyncio

from backend.config import Config
from backend.models import DocumentProcessingResult, RelevantChunk
from backend.services import LLMService, VectorService

NO_EVIDENCE = "I could not find a passage that answers this question. Try a more specific term from the source."


class RagService:
    def __init__(self, vectors: VectorService, llm: LLMService):
        self.vectors = vectors
        self.llm = llm

    async def answer(self, question: str, document: DocumentProcessingResult) -> str:
        candidates = await self._search(question, document.namespace)
        if not candidates and not document.cached and document.chunks:
            # Upserts may be visible to namespace stats before search catches up.
            await asyncio.sleep(0.5)
            candidates = await self._search(question, document.namespace)
        if not candidates:
            return NO_EVIDENCE
        if Config.RELEVANCE_CHECK_ENABLED and max(
            candidate.relevance_score for candidate in candidates
        ) < Config.RELEVANCE_THRESHOLD:
            return "This question is not relevant to the provided document content."

        context = await self._select(candidates, question)
        return await self.llm.generate_answer(question, context)

    async def _search(self, query: str, namespace: str) -> list[RelevantChunk]:
        result = await self.vectors.search_documents(query, namespace)
        return [hit for hit in result.chunks if hit.chunk.content.strip()]

    async def _select(self, candidates: list[RelevantChunk], question: str) -> list[RelevantChunk]:
        if len(candidates) == 1:
            return candidates
        ranked = await self.vectors.rerank_chunks_with_original_query(candidates, question)
        return ranked or candidates[:Config.PINECONE_RERANK_TOP_N]
