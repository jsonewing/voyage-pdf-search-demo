<img width="1470" height="1166" alt="image" src="https://github.com/user-attachments/assets/e5aa3ca0-42ed-40c2-a215-91ddbf946a55" />



# Voyage PDF Search Lab

> [!IMPORTANT]
> **Demonstration use only.** Use synthetic, public, or otherwise approved non-sensitive PDFs and a non-production Atlas namespace. This local application is not an authenticated or supported production deployment. Review [DEMO_NOTICE.md](DEMO_NOTICE.md) before sharing or presenting it.

For a repeatable 10-15 minute presentation, use the [SA Demo Walkthrough](docs/DEMO_WALKTHROUGH.md).

The **Enablement** button in the application header opens a copy-friendly reference to the exact configuration, connection, chunking, visual rendering, embedding, Atlas loading, index, and search modules used by the running demo. Each module includes concise implementation notes that jump to the relevant code. The endpoint is restricted to an explicit source-file allowlist and never returns environment-variable values or credentials.

An independent, lightweight PDF retrieval and RAG demo using MongoDB Atlas Search, three selectable Voyage AI embedding paths, and optional OpenAI answer generation:

- `voyage-4-lite` for efficient metadata-enriched chunk embeddings
- `voyage-context-4` for native contextualized embeddings across ordered page groups
- `voyage-multimodal-3.5` for chunk text paired with rendered PDF page or table-row imagery

The browser app accepts a PDF, lets the user select any combination of the three models, builds only those representations, creates or reuses their Atlas indexes, verifies index visibility, and compares live retrieval evidence.

The optional **OpenAI RAG answer** control sends each pipeline's five displayed passages to the configured OpenAI model after retrieval. It returns a concise executive summary with inline rank citations while preserving the extractive summary, evidence, Atlas scores, retrieval latency, and generation latency. Direct OpenAI connections use the [Responses API](https://developers.openai.com/api/docs/guides/text); OpenAI-compatible enterprise gateways can use [Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create). Both modes disable response storage.

## Run

From this repository's root:

```bash
./run.sh
```

The launcher downloads and SHA-256 verifies a pinned standalone Python runtime and installs private dependencies on first use, then opens [http://127.0.0.1:8020](http://127.0.0.1:8020). The local `.env` is ignored by Git.

If `.env` is absent, the browser opens a first-run connection screen. It verifies the supplied Atlas URI and Voyage API key, plus an optional OpenAI or compatible gateway key, then saves them locally with owner-only file permissions. Direct OpenAI defaults to `https://api.openai.com/v1` and `responses`; compatible gateways can provide their API root and select `chat_completions`. OpenAI generation is optional and retrieval remains fully available without it. The **Connected** control can update credentials or the Atlas namespace later without returning saved secrets to the browser.

## Portable Distribution

Build the secret-free handoff ZIP with:

```bash
make dist
```

The result is a versioned ZIP and matching SHA-256 file in `dist/`, for example `voyage-pdf-search-portable-v1.3.1.zip`. It excludes `.env`, `.venv`, `vendor`, tests, cached files, and uploaded PDFs. The package contains the demo notice, SA walkthrough, hash-locked dependency graph, full application, concise operator README, and self-bootstrapping launchers:

- macOS: double-click `start.command`
- macOS or Linux terminal: run `./run.sh`

The first launch downloads its own pinned Python runtime, creates a private virtual environment, and opens the app. A recipient does not need to install Python. They need internet access, a Voyage API key, an Atlas URI, an Atlas database user with data and Search-index privileges, and an Atlas access-list entry for their current IP address. An OpenAI or compatible enterprise gateway key is optional and enables generated RAG answers.

The first upload creates one lexical index plus one vector index per selected model and can take several minutes while Atlas builds them. Later uploads compare the live Atlas definitions with the expected mappings, update drifted definitions in place, and then wait for every index to become queryable. A conflicting index type fails with an actionable error instead of being reused silently. Progress is reported for extraction, each selected embedding pass, storage, index readiness, and search visibility.

## Retrieval Design

All modes search the same canonical chunk IDs so returned evidence can be compared directly.

| Mode | Atlas operator | Pipelines shown |
| --- | --- | --- |
| Lexical | `$search` | One shared full-text baseline |
| Vector | `$vectorSearch` | Each Voyage model selected when the PDF was uploaded |
| Hybrid | `$rankFusion` | Each selected Voyage model fused independently with the shared lexical baseline |

Hybrid uses weighted reciprocal rank fusion with a `0.65` vector and `0.35` lexical balance. Each source is filtered by `source_id`. Exact vector search is intentional for this single-document demo: it removes approximate-nearest-neighbor recall variance and makes model and representation comparisons easier to interpret.

The optional **Voyage rerank** checkbox is available for Vector and Hybrid searches. It expands first-stage retrieval to 20 candidates, sends their evidence text to `rerank-2.5`, and returns the reranker's top 5. The UI disables reranking for the shared Lexical baseline, preserves the original Atlas retrieval score, adds the reranker relevance score, and includes reranking in end-to-end latency.

The independent **OpenAI RAG answer** checkbox works with Lexical, Vector, or Hybrid retrieval, with or without Voyage reranking. One grounded answer is generated per displayed pipeline so differences in the generated summaries remain attributable to the retrieved evidence. Evidence is labeled by visible rank, input passage length is bounded, prompt-injection instructions inside source text are explicitly ignored, and factual claims are requested with `[1]`-style citations.

### Canonical chunking

The parser keeps chunks page-bound, splits narrative text at natural boundaries near 1,600 characters with 220 characters of overlap, and extracts detected PDF tables into header-qualified row chunks. Text inside detected tables is removed from the narrative pass to avoid duplicate evidence.

Voyage 4 Lite embeds each chunk with document, page, section, and content-type metadata prepended. Voyage Context 4 receives ordered groups for each page plus bounded neighboring-page context. Voyage Multimodal 3.5 receives that chunk text together with the rendered full page for narrative chunks or a padded table-row crop for table chunks. Only vectors and reproducibility metadata are stored; raw page images are not stored in Atlas. All three paths preserve one-to-one canonical evidence alignment.

Scanned image-only PDFs still require OCR because canonical text is used for lexical retrieval, evidence display, and text-plus-image multimodal inputs.

## Indexes

The app owns these indexes in `voyage_pdf_live_demo.pdf_chunks`:

- `pdf_lexical_v1`: explicit Atlas Search mappings for content, headings, source filters, and result metadata
- `pdf_vector_voyage_4_lite_v1`: 1,024-dimension cosine vectors plus source filters
- `pdf_vector_voyage_context_4_v1`: 1,024-dimension cosine vectors plus source filters
- `pdf_vector_voyage_multimodal_3_5_v1`: 1,024-dimension cosine vectors from text-plus-image inputs plus source filters

Indexes are created lazily after the first document is stored, which avoids Atlas's `NamespaceNotFound` error on an empty collection.

## What The UI Reports

- Live ingestion progress and per-stage details
- Extracted page, narrative chunk, and table-row counts
- Selected and skipped model lanes for each PDF
- End-to-end query latency, including query embedding
- Optional Voyage reranker latency and relevance score
- Optional OpenAI executive summary and generation latency
- Atlas relevance or vector score for each result
- Page, section, chunk type, and verbatim evidence text
- Top-result overlap shared across all available Voyage model lanes

Scores are meaningful within a single pipeline and query, but should not be compared numerically across `$search`, cosine similarity, and `$rankFusion`. The retrieval-only summary remains deterministic and extractive; the separately labeled RAG summary calls OpenAI only when selected.

## API

| Endpoint | Purpose |
| --- | --- |
| `POST /api/upload` | Validate, save, and enqueue a PDF |
| `GET /api/jobs/{job_id}` | Read live ingestion status |
| `GET /api/documents` | List indexed PDFs |
| `POST /api/search` | Run retrieval with optional Voyage reranking and OpenAI RAG generation |
| `GET /api/config` | Read non-secret pipeline configuration |
| `GET /api/setup` | Read redacted local connection status |
| `POST /api/setup` | Verify and save local Atlas and Voyage credentials |
| `GET /api/health` | Verify Atlas connectivity |

## Test

```bash
make test
```

The tests cover deterministic chunking, contextual and multimodal alignment, index definitions and drift handling, job state transitions, source-aware retrieval, hybrid normalization, secure setup, service-failure responses, and grounded OpenAI request construction. They do not call Atlas, Voyage AI, or OpenAI.

Before sharing a commit or release, run:

```bash
make release-check
```

This runs the tests, dependency consistency check, launcher syntax check, portable build, and a tracked-file audit for credentials, private environment references, personal paths, PDFs, archives, and generated runtime content.

## Production Boundary

The indexing and retrieval shapes follow production-oriented Atlas patterns: explicit mappings, source filters, one shared `MongoClient`, deterministic upserts, index-readiness checks, and canonical evidence IDs. The app itself remains demo-grade: jobs live in process memory, uploads are stored on local disk, and there is no authentication, distributed worker, OCR service, or retention policy.
