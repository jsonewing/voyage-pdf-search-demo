from __future__ import annotations

import unittest

from app.jobs import JobStore


class JobStoreTests(unittest.TestCase):
    def test_job_lifecycle_reports_stage_and_completion(self) -> None:
        store = JobStore()
        job = store.create("plan.pdf", "source-123")
        self.assertEqual(job["steps"][0]["status"], "complete")
        store.update_step(job["id"], "extract", "running", "Extracting", 10)
        self.assertEqual(store.get(job["id"])["steps"][1]["status"], "running")
        store.complete(job["id"], {"chunks": 12})
        completed = store.get(job["id"])
        self.assertEqual(completed["status"], "ready")
        self.assertEqual(completed["stats"]["chunks"], 12)

    def test_unselected_model_stages_are_skipped(self) -> None:
        store = JobStore()
        job = store.create("plan.pdf", "source-123", ["voyage_4_lite"])
        statuses = {step["key"]: step["status"] for step in job["steps"]}
        self.assertEqual(statuses["embed_lite"], "pending")
        self.assertEqual(statuses["embed_context"], "skipped")
        self.assertEqual(statuses["embed_multimodal"], "skipped")


if __name__ == "__main__":
    unittest.main()
