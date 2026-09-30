from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import voyageai

from app.chunking import Chunk, PdfCorpus
from app.config import get_settings
from app.visuals import PdfChunkRenderer


@lru_cache
def get_voyage_client() -> voyageai.Client:
    settings = get_settings()
    settings.validate()
    return voyageai.Client(api_key=settings.voyage_api_key)


def embed_lite_documents(
    chunks: list[Chunk],
    batch_size: int = 32,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    settings = get_settings()
    embeddings: list[list[float]] = []
    for offset in range(0, len(chunks), batch_size):
        batch = chunks[offset : offset + batch_size]
        response = get_voyage_client().embed(
            [chunk.embedding_text for chunk in batch],
            model=settings.voyage_lite_model,
            input_type="document",
            output_dimension=settings.voyage_dimensions,
        )
        embeddings.extend(response.embeddings)
        if progress_callback:
            progress_callback(min(offset + len(batch), len(chunks)), len(chunks))
    return embeddings


def embed_context_documents(
    corpus: PdfCorpus,
    group_batch_size: int = 8,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    """Contextualize ordered chunks page-by-page and preserve canonical chunk alignment."""
    settings = get_settings()
    page_indexes: dict[int, list[int]] = {}
    for index, chunk in enumerate(corpus.chunks):
        page_indexes.setdefault(chunk.page, []).append(index)

    groups: list[list[str]] = []
    canonical_indexes: list[list[int]] = []
    for page, indexes in sorted(page_indexes.items()):
        previous_tail = corpus.page_text.get(page - 1, "")[-900:]
        next_opening = corpus.page_text.get(page + 1, "")[:900]
        groups.append(
            [
                f"Document: {corpus.title}\nPrevious page context: {previous_tail or '[none]'}",
                *[corpus.chunks[index].embedding_text for index in indexes],
                f"Next page context: {next_opening or '[none]'}",
            ]
        )
        canonical_indexes.append(indexes)

    aligned: list[list[float] | None] = [None] * len(corpus.chunks)
    for offset in range(0, len(groups), group_batch_size):
        batch_groups = groups[offset : offset + group_batch_size]
        response = get_voyage_client().contextualized_embed(
            batch_groups,
            model=settings.voyage_context_model,
            input_type="document",
            output_dimension=settings.voyage_dimensions,
        )
        ordered = sorted(response.results, key=lambda item: item.index)
        for indexes, result in zip(
            canonical_indexes[offset : offset + group_batch_size], ordered
        ):
            vectors = result.embeddings[1 : 1 + len(indexes)]
            if len(vectors) != len(indexes):
                raise RuntimeError("Voyage Context returned an unexpected embedding shape")
            for chunk_index, vector in zip(indexes, vectors):
                aligned[chunk_index] = vector
        if progress_callback:
            progress_callback(min(offset + len(batch_groups), len(groups)), len(groups))

    if any(vector is None for vector in aligned):
        raise RuntimeError("Voyage Context did not return every chunk embedding")
    return [vector for vector in aligned if vector is not None]


def embed_multimodal_documents(
    pdf_path: Path,
    chunks: list[Chunk],
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[list[list[float]], list[dict]]:
    settings = get_settings()
    batch_size = max(settings.multimodal_batch_size, 1)
    embeddings: list[list[float]] = []
    visual_metadata: list[dict] = []
    with PdfChunkRenderer(pdf_path, dpi=settings.multimodal_render_dpi) as renderer:
        for offset in range(0, len(chunks), batch_size):
            batch = chunks[offset : offset + batch_size]
            visuals = [renderer.render(chunk) for chunk in batch]
            response = get_voyage_client().multimodal_embed(
                [
                    [chunk.embedding_text, visual.image]
                    for chunk, visual in zip(batch, visuals)
                ],
                model=settings.voyage_multimodal_model,
                input_type="document",
            )
            embeddings.extend(response.embeddings)
            visual_metadata.extend(
                {
                    "kind": visual.kind,
                    "sha256": visual.sha256,
                    "width": visual.width,
                    "height": visual.height,
                    "render_dpi": settings.multimodal_render_dpi,
                    "bbox_pdf_points": (
                        list(visual.bbox_pdf_points)
                        if visual.bbox_pdf_points is not None
                        else None
                    ),
                }
                for visual in visuals
            )
            if progress_callback:
                progress_callback(min(offset + len(batch), len(chunks)), len(chunks))
    return embeddings, visual_metadata


def embed_query(query: str, lane_key: str) -> list[float]:
    settings = get_settings()
    if lane_key == "voyage_4_lite":
        response = get_voyage_client().embed(
            [query],
            model=settings.voyage_lite_model,
            input_type="query",
            output_dimension=settings.voyage_dimensions,
        )
        return response.embeddings[0]
    if lane_key == "voyage_context_4":
        response = get_voyage_client().contextualized_embed(
            [[query]],
            model=settings.voyage_context_model,
            input_type="query",
            output_dimension=settings.voyage_dimensions,
        )
        return sorted(response.results, key=lambda item: item.index)[0].embeddings[0]
    if lane_key == "voyage_multimodal_3_5":
        response = get_voyage_client().multimodal_embed(
            [[query]],
            model=settings.voyage_multimodal_model,
            input_type="query",
        )
        return response.embeddings[0]
    raise ValueError(f"Unsupported lane: {lane_key}")


def rerank_documents(query: str, documents: list[str], top_k: int):
    if not documents:
        return []
    return get_voyage_client().rerank(
        query=query,
        documents=documents,
        model=get_settings().voyage_rerank_model,
        top_k=top_k,
    ).results


def close_voyage_client() -> None:
    get_voyage_client.cache_clear()
