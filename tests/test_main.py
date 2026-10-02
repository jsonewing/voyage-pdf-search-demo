from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class SearchApiTests(unittest.TestCase):
    @patch("app.main.get_client")
    def test_health_failure_does_not_expose_connection_details(self, get_client) -> None:
        get_client.return_value.admin.command.side_effect = RuntimeError(
            "mongodb+srv://user:private-password@example.mongodb.net"
        )

        with TestClient(app) as client:
            response = client.get("/api/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "detail": "Search services are unavailable. "
                "Check service connectivity and try again."
            },
        )
        self.assertNotIn("private-password", response.text)

    @patch("app.main.configure_local")
    def test_setup_saves_secrets_without_returning_them(self, configure_local) -> None:
        configure_local.return_value = {
            "configured": True,
            "atlas_configured": True,
            "voyage_configured": True,
            "openai_configured": True,
            "openai_base_url": "https://gateway.example/openai/v1",
            "openai_api_mode": "chat_completions",
            "openai_rag_model": "gpt-5",
            "atlas_target": "example.mongodb.net",
            "database": "demo_db",
            "collection": "chunks",
            "storage": ".env in this application folder",
            "message": "Connection verified and saved locally.",
        }
        with TestClient(app) as client:
            response = client.post(
                "/api/setup",
                json={
                    "atlas_uri": "mongodb+srv://user:secret@example.mongodb.net/",
                    "voyage_api_key": "pa-secret-value",
                    "openai_api_key": "sk-secret-value-for-testing",
                    "database": "demo_db",
                    "collection": "chunks",
                    "openai_base_url": "https://gateway.example/openai/v1",
                    "openai_api_mode": "chat_completions",
                    "openai_rag_model": "gpt-5",
                },
            )
        self.assertEqual(response.status_code, 200)
        configure_local.assert_called_once_with(
            "mongodb+srv://user:secret@example.mongodb.net/",
            "pa-secret-value",
            "sk-secret-value-for-testing",
            "demo_db",
            "chunks",
            "https://gateway.example/openai/v1",
            "chat_completions",
            "gpt-5",
        )
        self.assertNotIn("secret", response.text)

    def test_setup_status_never_returns_credentials(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/setup")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("atlas_uri", response.json())
        self.assertNotIn("voyage_api_key", response.json())
        self.assertNotIn("openai_api_key", response.json())

    def test_enablement_returns_only_approved_source_modules(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/enablement")
        self.assertEqual(response.status_code, 200)
        modules = response.json()["modules"]
        self.assertEqual(
            [module["key"] for module in modules],
            [
                "configuration",
                "database",
                "setup",
                "chunking",
                "visuals",
                "embeddings",
                "load",
                "indexes",
                "search",
                "generation",
            ],
        )
        self.assertTrue(all(module["path"].startswith("app/") for module in modules))
        self.assertIn("def extract_pdf", modules[3]["code"])
        self.assertTrue(all(3 <= len(module["notes"]) <= 4 for module in modules))
        self.assertTrue(
            all(
                note["anchor"] in module["code"]
                for module in modules
                for note in module["notes"]
            )
        )
        self.assertNotIn("VOYAGE_API_KEY=", "".join(module["code"] for module in modules))

    @patch("app.main.get_collection")
    def test_document_listing_reports_atlas_failures_without_secrets(
        self, get_collection
    ) -> None:
        get_collection.return_value.aggregate.side_effect = RuntimeError(
            "mongodb+srv://user:private-password@example.mongodb.net"
        )

        with TestClient(app) as client:
            response = client.get("/api/documents")

        self.assertEqual(response.status_code, 503)
        self.assertIn("Search services are unavailable", response.json()["detail"])
        self.assertNotIn("private-password", response.text)

    @patch("app.main.add_rag_summaries")
    @patch("app.main.compare_pipelines")
    @patch("app.main.get_settings")
    def test_rag_enriches_retrieval_when_enabled(
        self, get_settings, compare, add_rag
    ) -> None:
        get_settings.return_value.openai_api_key = "sk-test-key"
        compare.return_value = [{"key": "voyage_4_lite", "results": []}]
        add_rag.return_value = [
            {
                "key": "voyage_4_lite",
                "results": [],
                "rag": {"status": "complete", "answer": "Grounded answer [1]."},
            }
        ]
        with TestClient(app) as client:
            response = client.post(
                "/api/search",
                json={
                    "query": "benefit details",
                    "source_id": "source-123",
                    "mode": "hybrid",
                    "rag": True,
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["rag"])
        add_rag.assert_called_once_with("benefit details", compare.return_value)

    @patch("app.main.compare_pipelines")
    @patch("app.main.get_settings")
    def test_rag_requires_optional_openai_key(self, get_settings, compare) -> None:
        get_settings.return_value.openai_api_key = ""
        with TestClient(app) as client:
            response = client.post(
                "/api/search",
                json={
                    "query": "benefit details",
                    "source_id": "source-123",
                    "mode": "hybrid",
                    "rag": True,
                },
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("OpenAI API key", response.json()["detail"])
        compare.assert_not_called()

    def test_lexical_rerank_is_rejected_before_search_execution(self) -> None:
        with patch("app.main.compare_pipelines") as compare:
            with TestClient(app) as client:
                response = client.post(
                    "/api/search",
                    json={
                        "query": "benefit details",
                        "source_id": "source-123",
                        "mode": "lexical",
                        "rerank": True,
                    },
                )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Vector and Hybrid", response.json()["detail"])
        compare.assert_not_called()

    @patch("app.main.compare_pipelines")
    def test_search_failure_does_not_expose_service_details(self, compare) -> None:
        compare.side_effect = RuntimeError("pa-private-key")

        with TestClient(app) as client:
            response = client.post(
                "/api/search",
                json={
                    "query": "benefit details",
                    "source_id": "source-123",
                    "mode": "hybrid",
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("pa-private-key", response.text)

    @patch("pathlib.Path.write_bytes")
    @patch("app.main.executor.submit")
    @patch("app.main.jobs.create")
    @patch("app.main.get_settings")
    def test_upload_preserves_selected_model_lanes(
        self, get_settings, create_job, submit, write_bytes
    ) -> None:
        get_settings.return_value = SimpleNamespace(
            validate=lambda: None,
            upload_max_mb=50,
            upload_dir=Path("/tmp"),
            lanes=(
                SimpleNamespace(key="voyage_4_lite"),
                SimpleNamespace(key="voyage_context_4"),
                SimpleNamespace(key="voyage_multimodal_3_5"),
            ),
        )
        create_job.return_value = {"id": "job-1", "status": "processing"}
        with TestClient(app) as client:
            response = client.post(
                "/api/upload",
                files=[
                    ("file", ("sample.pdf", b"%PDF-1.4\n", "application/pdf")),
                    ("models", (None, "voyage_4_lite")),
                    ("models", (None, "voyage_multimodal_3_5")),
                ],
            )
        self.assertEqual(response.status_code, 202)
        selected = create_job.call_args.args[2]
        self.assertEqual(selected, ["voyage_4_lite", "voyage_multimodal_3_5"])
        self.assertEqual(submit.call_args.args[-1], selected)
        write_bytes.assert_called_once()


if __name__ == "__main__":
    unittest.main()
