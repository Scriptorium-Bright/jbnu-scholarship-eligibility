from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

from app.ai.providers import EmbeddingProvider, EmbeddingProviderError, build_embedding_provider
from app.core.config import Settings, get_settings
from app.db import session_scope
from app.repositories import ScholarshipRagChunkRepository
from app.schemas import RagRetrievalCandidate, RagRetrievalResult, RagRetrievedChunk


class ScholarshipRagRetrievalService:
    """query 시점 hybrid retrieval, dedup, diversity selection을 담당하는 서비스입니다."""

    """
    diversity selection은 단순히 점수 상위 근거만 뽑는 것이 아니라,
    같은 문서에 과하게 몰리지 않도록 후보를 분산시켜 citation 다양성을 확보하는 전략입니다.
    """

    def __init__(
        self,
        *,
        embedding_provider: Optional[EmbeddingProvider] = None,
        settings: Optional[Settings] = None,
        keyword_weight: float = 1.0,
        vector_weight: float = 1.0,
        rrf_k: int = 20,
        max_chunks_per_document: int = 2,
    ):
        """query embedding 공급자와 hybrid fusion 파라미터를 초기화합니다."""

        self._settings = settings or get_settings()
        self._embedding_provider = embedding_provider or build_embedding_provider(self._settings)
        self._keyword_weight = max(float(keyword_weight), 0.0)
        self._vector_weight = max(float(vector_weight), 0.0)
        self._rrf_k = max(int(rrf_k), 1)
        self._max_chunks_per_document = max(int(max_chunks_per_document), 1)

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 5,
        keyword_limit: int = 10,
        vector_limit: int = 10,
    ) -> RagRetrievalResult:
        """질의에 대한 hybrid top-k 근거 chunk를 반환합니다."""

        normalized_query = self._normalize_query(query)
        if not normalized_query:
            return self._build_no_evidence_result(
                query=query,
                retrieval_mode="no_evidence",
                failure_reason="empty_query",
            )

        resolved_limit = max(int(limit), 1)
        keyword_candidates: List[RagRetrievalCandidate]
        vector_candidates: List[RagRetrievalCandidate]
        keyword_fallback_used = False
        failure_reason: Optional[str] = None

        with session_scope() as session:
            repository = ScholarshipRagChunkRepository(session)
            keyword_candidates = repository.list_keyword_candidates(
                normalized_query,
                limit=max(resolved_limit, int(keyword_limit)),
            )

            vector_candidates = []
            try:
                query_embedding = self._embedding_provider.embed_query(text=normalized_query)
            except EmbeddingProviderError as exc:
                keyword_fallback_used = True
                failure_reason = type(exc).__name__
            else:
                vector_candidates = repository.list_vector_candidates(
                    query_embedding,
                    limit=max(resolved_limit, int(vector_limit)),
                )

        merged_candidates = self._merge_candidate_scores(
            keyword_candidates=keyword_candidates,
            vector_candidates=vector_candidates,
        )
        selected_chunks = self._deduplicate_candidates(
            merged_candidates,
            limit=resolved_limit,
        )

        retrieval_mode = self._resolve_retrieval_mode(
            keyword_candidates=keyword_candidates,
            vector_candidates=vector_candidates,
            keyword_fallback_used=keyword_fallback_used,
        )
        if not selected_chunks:
            return self._build_no_evidence_result(
                query=query,
                retrieval_mode=retrieval_mode,
                keyword_fallback_used=keyword_fallback_used,
                failure_reason=failure_reason,
            )

        return RagRetrievalResult(
            query=query,
            count=len(selected_chunks),
            has_evidence=True,
            retrieval_mode=retrieval_mode,
            keyword_fallback_used=keyword_fallback_used,
            failure_reason=failure_reason,
            chunks=selected_chunks,
        )

    def _merge_candidate_scores(
        self,
        *,
        keyword_candidates: Sequence[RagRetrievalCandidate],
        vector_candidates: Sequence[RagRetrievalCandidate],
    ) -> List[RagRetrievedChunk]:
        """rank 기반 weighted fusion으로 retrieval 후보를 합칩니다."""

        merged: Dict[Tuple[int, str], Dict[str, object]] = {}

        self._accumulate_candidates(
            merged=merged,
            candidates=keyword_candidates,
            retrieval_kind="keyword",
            weight=self._keyword_weight,
        )
        self._accumulate_candidates(
            merged=merged,
            candidates=vector_candidates,
            retrieval_kind="vector",
            weight=self._vector_weight,
        )

        results = [
            RagRetrievedChunk(
                chunk_id=int(values["chunk_id"]),
                chunk_key=str(values["chunk_key"]),
                notice_id=int(values["notice_id"]),
                document_id=int(values["document_id"]),
                rule_id=values["rule_id"],
                block_id=str(values["block_id"]),
                chunk_text=str(values["chunk_text"]),
                scholarship_name=values["scholarship_name"],
                source_label=str(values["source_label"]),
                document_kind=values["document_kind"],
                page_number=values["page_number"],
                anchor_keys=sorted(str(key) for key in values["anchor_keys"]),
                metadata=dict(values["metadata"]),
                keyword_score=round(float(values["keyword_score"]), 6),
                vector_score=round(float(values["vector_score"]), 6),
                final_score=round(float(values["final_score"]), 6),
                matched_retrieval_kinds=sorted(str(kind) for kind in values["retrieval_kinds"]),
            )
            for values in merged.values()
        ]
        return sorted(results, key=self._retrieved_chunk_sort_key)

    def _accumulate_candidates(
        self,
        *,
        merged: Dict[Tuple[int, str], Dict[str, object]],
        candidates: Sequence[RagRetrievalCandidate],
        retrieval_kind: str,
        weight: float,
    ) -> None:
        """단일 retrieval source 결과를 누적해 fused candidate를 만듭니다."""

        if weight <= 0:
            return

        score_field = "{0}_score".format(retrieval_kind)
        for rank, candidate in enumerate(candidates, start=1):
            key = (candidate.document_id, candidate.block_id)
            entry = merged.setdefault(
                key,
                {
                    "chunk_id": candidate.chunk_id,
                    "chunk_key": candidate.chunk_key,
                    "notice_id": candidate.notice_id,
                    "document_id": candidate.document_id,
                    "rule_id": candidate.rule_id,
                    "block_id": candidate.block_id,
                    "chunk_text": candidate.chunk_text,
                    "scholarship_name": candidate.scholarship_name,
                    "source_label": candidate.source_label,
                    "document_kind": candidate.document_kind,
                    "page_number": candidate.page_number,
                    "anchor_keys": set(candidate.anchor_keys),
                    "metadata": dict(candidate.metadata),
                    "keyword_score": 0.0,
                    "vector_score": 0.0,
                    "final_score": 0.0,
                    "retrieval_kinds": set(),
                },
            )

            if candidate.rule_id is not None and entry["rule_id"] is None:
                entry["rule_id"] = candidate.rule_id
                entry["chunk_id"] = candidate.chunk_id
                entry["chunk_key"] = candidate.chunk_key
                entry["scholarship_name"] = candidate.scholarship_name
            if candidate.scholarship_name and not entry["scholarship_name"]:
                entry["scholarship_name"] = candidate.scholarship_name
            if candidate.page_number is not None and entry["page_number"] is None:
                entry["page_number"] = candidate.page_number

            entry["anchor_keys"].update(candidate.anchor_keys)
            self._merge_metadata(entry["metadata"], candidate.metadata)
            entry["retrieval_kinds"].add(retrieval_kind)
            entry[score_field] = max(float(entry[score_field]), float(candidate.score))
            entry["final_score"] = float(entry["final_score"]) + (
                weight / float(self._rrf_k + rank)
            )

    def _deduplicate_candidates(
        self,
        candidates: Sequence[RagRetrievedChunk],
        *,
        limit: int,
    ) -> List[RagRetrievedChunk]:
        """문서 다양성을 우선 적용한 뒤 부족하면 overflow를 채워 top-k를 확정합니다."""

        selected: List[RagRetrievedChunk] = []
        overflow: List[RagRetrievedChunk] = []
        counts_by_document = defaultdict(int)

        for candidate in candidates:
            if counts_by_document[candidate.document_id] < self._max_chunks_per_document:
                selected.append(candidate)
                counts_by_document[candidate.document_id] += 1
            else:
                overflow.append(candidate)
            if len(selected) >= limit:
                return selected[:limit]

        for candidate in overflow:
            selected.append(candidate)
            if len(selected) >= limit:
                break

        return selected[:limit]

    def _build_no_evidence_result(
        self,
        *,
        query: str,
        retrieval_mode: str,
        keyword_fallback_used: bool = False,
        failure_reason: Optional[str] = None,
    ) -> RagRetrievalResult:
        """generation 단계가 안전하게 거절할 수 있는 no-evidence 결과를 만듭니다."""

        return RagRetrievalResult(
            query=query,
            count=0,
            has_evidence=False,
            retrieval_mode=retrieval_mode,
            keyword_fallback_used=keyword_fallback_used,
            failure_reason=failure_reason,
            chunks=[],
        )

    def _resolve_retrieval_mode(
        self,
        *,
        keyword_candidates: Sequence[RagRetrievalCandidate],
        vector_candidates: Sequence[RagRetrievalCandidate],
        keyword_fallback_used: bool,
    ) -> str:
        """실행된 retrieval 경로를 읽기 쉬운 mode 문자열로 반환합니다."""

        if keyword_fallback_used:
            return "keyword_fallback"
        if keyword_candidates and vector_candidates:
            return "hybrid"
        if vector_candidates:
            return "vector_only"
        if keyword_candidates:
            return "keyword_only"
        return "no_evidence"

    def _normalize_query(self, query: str) -> str:
        """빈 공백과 줄바꿈을 정리한 query 비교 문자열을 반환합니다."""

        return " ".join(str(query).strip().split())

    def _merge_metadata(self, target: Dict[str, object], incoming: Dict[str, object]) -> None:
        """후보가 합쳐질 때 citation metadata를 보수적으로 병합합니다."""

        for key, value in incoming.items():
            if key not in target:
                target[key] = value

    def _retrieved_chunk_sort_key(self, chunk: RagRetrievedChunk):
        """fusion 결과를 score 우선으로 안정 정렬합니다."""

        return (-chunk.final_score, -max(chunk.keyword_score, chunk.vector_score), chunk.chunk_id)
