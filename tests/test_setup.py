from __future__ import annotations

import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from dotenv import dotenv_values

from app.setup import _atlas_target, _persist_env, configure_local


class SetupTests(unittest.TestCase):
    def test_atlas_target_redacts_credentials(self) -> None:
        target = _atlas_target("mongodb+srv://user:password@example.mongodb.net/?retryWrites=true")
        self.assertEqual(target, "example.mongodb.net")
        self.assertNotIn("password", target)

    def test_persist_env_is_private_and_preserves_existing_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text("UPLOAD_MAX_MB=75\n", encoding="utf-8")
            _persist_env(
                {
                    "ATLAS_URI": "mongodb+srv://user:p@cluster.mongodb.net/",
                    "VOYAGE_API_KEY": "pa-test-key-value",
                },
                env_path,
            )
            values = dotenv_values(env_path)
            self.assertEqual(values["UPLOAD_MAX_MB"], "75")
            self.assertEqual(values["VOYAGE_API_KEY"], "pa-test-key-value")
            self.assertEqual(stat.S_IMODE(env_path.stat().st_mode), 0o600)

    @patch("app.setup.setup_summary")
    @patch("app.setup.reload_settings")
    @patch("app.setup.close_openai_client")
    @patch("app.setup.close_voyage_client")
    @patch("app.setup.close_client")
    @patch("app.setup._persist_env")
    @patch("app.setup._validate_openai")
    @patch("app.setup._validate_voyage")
    @patch("app.setup._validate_atlas")
    @patch("app.setup.get_settings")
    def test_blank_secrets_keep_existing_local_credentials(
        self,
        get_settings,
        validate_atlas,
        validate_voyage,
        validate_openai,
        persist_env,
        close_client,
        close_voyage_client,
        close_openai_client,
        reload_settings,
        setup_summary,
    ) -> None:
        get_settings.return_value = SimpleNamespace(
            atlas_uri="mongodb+srv://saved@cluster.mongodb.net/",
            voyage_api_key="pa-saved-key-value",
            openai_api_key="sk-saved-key-value-for-testing",
            openai_base_url="https://gateway.example/openai/v1",
            openai_api_mode="chat_completions",
            openai_rag_model="gpt-5-mini",
        )
        setup_summary.return_value = {"configured": True}
        result = configure_local(
            "",
            "",
            "",
            "demo_db",
            "chunks",
            "",
            "",
            "",
        )
        validate_atlas.assert_called_once_with("mongodb+srv://saved@cluster.mongodb.net/")
        validate_voyage.assert_called_once_with("pa-saved-key-value")
        validate_openai.assert_called_once_with(
            "sk-saved-key-value-for-testing",
            "gpt-5-mini",
            "https://gateway.example/openai/v1",
            "chat_completions",
        )
        persisted = persist_env.call_args.args[0]
        self.assertEqual(persisted["ATLAS_DB"], "demo_db")
        self.assertEqual(persisted["ATLAS_COLLECTION"], "chunks")
        self.assertEqual(
            persisted["OPENAI_API_KEY"], "sk-saved-key-value-for-testing"
        )
        self.assertEqual(
            persisted["OPENAI_BASE_URL"], "https://gateway.example/openai/v1"
        )
        self.assertEqual(persisted["OPENAI_API_MODE"], "chat_completions")
        self.assertEqual(persisted["OPENAI_RAG_MODEL"], "gpt-5-mini")
        close_client.assert_called_once()
        close_voyage_client.assert_called_once()
        close_openai_client.assert_called_once()
        reload_settings.assert_called_once_with(persisted)
        self.assertTrue(result["configured"])


if __name__ == "__main__":
    unittest.main()
