from __future__ import annotations

from dataclasses import dataclass

from app.config import ROOT


@dataclass(frozen=True)
class EnablementNote:
    title: str
    anchor: str
    detail: str


@dataclass(frozen=True)
class EnablementModule:
    key: str
    label: str
    path: str
    description: str
    notes: tuple[EnablementNote, ...]


MODULES = (
    EnablementModule(
        key="configuration",
        label="Configuration",
        path="app/config.py",
        description=(
            "Maps environment variables to retrieval and generation models, vector "
            "fields, Atlas index names, weights, and limits without exposing values."
        ),
        notes=(
            EnablementNote(
                "Settings",
                "class Settings:",
                "Keeps deployment-specific values in environment variables, never in code.",
            ),
            EnablementNote(
                "Model lanes",
                "def lanes(self)",
                "Binds each model to its stored vector field and dedicated Atlas index.",
            ),
            EnablementNote(
                "Validation",
                "def validate(self)",
                "Fails before ingestion when required Atlas or Voyage settings are missing.",
            ),
        ),
    ),
    EnablementModule(
        key="database",
        label="Atlas client",
        path="app/db.py",
        description=(
            "Creates one process-wide MongoDB client and provides the collection used "
            "by ingestion, indexing, and retrieval."
        ),
        notes=(
            EnablementNote(
                "Shared client",
                "def get_client()",
                "Caches one MongoClient so requests reuse the driver's connection pool.",
            ),
            EnablementNote(
                "Collection boundary",
                "def get_collection()",
                "Centralizes the configured database and collection for every pipeline stage.",
            ),
            EnablementNote(
                "Lifecycle cleanup",
                "def close_client()",
                "Closes the pooled client during application shutdown.",
            ),
        ),
    ),
    EnablementModule(
        key="setup",
        label="Local setup",
        path="app/setup.py",
        description=(
            "Validates customer-owned Atlas, Voyage, and optional OpenAI credentials, "
            "stores them locally, and refreshes the running clients."
        ),
        notes=(
            EnablementNote(
                "Redacted status",
                "def setup_summary()",
                "Reports readiness and the Atlas host without returning either saved secret.",
            ),
            EnablementNote(
                "Bounded validation",
                "def _validate_atlas(",
                "Uses a temporary client with bounded setup timeouts, then closes it.",
            ),
            EnablementNote(
                "Private persistence",
                "def _persist_env(",
                "Atomically replaces .env and restricts it to owner read/write permissions.",
            ),
            EnablementNote(
                "Runtime refresh",
                "def configure_local(",
                "Validates before saving, clears all cached service clients, and reloads configuration.",
            ),
        ),
    ),
    EnablementModule(
        key="chunking",
        label="Chunking",
        path="app/chunking.py",
        description=(
            "Extracts narrative text and tables, preserves table-row geometry, and "
            "creates page-aligned canonical chunks with stable metadata."
        ),
        notes=(
            EnablementNote(
                "Natural boundaries",
                "def split_text(",
                "Targets 1,600 characters with 220-character overlap and sentence-aware splits.",
            ),
            EnablementNote(
                "Table rows",
                "def table_row_texts(",
                "Creates one semantic row per chunk with header labels and its PDF bounding box.",
            ),
            EnablementNote(
                "Canonical corpus",
                "def extract_pdf(",
                "Separates tables from narrative text to avoid duplicate evidence and preserves pages.",
            ),
        ),
    ),
    EnablementModule(
        key="visuals",
        label="PDF visuals",
        path="app/visuals.py",
        description=(
            "Renders full pages for narrative chunks and focused table-row crops for "
            "the multimodal embedding lane."
        ),
        notes=(
            EnablementNote(
                "Page cache",
                "def _page_image(",
                "Renders each page once at the configured DPI and keeps a bounded LRU cache.",
            ),
            EnablementNote(
                "Focused visuals",
                "def render(self, chunk",
                "Uses full pages for narrative and padded row crops for table evidence.",
            ),
            EnablementNote(
                "Visual provenance",
                "def _image_sha256(",
                "Stores a visual fingerprint and dimensions; raw rendered images are not persisted.",
            ),
        ),
    ),
    EnablementModule(
        key="embeddings",
        label="Embeddings",
        path="app/embeddings.py",
        description=(
            "Calls Voyage 4 Lite, Voyage Context 4, and Voyage Multimodal 3.5 while "
            "keeping every vector aligned to its canonical chunk."
        ),
        notes=(
            EnablementNote(
                "Lite batches",
                "def embed_lite_documents(",
                "Embeds metadata-enriched chunks in batches with input_type='document'.",
            ),
            EnablementNote(
                "Native context",
                "def embed_context_documents(",
                "Sends ordered page groups and maps returned vectors back to canonical chunks.",
            ),
            EnablementNote(
                "Text plus image",
                "def embed_multimodal_documents(",
                "Pairs each chunk's text with its rendered evidence for multimodal embedding.",
            ),
            EnablementNote(
                "Query vectors",
                "def embed_query(",
                "Uses input_type='query' and the same selected model family at retrieval time.",
            ),
        ),
    ),
    EnablementModule(
        key="load",
        label="Atlas load",
        path="app/pipeline.py",
        description=(
            "Coordinates ingestion, writes selected model vectors with bulk upserts, "
            "and verifies that the source is queryable."
        ),
        notes=(
            EnablementNote(
                "Selected lanes",
                "selected = tuple(",
                "Runs and stores only the model pipelines chosen during upload.",
            ),
            EnablementNote(
                "Aligned document",
                'document = {',
                "Stores canonical text, metadata, selected vectors, and optional visual provenance together.",
            ),
            EnablementNote(
                "Idempotent load",
                "collection.bulk_write(",
                "Uses stable IDs and ReplaceOne upserts so reprocessing replaces the same chunks.",
            ),
            EnablementNote(
                "Retrieval readiness",
                "wait_for_source_visibility(",
                "Finishes only after lexical and every selected vector lane can retrieve the source.",
            ),
        ),
    ),
    EnablementModule(
        key="indexes",
        label="Atlas indexes",
        path="app/indexes.py",
        description=(
            "Defines explicit Atlas Search and Vector Search mappings and waits for "
            "each selected index to become ready."
        ),
        notes=(
            EnablementNote(
                "Lexical mapping",
                "def lexical_definition()",
                "Indexes only searchable fields and stores the evidence fields returned to the UI.",
            ),
            EnablementNote(
                "Vector mapping",
                "def vector_definition(",
                "Uses cosine similarity, fixed dimensions, and source/type filter fields.",
            ),
            EnablementNote(
                "Per-lane indexes",
                "def required_indexes(",
                "Creates the shared lexical index plus one vector index per selected model.",
            ),
            EnablementNote(
                "Ready and queryable",
                "def wait_for_indexes(",
                "Checks both READY status and queryable=true before ingestion completes.",
            ),
        ),
    ),
    EnablementModule(
        key="search",
        label="Search queries",
        path="app/search.py",
        description=(
            "Runs source-filtered lexical, exact vector, and weighted hybrid queries, "
            "with optional Voyage reranking."
        ),
        notes=(
            EnablementNote(
                "Lexical relevance",
                "def lexical_stage(",
                "Boosts section titles, retains fuzzy recall, and filters every query to one PDF.",
            ),
            EnablementNote(
                "Exact vectors",
                "def vector_stage(",
                "Queries the lane-specific field and index with exact cosine retrieval.",
            ),
            EnablementNote(
                "Weighted hybrid",
                "def hybrid_search(",
                "Fuses vector and lexical ranks using the configured 65/35 weighting.",
            ),
            EnablementNote(
                "Optional reranking",
                "def apply_reranker(",
                "Reranks a deeper candidate set while retaining the original Atlas score.",
            ),
        ),
    ),
    EnablementModule(
        key="generation",
        label="RAG answer",
        path="app/generation.py",
        description=(
            "Uses OpenAI Responses or compatible Chat Completions APIs to turn each "
            "pipeline's evidence into a grounded executive summary with rank citations."
        ),
        notes=(
            EnablementNote(
                "Grounding contract",
                "RAG_INSTRUCTIONS =",
                "Requires evidence-only answers, inline rank citations, and explicit uncertainty.",
            ),
            EnablementNote(
                "Bounded context",
                "def _evidence_prompt(",
                "Labels each result by visible rank and caps passage length before generation.",
            ),
            EnablementNote(
                "Generation API",
                "def generate_executive_summary(",
                "Selects Responses or Chat Completions, disables storage, and reports latency.",
            ),
            EnablementNote(
                "Pipeline isolation",
                "def add_rag_summaries(",
                "Generates one answer per retrieval pipeline so differences remain attributable.",
            ),
        ),
    ),
)


def source_modules() -> list[dict[str, object]]:
    modules = []
    root = ROOT.resolve()
    for module in MODULES:
        source_path = (ROOT / module.path).resolve()
        if root not in source_path.parents:
            raise RuntimeError(f"Invalid enablement source path: {module.path}")
        modules.append(
            {
                "key": module.key,
                "label": module.label,
                "path": module.path,
                "description": module.description,
                "language": "python",
                "code": source_path.read_text(encoding="utf-8"),
                "notes": [
                    {
                        "title": note.title,
                        "anchor": note.anchor,
                        "detail": note.detail,
                    }
                    for note in module.notes
                ],
            }
        )
    return modules
