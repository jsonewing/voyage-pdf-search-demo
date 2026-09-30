# SA Demo Walkthrough

This walkthrough is designed for a focused 10-15 minute demonstration of PDF retrieval with MongoDB Atlas and Voyage AI. It is not a benchmark protocol and should not be used to make broad model-quality claims from one document or a handful of questions.

## Before The Session

1. Read [DEMO_NOTICE.md](../DEMO_NOTICE.md) and use only synthetic, public, or approved non-sensitive content.
2. Prepare a non-production Atlas namespace and a least-privileged database user that can write data and manage Search indexes.
3. Confirm the presenter's IP address is allowed by Atlas.
4. Have a Voyage AI API key available. An OpenAI or compatible gateway key is optional and is needed only for generated RAG answers.
5. Choose a text-based PDF under 50 MB. A document with narrative text, tables, and meaningful page visuals demonstrates the model differences best.
6. Run `./run.sh`, open `http://127.0.0.1:8020`, and use **Connection** to verify the credentials.
7. For a time-limited meeting, upload and index the PDF before the call. The indexed corpus remains available in Atlas for the live query portion.

## Recommended Story

### 1. Orient The Audience

Explain that every model searches the same canonical chunks, so differences are attributable to the embedding representation rather than different source text. The demo offers three retrieval modes:

- **Lexical** uses Atlas `$search` for term-based relevance.
- **Vector** uses exact cosine `$vectorSearch` independently for each selected Voyage model.
- **Hybrid** uses Atlas `$rankFusion` with 65% vector and 35% lexical weighting.

### 2. Build The Corpus

Select the PDF and the model lanes to compare. For a quick live build, select **Voyage 4 Lite** and **Voyage Context 4**. Add **Voyage Multimodal 3.5** when the document contains charts, diagrams, forms, or other visual evidence worth evaluating.

Select **Build search pipelines** and narrate the status window: upload, extraction and canonical chunking, embeddings, Atlas storage, index readiness, and retrieval verification. Context 4 receives ordered page groups; Multimodal 3.5 receives chunk text paired with a rendered page or table-row crop.

### 3. Establish The Baseline

Start with **Hybrid**, with reranking and RAG turned off. Ask a precise question and compare the returned passages, source pages, Atlas scores, and latency across model lanes. Point out that this is retrieval evidence, not a generated answer.

Switch to **Lexical** for a query containing exact terminology from the PDF. Then switch to **Vector** and paraphrase the same question to show semantic retrieval. Lexical is a shared baseline, so Voyage reranking is intentionally unavailable in that mode.

### 4. Add Reranking

Return to **Hybrid**, select **Voyage rerank**, and repeat the question. Explain that Atlas retrieves 20 candidates and `rerank-2.5` selects the final five. The UI preserves the original Atlas score and shows the separate reranker relevance score and added latency.

### 5. Add The RAG Layer

Select **OpenAI RAG answer** and repeat the query. The generated executive answer is grounded only in the five displayed passages and uses visible rank citations such as `[1]`. Retrieval evidence remains available so the audience can verify the answer rather than treating generation as the source of truth.

### 6. Show Enablement

Open **Enablement** to show the credential-free source modules for chunking, embeddings, Atlas loading, index creation, search, reranking, and generation. This connects the visible workflow to implementation code a customer can adapt.

## Question Set

Use four or five questions prepared from the selected PDF:

1. **Exact fact:** Ask for a named value, requirement, date, or definition.
2. **Table comparison:** Ask how two options differ across a specific benefit or attribute.
3. **Paraphrase:** Use different wording from the document to test semantic retrieval.
4. **Cross-page context:** Ask a question whose answer depends on a heading and details that span nearby pages.
5. **Visual evidence:** When Multimodal 3.5 is indexed, ask about a chart, diagram, layout, or table presentation.
6. **Unanswerable control:** Ask one question the PDF does not answer and verify that the evidence does not support a confident response.

Avoid inventing questions during the presentation. Confirm the expected source pages beforehand so retrieval quality can be discussed objectively.

## Reading The Results

- Compare rank order and evidence quality first; raw scores from `$search`, cosine similarity, `$rankFusion`, and reranking are not directly comparable.
- Latency is end to end for the selected pipeline and depends on document size, network conditions, provider latency, candidate depth, and whether reranking or generation is enabled.
- Exact vector search is intentional for this single-document comparison and removes approximate-nearest-neighbor recall variance.
- Reranking improves ordering only when the relevant evidence is present in the first-stage candidate set.
- A generated answer is a presentation layer over retrieval. Validate its claims against the cited passages.

## Troubleshooting

- **Connection fails:** Check Atlas cluster availability, the IP access list, database-user permissions, and API-key validity.
- **Indexing takes several minutes:** Atlas may still be building or updating Search indexes; follow the status window rather than restarting.
- **No useful lexical evidence:** Confirm the PDF contains extractable text. Image-only scans require OCR outside this demo.
- **Multimodal is slower:** Page rendering and image embedding add work by design. Pre-index before a scheduled presentation.
- **RAG is unavailable:** Add an OpenAI or compatible gateway key in **Connection**. Retrieval remains fully functional without it.
- **Port 8020 is occupied:** Run `PORT=8030 ./run.sh` and open the displayed URL.

## Close And Clean Up

Stop the local server with `Ctrl+C`. Uploaded PDFs remain under `uploads/`, while chunks, embeddings, and indexes remain in the configured Atlas namespace. Remove them through your organization's approved process when they are no longer needed. Do not share the working folder after configuration; share the clean portable ZIP or the reviewed Git repository instead.
