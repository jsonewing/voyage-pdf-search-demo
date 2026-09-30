# Voyage PDF Search Portable Demo

> **Demonstration use only.** Use synthetic, public, or otherwise approved non-sensitive PDFs and a non-production Atlas namespace. Read [DEMO_NOTICE.md](DEMO_NOTICE.md) before presenting or sharing this package.

The [SA Demo Walkthrough](docs/DEMO_WALKTHROUGH.md) provides a concise setup checklist, talk track, suggested questions, score guidance, and cleanup steps.

This package runs locally and connects directly to your MongoDB Atlas cluster and Voyage AI account. Credentials are entered in the browser on first launch and saved only to a local `.env` file inside this folder.

## Requirements

- macOS or Linux on Apple Silicon/ARM64 or x86-64
- `curl`, `tar`, `shasum` or `sha256sum`, and internet access on first launch for the bundled Python runtime and pinned dependencies, plus ongoing access to MongoDB Atlas and Voyage AI
- An Atlas database user that can write collection data and manage Search and Vector Search indexes
- This computer's current IP address in the Atlas project access list
- A Voyage AI API key
- An OpenAI or compatible enterprise gateway key only when generated RAG answers are desired

## Start

### macOS

Double-click `start.command`. If macOS blocks the first launch, right-click it and choose **Open**.

### Linux or terminal

```bash
./run.sh
```

The first launch downloads and SHA-256 verifies a pinned standalone Python runtime inside this folder, creates a private `.venv`, installs the hash-verified dependency lock, starts the app on `http://127.0.0.1:8020`, and opens the browser. No system Python installation is needed. Later launches reuse the verified local runtime and environment.

## First-run setup

1. Enter the MongoDB Atlas connection URI and Voyage API key. Optionally add an OpenAI or compatible gateway key for generated RAG answers.
2. For direct OpenAI, keep the default API URL and **Responses API**. For a compatible gateway, enter its API root, select **Chat Completions**, and provide its model deployment name.
3. Keep the default database and collection names unless you need a different namespace.
4. Select **Verify and save**.
5. Upload a PDF and select the Voyage model lanes to build.
6. For a live question, optionally select **OpenAI RAG answer** to generate a cited executive summary after retrieval.

The app verifies required services and any supplied OpenAI key before writing `.env`. Saved credentials are never returned to the browser, included in a newly built distribution, or committed by the included ignore rules. Use the **Connected** button in the header to switch credentials or Atlas namespaces later.

## Stop and restart

Press `Ctrl+C` in the launcher window to stop the server. Run the launcher again to restart it. To use another local port from a terminal:

```bash
PORT=8030 ./run.sh
```

Uploaded PDFs remain in `uploads/` on this computer. Embedded chunks and indexes remain in the configured Atlas cluster.

Re-running `./run.sh` safely restarts a prior copy of this demo on the same port. It will not stop an unrelated application that happens to use that port.

## Distribution integrity

The release includes a matching `.zip.sha256` file. On macOS, verify the download from the directory containing both files:

```bash
shasum -a 256 -c voyage-pdf-search-portable-v1.2.1.zip.sha256
```

For automated or headless use, set `NO_BROWSER=1` before `./run.sh`.

## Scope

The server binds only to `127.0.0.1`. The runtime and application dependencies are local to the extracted folder; Atlas data and Voyage model calls remain cloud services. This is a portable demonstration package, not a shared authenticated web deployment.
