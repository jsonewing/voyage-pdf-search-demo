# Demonstration Use Notice

This repository is a demonstration and enablement asset. It illustrates PDF ingestion, chunking, Voyage AI embeddings and reranking, MongoDB Atlas Search, Vector Search, hybrid retrieval, and optional OpenAI-compatible answer generation. It is not an authenticated, supported, or hardened production service.

## Data Safety

- Use synthetic, public, or otherwise approved non-sensitive PDFs.
- Use a dedicated non-production Atlas project, cluster, database, and database user.
- Grant only the data and Search-index privileges required for the demonstration.
- Keep Atlas, Voyage AI, and optional generation credentials out of Git, chat, slides, screenshots, and shared ZIP files.
- Treat the generated `.env` as sensitive. It is stored only in the application folder and is excluded from Git and portable builds.

## Data Flow

- The original PDF remains in the local `uploads/` directory.
- Extracted chunks, metadata, and embeddings are written to the configured Atlas collection.
- PDF content is sent to the selected Voyage AI models to create embeddings and, when enabled, reranking scores.
- Retrieved evidence is sent to the configured OpenAI-compatible endpoint only when **OpenAI RAG answer** is selected.

## Deployment Boundary

The server binds to `127.0.0.1` and is intended for one presenter on one workstation. It has no authentication, multi-user isolation, durable job queue, OCR service, automated retention policy, or production monitoring. Do not expose it on a shared host or public network without a separate production security and architecture review.

## Before Sharing

Run `make release-check`, verify the generated ZIP checksum, and inspect `git status`. Share only source controlled by Git or the generated portable ZIP. Never share a configured `.env`, the `uploads/` directory, `.venv/`, `vendor/`, `.runtime/`, or an entire previously used working directory.

After a demonstration, remove local uploads and Atlas data according to your organization's approved retention process, and rotate temporary credentials when appropriate.
