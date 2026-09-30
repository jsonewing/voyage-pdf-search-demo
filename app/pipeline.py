from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pymongo import ReplaceOne

from app.chunking import extract_pdf, stable_chunk_id
from app.config import get_settings
from app.db import get_collection
from app.embeddings import (
    embed_context_documents,
    embed_lite_documents,
    embed_multimodal_documents,
)
from app.indexes import ensure_indexes, wait_for_indexes, wait_for_source_visibility
from app.jobs import jobs


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def process_pdf(
    job_id: str,
    pdf_path: Path,
    source_id: str,
    filename: str,
    selected_model_keys: list[str] | tuple[str, ...],
) -> None:
    try:
        settings = get_settings()
        requested_keys = set(selected_model_keys)
        selected = tuple(lane.key for lane in settings.lanes if lane.key in requested_keys)
        if not selected:
            raise ValueError("Select at least one Voyage model")

        jobs.update_step(job_id, "extract", "running", "Extracting page text and tables.", 10)
        corpus = extract_pdf(pdf_path)
        narrative_count = sum(chunk.kind == "narrative" for chunk in corpus.chunks)
        table_count = sum(chunk.kind == "table_row" for chunk in corpus.chunks)
        jobs.update_step(
            job_id,
            "extract",
            "complete",
            f"Created {len(corpus.chunks)} page-aligned chunks.",
            25,
            {
                "pages": corpus.page_count,
                "chunks": len(corpus.chunks),
                "narrative_chunks": narrative_count,
                "table_chunks": table_count,
            },
        )

        vectors_by_lane: dict[str, list[list[float]]] = {}
        visual_metadata: list[dict] | None = None

        if "voyage_4_lite" in selected:
            jobs.update_step(
                job_id, "embed_lite", "running", "Embedding metadata-enriched chunks.", 28
            )
            vectors_by_lane["voyage_4_lite"] = embed_lite_documents(
                corpus.chunks,
                progress_callback=lambda done, total: jobs.update_step(
                    job_id,
                    "embed_lite",
                    "running",
                    f"Voyage 4 Lite embedded {done} of {total} chunks.",
                    28 + round(12 * done / max(total, 1)),
                ),
            )
            jobs.update_step(
                job_id,
                "embed_lite",
                "complete",
                f"Voyage 4 Lite embedded {len(corpus.chunks)} chunks.",
                40,
            )

        if "voyage_context_4" in selected:
            jobs.update_step(
                job_id,
                "embed_context",
                "running",
                "Embedding ordered page groups with native context.",
                42,
            )
            vectors_by_lane["voyage_context_4"] = embed_context_documents(
                corpus,
                progress_callback=lambda done, total: jobs.update_step(
                    job_id,
                    "embed_context",
                    "running",
                    f"Voyage Context 4 embedded {done} of {total} page groups.",
                    42 + round(13 * done / max(total, 1)),
                ),
            )
            jobs.update_step(
                job_id,
                "embed_context",
                "complete",
                f"Voyage Context 4 embedded {len(corpus.chunks)} aligned chunks.",
                55,
            )

        if "voyage_multimodal_3_5" in selected:
            jobs.update_step(
                job_id,
                "embed_multimodal",
                "running",
                "Rendering PDF evidence and creating text-plus-image embeddings.",
                57,
            )
            multimodal_vectors, visual_metadata = embed_multimodal_documents(
                pdf_path,
                corpus.chunks,
                progress_callback=lambda done, total: jobs.update_step(
                    job_id,
                    "embed_multimodal",
                    "running",
                    f"Voyage Multimodal 3.5 embedded {done} of {total} visuals.",
                    57 + round(16 * done / max(total, 1)),
                ),
            )
            vectors_by_lane["voyage_multimodal_3_5"] = multimodal_vectors
            jobs.update_step(
                job_id,
                "embed_multimodal",
                "complete",
                f"Voyage Multimodal 3.5 embedded {len(corpus.chunks)} visuals.",
                73,
            )

        if any(len(vectors_by_lane[key]) != len(corpus.chunks) for key in selected):
            raise RuntimeError("Embedding output did not align with the canonical chunks")
        if visual_metadata is not None and len(visual_metadata) != len(corpus.chunks):
            raise RuntimeError("Visual metadata did not align with the canonical chunks")

        jobs.update_step(job_id, "store", "running", "Writing chunk documents to Atlas.", 76)
        collection = get_collection()
        created_at = _now()
        documents = []
        for index, chunk in enumerate(corpus.chunks):
            document = {
                "_id": stable_chunk_id(source_id, chunk),
                "record_type": "chunk",
                "source_id": source_id,
                "filename": filename,
                "document_title": corpus.title,
                "page": chunk.page,
                "chunk_index": chunk.index,
                "chunk_kind": chunk.kind,
                "section_title": chunk.section_title,
                "text": chunk.text,
                "lexical_text": chunk.embedding_text,
                "selected_model_keys": list(selected),
                "models": {key: settings.lane(key).model for key in selected},
                "created_at": created_at,
            }
            for key in selected:
                document[settings.lane(key).field] = vectors_by_lane[key][index]
            if visual_metadata is not None:
                document["visual"] = visual_metadata[index]
            documents.append(document)

        collection.bulk_write(
            [ReplaceOne({"_id": document["_id"]}, document, upsert=True) for document in documents],
            ordered=False,
        )
        collection.delete_many(
            {"source_id": source_id, "_id": {"$nin": [document["_id"] for document in documents]}}
        )
        collection.create_index("source_id")
        jobs.update_step(
            job_id,
            "store",
            "complete",
            f"Stored {len(documents)} chunks in {settings.atlas_db}.{settings.atlas_collection}.",
            82,
        )

        index_count = 1 + len(selected)
        jobs.update_step(
            job_id,
            "indexes",
            "running",
            f"Creating or reusing {index_count} Atlas Search indexes.",
            84,
        )
        requested = ensure_indexes(collection, selected)
        wait_for_indexes(
            collection,
            selected,
            progress_callback=lambda states: jobs.update_step(
                job_id,
                "indexes",
                "running",
                "Atlas index states: "
                + ", ".join(f"{name} {status}" for name, status in states.items()),
                88,
            ),
        )
        jobs.update_step(
            job_id,
            "indexes",
            "complete",
            "; ".join(requested) + ".",
            93,
            {"indexes": requested},
        )

        jobs.update_step(
            job_id, "sync", "running", "Waiting for uploaded chunks to become searchable.", 95
        )
        wait_for_source_visibility(
            collection,
            source_id,
            documents[0],
            selected,
            progress_callback=lambda attempt: jobs.update_step(
                job_id,
                "sync",
                "running",
                f"Checking lexical and vector visibility (attempt {attempt}).",
                97,
            ),
        )
        labels = [settings.lane(key).label for key in selected]
        jobs.update_step(
            job_id,
            "sync",
            "complete",
            "Lexical and selected vector indexes can retrieve this PDF.",
            99,
        )
        jobs.complete(
            job_id,
            {
                "source_id": source_id,
                "filename": filename,
                "pages": corpus.page_count,
                "chunks": len(documents),
                "selected_model_keys": list(selected),
                "selected_models": labels,
            },
        )
    except Exception as exc:  # noqa: BLE001
        jobs.fail(job_id, str(exc))
