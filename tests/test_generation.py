from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.generation import (
    _evidence_prompt,
    create_openai_client,
    generate_executive_summary,
)


class GenerationTests(unittest.TestCase):
    def test_evidence_prompt_maps_visible_ranks_and_metadata(self) -> None:
        prompt = _evidence_prompt(
            "What is included?",
            [
                {
                    "page": 4,
                    "section_title": "Benefits",
                    "text": "The standard option includes the stated benefit.",
                }
            ],
        )
        self.assertIn("Question:\nWhat is included?", prompt)
        self.assertIn("[Evidence 1]", prompt)
        self.assertIn("Page: 4", prompt)
        self.assertIn("Section: Benefits", prompt)

    @patch("app.generation.get_openai_client")
    @patch("app.generation.get_settings")
    def test_generation_uses_responses_api_without_storage(
        self, get_settings, get_client
    ) -> None:
        get_settings.return_value = SimpleNamespace(
            openai_rag_model="gpt-5-mini",
            openai_api_mode="responses",
        )
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text="The benefit is included [1]."
        )
        get_client.return_value = client

        generated = generate_executive_summary(
            "What is included?",
            [{"page": 4, "section_title": "Benefits", "text": "Included benefit."}],
        )

        self.assertEqual(generated["status"], "complete")
        self.assertEqual(generated["answer"], "The benefit is included [1].")
        request = client.responses.create.call_args.kwargs
        self.assertEqual(request["model"], "gpt-5-mini")
        self.assertFalse(request["store"])
        self.assertIn("[Evidence 1]", request["input"])

    @patch("app.generation.get_openai_client")
    @patch("app.generation.get_settings")
    def test_generation_supports_chat_completions_gateways(
        self, get_settings, get_client
    ) -> None:
        get_settings.return_value = SimpleNamespace(
            openai_rag_model="gpt-5-mini",
            openai_api_mode="chat_completions",
        )
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="The benefit is included [1].")
                )
            ]
        )
        get_client.return_value = client

        generated = generate_executive_summary(
            "What is included?",
            [{"page": 4, "section_title": "Benefits", "text": "Included benefit."}],
        )

        self.assertEqual(generated["status"], "complete")
        self.assertEqual(generated["api_mode"], "chat_completions")
        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "gpt-5-mini")
        self.assertEqual(request["max_completion_tokens"], 1200)
        self.assertFalse(request["store"])
        self.assertEqual(request["messages"][0]["role"], "developer")
        self.assertIn("[Evidence 1]", request["messages"][1]["content"])

    @patch("app.generation.OpenAI")
    def test_custom_gateway_client_adds_api_key_header(self, openai_client) -> None:
        create_openai_client(
            "gateway-secret-value",
            "https://gateway.example/openai/v1/",
        )

        openai_client.assert_called_once_with(
            api_key="gateway-secret-value",
            base_url="https://gateway.example/openai/v1",
            default_headers={"api-key": "gateway-secret-value"},
        )


if __name__ == "__main__":
    unittest.main()
