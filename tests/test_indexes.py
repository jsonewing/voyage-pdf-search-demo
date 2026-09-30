from __future__ import annotations

import unittest
from copy import deepcopy
from unittest.mock import MagicMock

from app.indexes import ensure_indexes, lexical_definition, required_indexes, vector_definition


class IndexDefinitionTests(unittest.TestCase):
    def test_lexical_mapping_is_explicit_and_filterable(self) -> None:
        definition = lexical_definition()
        fields = definition["mappings"]["fields"]
        self.assertFalse(definition["mappings"]["dynamic"])
        self.assertEqual(fields["source_id"]["type"], "token")
        self.assertIn("section_title", fields)
        self.assertIn("text", definition["storedSource"]["include"])

    def test_vector_mapping_has_cosine_vector_and_filters(self) -> None:
        fields = vector_definition("embedding_test")["fields"]
        self.assertEqual(fields[0]["path"], "embedding_test")
        self.assertEqual(fields[0]["numDimensions"], 1024)
        self.assertEqual(fields[0]["similarity"], "cosine")
        self.assertEqual({field["path"] for field in fields[1:]}, {"source_id", "chunk_kind"})

    def test_selected_index_set_includes_only_requested_vector_lane(self) -> None:
        indexes = required_indexes(("voyage_multimodal_3_5",))
        names = [index.document["name"] for index in indexes]
        self.assertEqual(names, ["pdf_lexical_v1", "pdf_vector_voyage_multimodal_3_5_v1"])

    def test_matching_indexes_are_reused(self) -> None:
        collection = MagicMock()
        collection.list_search_indexes.return_value = [
            {
                "name": "pdf_lexical_v1",
                "type": "search",
                "latestDefinition": lexical_definition(),
            },
            {
                "name": "pdf_vector_voyage_4_lite_v1",
                "type": "vectorSearch",
                "latestDefinition": vector_definition("embedding_voyage_4_lite"),
            },
        ]

        actions = ensure_indexes(collection, ("voyage_4_lite",))

        self.assertEqual(
            actions,
            ["pdf_lexical_v1 reused", "pdf_vector_voyage_4_lite_v1 reused"],
        )
        collection.create_search_index.assert_not_called()
        collection.update_search_index.assert_not_called()

    def test_definition_drift_updates_existing_index(self) -> None:
        stale_vector = deepcopy(vector_definition("embedding_voyage_4_lite"))
        stale_vector["fields"][0]["numDimensions"] = 768
        collection = MagicMock()
        collection.list_search_indexes.return_value = [
            {
                "name": "pdf_lexical_v1",
                "type": "search",
                "latestDefinition": lexical_definition(),
            },
            {
                "name": "pdf_vector_voyage_4_lite_v1",
                "type": "vectorSearch",
                "latestDefinition": stale_vector,
            },
        ]

        actions = ensure_indexes(collection, ("voyage_4_lite",))

        expected = vector_definition("embedding_voyage_4_lite")
        collection.update_search_index.assert_called_once_with(
            "pdf_vector_voyage_4_lite_v1", expected
        )
        self.assertIn("pdf_vector_voyage_4_lite_v1 updated", actions)

    def test_conflicting_index_type_fails_with_actionable_error(self) -> None:
        collection = MagicMock()
        collection.list_search_indexes.return_value = [
            {
                "name": "pdf_lexical_v1",
                "type": "search",
                "latestDefinition": lexical_definition(),
            },
            {
                "name": "pdf_vector_voyage_4_lite_v1",
                "type": "search",
                "latestDefinition": vector_definition("embedding_voyage_4_lite"),
            },
        ]

        with self.assertRaisesRegex(RuntimeError, "Use a new index name"):
            ensure_indexes(collection, ("voyage_4_lite",))


if __name__ == "__main__":
    unittest.main()
