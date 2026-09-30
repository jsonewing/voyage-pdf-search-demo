from __future__ import annotations

from collections.abc import Callable
import time

from pymongo.operations import SearchIndexModel

from app.config import get_settings


def lexical_definition() -> dict:
    return {
        "storedSource": {
            "include": [
                "source_id",
                "filename",
                "page",
                "chunk_index",
                "chunk_kind",
                "section_title",
                "text",
            ]
        },
        "mappings": {
            "dynamic": False,
            "fields": {
                "lexical_text": {"type": "string", "analyzer": "lucene.standard"},
                "text": {"type": "string", "analyzer": "lucene.standard"},
                "section_title": {"type": "string", "analyzer": "lucene.standard"},
                "source_id": {"type": "token"},
                "filename": {"type": "token", "normalizer": "lowercase"},
                "page": {"type": "number"},
                "chunk_index": {"type": "number"},
                "chunk_kind": {"type": "token"},
            },
        },
    }


def vector_definition(path: str) -> dict:
    settings = get_settings()
    return {
        "fields": [
            {
                "type": "vector",
                "path": path,
                "numDimensions": settings.voyage_dimensions,
                "similarity": "cosine",
            },
            {"type": "filter", "path": "source_id"},
            {"type": "filter", "path": "chunk_kind"},
        ]
    }


def required_indexes(lane_keys: list[str] | tuple[str, ...] | None = None) -> list[SearchIndexModel]:
    settings = get_settings()
    selected = set(lane_keys or (lane.key for lane in settings.lanes))
    return [
        SearchIndexModel(
            name=settings.lexical_index_name,
            definition=lexical_definition(),
        ),
        *[
            SearchIndexModel(
                name=lane.index_name,
                definition=vector_definition(lane.field),
                type="vectorSearch",
            )
            for lane in settings.lanes
            if lane.key in selected
        ],
    ]


def ensure_indexes(
    collection, lane_keys: list[str] | tuple[str, ...] | None = None
) -> list[str]:
    existing = {
        index["name"]: index for index in collection.list_search_indexes()
    }
    requested: list[str] = []
    for index in required_indexes(lane_keys):
        name = index.document["name"]
        current = existing.get(name)
        if current is None:
            collection.create_search_index(index)
            requested.append(f"{name} created")
            continue

        expected_type = index.document.get("type", "search")
        current_type = current.get("type", "search")
        if current_type != expected_type:
            raise RuntimeError(
                f"Atlas Search index '{name}' has type '{current_type}', expected "
                f"'{expected_type}'. Use a new index name or remove the conflicting index."
            )

        current_definition = current.get("latestDefinition")
        if current_definition is None:
            raise RuntimeError(
                f"Atlas Search index '{name}' did not report its definition; "
                "its configuration cannot be validated safely."
            )

        expected_definition = index.document["definition"]
        if current_definition != expected_definition:
            collection.update_search_index(name, expected_definition)
            requested.append(f"{name} updated")
        else:
            requested.append(f"{name} reused")
    return requested


def wait_for_indexes(
    collection,
    lane_keys: list[str] | tuple[str, ...] | None = None,
    timeout_seconds: int | None = None,
    progress_callback: Callable[[dict[str, str]], None] | None = None,
) -> None:
    settings = get_settings()
    timeout_seconds = timeout_seconds or settings.index_ready_timeout_seconds
    selected = set(lane_keys or (lane.key for lane in settings.lanes))
    required = {settings.lexical_index_name} | {
        lane.index_name for lane in settings.lanes if lane.key in selected
    }
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        states = {index["name"]: index for index in collection.list_search_indexes()}
        if progress_callback:
            progress_callback(
                {
                    name: states.get(name, {}).get("status", "PENDING")
                    for name in sorted(required)
                }
            )
        failed = [
            name
            for name in required
            if states.get(name, {}).get("status") in {"FAILED", "DELETING"}
        ]
        if failed:
            raise RuntimeError(f"Atlas Search index failed: {', '.join(sorted(failed))}")
        if all(
            states.get(name, {}).get("status") == "READY"
            and states.get(name, {}).get("queryable") is True
            for name in required
        ):
            return
        time.sleep(3)
    raise TimeoutError(f"Atlas Search indexes were not ready after {timeout_seconds} seconds")


def wait_for_source_visibility(
    collection,
    source_id: str,
    sample: dict,
    lane_keys: list[str] | tuple[str, ...] | None = None,
    progress_callback: Callable[[int], None] | None = None,
) -> None:
    settings = get_settings()
    selected = set(lane_keys or (lane.key for lane in settings.lanes))
    deadline = time.monotonic() + settings.index_sync_timeout_seconds
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        if progress_callback:
            progress_callback(attempt)
        try:
            lexical = list(
                collection.aggregate(
                    [
                        {
                            "$search": {
                                "index": settings.lexical_index_name,
                                "compound": {
                                    "must": [{"exists": {"path": "text"}}],
                                    "filter": [
                                        {"equals": {"path": "source_id", "value": source_id}}
                                    ],
                                },
                            }
                        },
                        {"$limit": 1},
                    ]
                )
            )
            vectors_visible = True
            for lane in settings.lanes:
                if lane.key not in selected:
                    continue
                result = list(
                    collection.aggregate(
                        [
                            {
                                "$vectorSearch": {
                                    "index": lane.index_name,
                                    "path": lane.field,
                                    "queryVector": sample[lane.field],
                                    "exact": True,
                                    "filter": {"source_id": source_id},
                                    "limit": 1,
                                }
                            }
                        ]
                    )
                )
                vectors_visible = vectors_visible and bool(result)
            if lexical and vectors_visible:
                return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    raise TimeoutError(
        "Indexes are ready, but the uploaded chunks did not become queryable before the sync timeout."
    )
