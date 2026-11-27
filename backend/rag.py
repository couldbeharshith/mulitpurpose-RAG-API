"""Retrieval and answering for indexed sources."""

import asyncio
import json
import logging
from itertools import zip_longest
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from backend.config import Config
from backend.models import DocumentProcessingResult, RelevantChunk
from backend.services import LLMService, VectorService

logger = logging.getLogger(__name__)

SearchQuery = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
EvidenceQuote = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1800)]


class Evidence(BaseModel):
    passage: int = Field(ge=1)
    quote: EvidenceQuote


class AgentStep(BaseModel):
    action: Literal["answer", "search", "abstain"]
    answer: str = ""
    evidence: list[Evidence] = Field(default_factory=list, max_length=12)
    queries: list[SearchQuery] = Field(default_factory=list, max_length=3)


class Review(BaseModel):
    supported: bool
    queries: list[SearchQuery] = Field(default_factory=list, max_length=3)


NO_EVIDENCE = "I could not find a passage that answers this question. Try a more specific term from the source."


class RagService:
    def __init__(self, vectors: VectorService, llm: LLMService):
        self.vectors = vectors
        self.llm = llm

    async def answer(self, question: str, document: DocumentProcessingResult) -> str:
        candidates = await self._initial_search(question, document)
        if not candidates:
            return NO_EVIDENCE
        if Config.RELEVANCE_CHECK_ENABLED and max(
            candidate.relevance_score for candidate in candidates
        ) < Config.RELEVANCE_THRESHOLD:
            return "This question is not relevant to the provided document content."

        context = await self._select(candidates, question)
        return await self.llm.generate_answer(question, context)

    async def answer_agentic(self, question: str, document: DocumentProcessingResult) -> str:
        results = await self._initial_search(question, document)
        context = await self._select(results, question) if results else []
        for can_search in (True, False):
            step, review = await self._assess(question, context, can_search)
            if review and review.supported:
                return self._with_sources(step, context)

            # Leave the original search in the pool and only search for new queries.
            if not can_search:
                return NO_EVIDENCE
            proposed = review.queries if review else step.queries
            seen = {self._query_key(question), ""}
            queries = []
            for query in proposed:
                key = self._query_key(query)
                if key not in seen:
                    seen.add(key)
                    queries.append(query)
            if not queries:
                return NO_EVIDENCE

            followups = await self._search_followups(queries, document.namespace)
            if not any(followups):
                return NO_EVIDENCE
            merged = self._interleave([results, *followups])
            context = await self._select(merged, question)
            # Retain the best hit for each targeted facet if reranking dropped it.
            context = self._interleave([context, [hits[0] for hits in followups if hits]])

        return NO_EVIDENCE

    async def _assess(
        self, question: str, context: list[RelevantChunk], can_search: bool,
    ) -> tuple[AgentStep, Review | None]:
        payload = {
            "question": question,
            "passages": [{"id": i, "text": hit.chunk.content} for i, hit in enumerate(context, 1)],
        }
        prompt = Config.get_prompt("rag_agent_step", payload=json.dumps(payload, ensure_ascii=False),
                                   can_search=can_search)
        step = AgentStep.model_validate_json(await self.llm.complete_rag_step(prompt), strict=True)
        if step.action != "answer" or not step.answer.strip() or not self._quotes_exist(step.evidence, context):
            return step, None

        payload.update(answer=step.answer, quotations=[item.model_dump() for item in step.evidence])
        prompt = Config.get_prompt("rag_verify", payload=json.dumps(payload, ensure_ascii=False),
                                   can_search=can_search)
        review = Review.model_validate_json(await self.llm.complete_rag_step(prompt), strict=True)
        return step, review

    @staticmethod
    def _quotes_exist(evidence: list[Evidence], context: list[RelevantChunk]) -> bool:
        return bool(evidence) and all(
            item.passage <= len(context)
            and " ".join(item.quote.split()) in " ".join(context[item.passage - 1].chunk.content.split())
            for item in evidence
        )

    @staticmethod
    def _with_sources(step: AgentStep, context: list[RelevantChunk]) -> str:
        references = []
        for number in dict.fromkeys(item.passage for item in step.evidence):
            metadata = context[number - 1].chunk.metadata
            location = f"Passage {metadata.chunk_number or number}"
            if metadata.page_number > 0:
                if metadata.document_type == "pdf":
                    location += f", page {metadata.page_number}"
                elif metadata.document_type == "pptx":
                    location += f", slide {metadata.page_number}"
                elif metadata.document_type == "xlsx":
                    location += f", sheet {metadata.page_number}"
            references.append(f"- {location}")
        return step.answer.strip() + "\n\n**Sources**\n" + "\n".join(references)

    @staticmethod
    def _query_key(query: str) -> str:
        return " ".join(query.casefold().split()).rstrip("?.!")

    async def _search_followups(self, queries: list[str], namespace: str) -> list[list[RelevantChunk]]:
        searches = await asyncio.gather(
            *(self._search(query, namespace) for query in queries), return_exceptions=True,
        )
        results = []
        for search in searches:
            if isinstance(search, BaseException):
                if not isinstance(search, Exception):
                    raise search
                logger.warning("Agentic follow-up search failed: %s", type(search).__name__)
            else:
                results.append(search)
        if not results:
            raise RuntimeError("All agentic follow-up searches failed")
        return results

    @staticmethod
    def _interleave(results: list[list[RelevantChunk]]) -> list[RelevantChunk]:
        unique = {}
        for group in zip_longest(*results):
            for hit in group:
                if hit is not None:
                    unique.setdefault(hit.chunk.content, hit)
        return list(unique.values())

    async def _initial_search(self, question: str, document: DocumentProcessingResult) -> list[RelevantChunk]:
        candidates = await self._search(question, document.namespace)
        if not candidates and not document.cached and document.chunks:
            # Upserts may be visible to namespace stats before search catches up.
            await asyncio.sleep(0.5)
            candidates = await self._search(question, document.namespace)
        return candidates

    async def _search(self, query: str, namespace: str) -> list[RelevantChunk]:
        result = await self.vectors.search_documents(query, namespace)
        return [hit for hit in result.chunks if hit.chunk.content.strip()]

    async def _select(self, candidates: list[RelevantChunk], question: str) -> list[RelevantChunk]:
        if len(candidates) == 1:
            return candidates
        ranked = await self.vectors.rerank_chunks_with_original_query(candidates, question)
        return ranked or candidates[:Config.PINECONE_RERANK_TOP_N]
