from __future__ import annotations

import unittest

from app.chunking import Chunk, normalize_text, split_text, stable_chunk_id, table_row_texts


class ChunkingTests(unittest.TestCase):
    def test_normalize_text_repairs_line_break_hyphenation(self) -> None:
        self.assertEqual(normalize_text("contex-\ntual  search"), "contextual search")

    def test_split_text_preserves_bounded_overlap(self) -> None:
        text = " ".join(f"Sentence {index} contains useful evidence." for index in range(90))
        chunks = split_text(text, max_chars=300, overlap_chars=45)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(len(chunk) <= 345 for chunk in chunks))
        self.assertTrue(all(chunk.strip() for chunk in chunks))

    def test_stable_chunk_id_is_deterministic(self) -> None:
        chunk = Chunk("Evidence", "Document: Test\nEvidence", 3, 4, "narrative", "Plan")
        self.assertEqual(stable_chunk_id("source", chunk), stable_chunk_id("source", chunk))
        self.assertNotEqual(stable_chunk_id("source", chunk), stable_chunk_id("other", chunk))

    def test_table_rows_keep_pdf_geometry_for_visual_crops(self) -> None:
        class Row:
            def __init__(self, bbox):
                self.bbox = bbox

        class Table:
            bbox = (10, 20, 300, 180)
            rows = [Row((10, 20, 300, 50)), Row((10, 50, 300, 90))]

            @staticmethod
            def extract():
                return [["Benefit", "Standard"], ["Office visit", "$30"]]

        class Page:
            @staticmethod
            def find_tables():
                return [Table()]

        rows, _ = table_row_texts(Page())
        self.assertEqual(rows[0].bbox, (10.0, 50.0, 300.0, 90.0))
        self.assertIn("Benefit: Office visit", rows[0].text)


if __name__ == "__main__":
    unittest.main()
