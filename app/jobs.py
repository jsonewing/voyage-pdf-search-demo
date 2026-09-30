from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4


STAGES = (
    ("upload", "Upload PDF"),
    ("extract", "Extract and chunk"),
    ("embed_lite", "Embed with Voyage 4 Lite"),
    ("embed_context", "Embed with Voyage Context 4"),
    ("embed_multimodal", "Embed with Multimodal 3.5"),
    ("store", "Store chunks in Atlas"),
    ("indexes", "Build Search indexes"),
    ("sync", "Verify index visibility"),
)

MODEL_STAGE_KEYS = {
    "embed_lite": "voyage_4_lite",
    "embed_context": "voyage_context_4",
    "embed_multimodal": "voyage_multimodal_3_5",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = Lock()

    def create(
        self,
        filename: str,
        source_id: str,
        selected_model_keys: list[str] | tuple[str, ...] | None = None,
    ) -> dict:
        job_id = uuid4().hex
        selected_model_keys = list(selected_model_keys or MODEL_STAGE_KEYS.values())
        job = {
            "id": job_id,
            "filename": filename,
            "source_id": source_id,
            "selected_model_keys": selected_model_keys,
            "status": "processing",
            "progress": 5,
            "message": "PDF uploaded and validated.",
            "created_at": _now(),
            "updated_at": _now(),
            "stats": {},
            "steps": [
                {
                    "key": key,
                    "label": label,
                    "status": (
                        "complete"
                        if key == "upload"
                        else "skipped"
                        if key in MODEL_STAGE_KEYS
                        and MODEL_STAGE_KEYS[key] not in selected_model_keys
                        else "pending"
                    ),
                    "detail": (
                        "File saved locally."
                        if key == "upload"
                        else "Not selected for this PDF."
                        if key in MODEL_STAGE_KEYS
                        and MODEL_STAGE_KEYS[key] not in selected_model_keys
                        else ""
                    ),
                }
                for key, label in STAGES
            ],
        }
        with self._lock:
            self._jobs[job_id] = job
        return deepcopy(job)

    def update_step(
        self,
        job_id: str,
        key: str,
        status: str,
        detail: str,
        progress: int,
        stats: dict | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for step in job["steps"]:
                if step["key"] == key:
                    step["status"] = status
                    step["detail"] = detail
                    break
            job["message"] = detail
            job["progress"] = progress
            job["updated_at"] = _now()
            if stats:
                job["stats"].update(stats)

    def complete(self, job_id: str, stats: dict) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["status"] = "ready"
            job["progress"] = 100
            job["message"] = "PDF is indexed and ready for live questions."
            job["updated_at"] = _now()
            job["stats"].update(stats)

    def fail(self, job_id: str, message: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job["status"] = "error"
            job["message"] = message
            job["updated_at"] = _now()
            for step in job["steps"]:
                if step["status"] == "running":
                    step["status"] = "error"
                    step["detail"] = message
                    break

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return deepcopy(job) if job else None


jobs = JobStore()
