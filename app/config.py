from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class ModelLane:
    key: str
    label: str
    model: str
    field: str
    index_name: str
    representation: str
    provider: str


class Settings:
    def __init__(self) -> None:
        self.atlas_uri = os.getenv("ATLAS_URI", "")
        self.atlas_db = os.getenv("ATLAS_DB", "voyage_pdf_live_demo")
        self.atlas_collection = os.getenv("ATLAS_COLLECTION", "pdf_chunks")
        self.voyage_api_key = os.getenv("VOYAGE_API_KEY", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "") or os.getenv(
            "GROVE_API_KEY", ""
        )
        self.openai_base_url = os.getenv(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        ).rstrip("/")
        self.openai_api_mode = os.getenv("OPENAI_API_MODE", "responses")
        self.openai_rag_model = os.getenv("OPENAI_RAG_MODEL", "gpt-5")
        self.openai_rag_max_output_tokens = int(
            os.getenv("OPENAI_RAG_MAX_OUTPUT_TOKENS", "4096")
        )

        self.voyage_lite_model = os.getenv("VOYAGE_LITE_MODEL", "voyage-4-lite")
        self.voyage_context_model = os.getenv("VOYAGE_CONTEXT_MODEL", "voyage-context-4")
        self.voyage_multimodal_model = os.getenv(
            "VOYAGE_MULTIMODAL_MODEL", "voyage-multimodal-3.5"
        )
        self.voyage_rerank_model = os.getenv("VOYAGE_RERANK_MODEL", "rerank-2.5")
        self.voyage_dimensions = int(os.getenv("VOYAGE_DIMENSIONS", "1024"))
        self.multimodal_render_dpi = int(os.getenv("MULTIMODAL_RENDER_DPI", "120"))
        self.multimodal_batch_size = int(os.getenv("MULTIMODAL_BATCH_SIZE", "8"))

        self.lexical_index_name = os.getenv("LEXICAL_INDEX_NAME", "pdf_lexical_v1")
        self.lite_vector_index_name = os.getenv(
            "LITE_VECTOR_INDEX_NAME", "pdf_vector_voyage_4_lite_v1"
        )
        self.context_vector_index_name = os.getenv(
            "CONTEXT_VECTOR_INDEX_NAME", "pdf_vector_voyage_context_4_v1"
        )
        self.multimodal_vector_index_name = os.getenv(
            "MULTIMODAL_VECTOR_INDEX_NAME", "pdf_vector_voyage_multimodal_3_5_v1"
        )

        self.hybrid_vector_weight = float(os.getenv("HYBRID_VECTOR_WEIGHT", "0.65"))
        self.hybrid_lexical_weight = float(os.getenv("HYBRID_LEXICAL_WEIGHT", "0.35"))
        self.upload_max_mb = int(os.getenv("UPLOAD_MAX_MB", "50"))
        self.index_ready_timeout_seconds = int(
            os.getenv("INDEX_READY_TIMEOUT_SECONDS", "900")
        )
        self.index_sync_timeout_seconds = int(os.getenv("INDEX_SYNC_TIMEOUT_SECONDS", "180"))
        self.upload_dir = ROOT / "uploads"

    @property
    def lanes(self) -> tuple[ModelLane, ...]:
        return (
            ModelLane(
                key="voyage_4_lite",
                label="Voyage 4 Lite",
                model=self.voyage_lite_model,
                field="embedding_voyage_4_lite",
                index_name=self.lite_vector_index_name,
                representation="Metadata-enriched page and table chunks",
                provider="text",
            ),
            ModelLane(
                key="voyage_context_4",
                label="Voyage Context 4",
                model=self.voyage_context_model,
                field="embedding_voyage_context_4",
                index_name=self.context_vector_index_name,
                representation="Native contextualized page groups",
                provider="context",
            ),
            ModelLane(
                key="voyage_multimodal_3_5",
                label="Voyage Multimodal 3.5",
                model=self.voyage_multimodal_model,
                field="embedding_voyage_multimodal_3_5",
                index_name=self.multimodal_vector_index_name,
                representation="Chunk text plus rendered page or table-row image",
                provider="multimodal",
            ),
        )

    def lane(self, key: str) -> ModelLane:
        for lane in self.lanes:
            if lane.key == key:
                return lane
        raise ValueError(f"Unknown model lane: {key}")

    def validate(self) -> None:
        missing = []
        if not self.atlas_uri:
            missing.append("ATLAS_URI")
        if not self.voyage_api_key:
            missing.append("VOYAGE_API_KEY")
        if missing:
            raise RuntimeError(f"Missing required configuration: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reload_settings(overrides: dict[str, str] | None = None) -> Settings:
    if overrides:
        os.environ.update(overrides)
    else:
        load_dotenv(ROOT / ".env", override=True)
    get_settings.cache_clear()
    return get_settings()
