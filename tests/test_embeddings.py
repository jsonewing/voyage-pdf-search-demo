from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.chunking import Chunk, PdfCorpus
from app.embeddings import (
    embed_context_documents,
    embed_multimodal_documents,
    embed_query,
    rerank_documents,
)


class ContextEmbeddingTests(unittest.TestCase):
    @patch("app.embeddings.get_voyage_client")
    def test_context_vectors_remain_aligned_to_canonical_chunks(self, client_factory) -> None:
        chunks = [
            Chunk("first", "first metadata", 1, 1, "narrative", "A"),
            Chunk("second", "second metadata", 1, 2, "table_row", "A"),
            Chunk("third", "third metadata", 2, 3, "narrative", "B"),
        ]
        corpus = PdfCorpus("Document", 2, chunks, {1: "page one", 2: "page two"})
        client = Mock()
        client.contextualized_embed.return_value = SimpleNamespace(
            results=[
                SimpleNamespace(index=1, embeddings=[[20.0], [3.0], [21.0]]),
                SimpleNamespace(index=0, embeddings=[[10.0], [1.0], [2.0], [11.0]]),
            ]
        )
        client_factory.return_value = client

        progress = []
        self.assertEqual(
            embed_context_documents(
                corpus,
                progress_callback=lambda done, total: progress.append((done, total)),
            ),
            [[1.0], [2.0], [3.0]],
        )
        self.assertEqual(progress, [(2, 2)])
        groups = client.contextualized_embed.call_args.args[0]
        self.assertEqual(groups[0][1:3], ["first metadata", "second metadata"])

    @patch("app.embeddings.get_voyage_client")
    def test_reranker_uses_configured_model_and_depth(self, client_factory) -> None:
        client = Mock()
        client.rerank.return_value = SimpleNamespace(results=[{"index": 1}])
        client_factory.return_value = client
        self.assertEqual(rerank_documents("query", ["a", "b"], 1), [{"index": 1}])
        self.assertEqual(client.rerank.call_args.kwargs["model"], "rerank-2.5")
        self.assertEqual(client.rerank.call_args.kwargs["top_k"], 1)

    @patch("app.embeddings.PdfChunkRenderer")
    @patch("app.embeddings.get_voyage_client")
    def test_multimodal_documents_pair_text_with_visuals(
        self, client_factory, renderer_class
    ) -> None:
        chunk = Chunk("benefit", "benefit metadata", 1, 1, "table_row", "Benefits")
        visual = SimpleNamespace(
            image="image-object",
            kind="table_row_crop",
            sha256="abc123",
            width=500,
            height=120,
            bbox_pdf_points=(1.0, 2.0, 3.0, 4.0),
        )
        renderer = Mock()
        renderer.render.return_value = visual
        renderer_class.return_value.__enter__.return_value = renderer
        client = Mock()
        client.multimodal_embed.return_value = SimpleNamespace(embeddings=[[0.1, 0.2]])
        client_factory.return_value = client

        vectors, metadata = embed_multimodal_documents(Path("sample.pdf"), [chunk])

        self.assertEqual(vectors, [[0.1, 0.2]])
        self.assertEqual(
            client.multimodal_embed.call_args.args[0],
            [["benefit metadata", "image-object"]],
        )
        self.assertEqual(metadata[0]["kind"], "table_row_crop")
        self.assertEqual(metadata[0]["bbox_pdf_points"], [1.0, 2.0, 3.0, 4.0])

    @patch("app.embeddings.get_voyage_client")
    def test_multimodal_query_uses_text_only_input(self, client_factory) -> None:
        client = Mock()
        client.multimodal_embed.return_value = SimpleNamespace(embeddings=[[0.4, 0.5]])
        client_factory.return_value = client
        self.assertEqual(embed_query("office visit", "voyage_multimodal_3_5"), [0.4, 0.5])
        self.assertEqual(client.multimodal_embed.call_args.args[0], [["office visit"]])


if __name__ == "__main__":
    unittest.main()
