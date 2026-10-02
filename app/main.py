from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import hashlib
import logging
from pathlib import Path
import re
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr
from pymongo.errors import PyMongoError

from app.config import ROOT, get_settings
from app.db import close_client, get_client, get_collection
from app.enablement import source_modules
from app.embeddings import close_voyage_client
from app.generation import add_rag_summaries, close_openai_client
from app.jobs import jobs
from app.pipeline import process_pdf
from app.search import compare_pipelines
from app.setup import SetupValidationError, configure_local, setup_summary


executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pdf-ingestion")
logger = logging.getLogger(__name__)


def service_error(exc: Exception) -> HTTPException:
    logger.warning("Search service request failed (%s)", type(exc).__name__)
    return HTTPException(
        status_code=503,
        detail="Search services are unavailable. Check service connectivity and try again.",
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings().upload_dir.mkdir(parents=True, exist_ok=True)
    yield
    executor.shutdown(wait=False, cancel_futures=False)
    close_voyage_client()
    close_openai_client()
    close_client()


app = FastAPI(title="Voyage PDF Search Lab", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    source_id: str = Field(min_length=8, max_length=128)
    mode: Literal["lexical", "vector", "hybrid"] = "hybrid"
    limit: int = Field(default=5, ge=1, le=10)
    rerank: bool = False
    rag: bool = False


class SetupRequest(BaseModel):
    atlas_uri: SecretStr | None = None
    voyage_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    openai_base_url: str = Field(default="", max_length=500)
    openai_api_mode: Literal["responses", "chat_completions"] = "responses"
    openai_rag_model: str = Field(default="gpt-5", min_length=1, max_length=100)
    database: str = Field(default="voyage_pdf_live_demo", min_length=1, max_length=64)
    collection: str = Field(default="pdf_chunks", min_length=1, max_length=64)


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "document.pdf").name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
    return name or "document.pdf"


@app.get("/")
def index() -> FileResponse:
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/config")
def config() -> dict:
    settings = get_settings()
    return {
        "models": [
            {
                "key": lane.key,
                "label": lane.label,
                "model": lane.model,
                "representation": lane.representation,
                "provider": lane.provider,
            }
            for lane in settings.lanes
        ],
        "hybrid_weights": {
            "vector": settings.hybrid_vector_weight,
            "lexical": settings.hybrid_lexical_weight,
        },
        "rerank_model": settings.voyage_rerank_model,
        "rag_model": settings.openai_rag_model,
        "rag_available": bool(settings.openai_api_key),
        "rag_api_mode": settings.openai_api_mode,
        "rag_base_url": settings.openai_base_url,
        "upload_max_mb": settings.upload_max_mb,
        "database": settings.atlas_db,
        "collection": settings.atlas_collection,
    }


@app.get("/api/health")
def health() -> dict:
    try:
        get_client().admin.command("ping")
    except (RuntimeError, PyMongoError) as exc:
        raise service_error(exc) from exc
    return {"status": "ok"}


@app.get("/api/setup")
def setup_status() -> dict:
    return setup_summary()


@app.post("/api/setup")
async def save_setup(request: SetupRequest) -> dict:
    atlas_uri = request.atlas_uri.get_secret_value() if request.atlas_uri else ""
    voyage_api_key = (
        request.voyage_api_key.get_secret_value() if request.voyage_api_key else ""
    )
    openai_api_key = (
        request.openai_api_key.get_secret_value() if request.openai_api_key else ""
    )
    try:
        return await run_in_threadpool(
            configure_local,
            atlas_uri,
            voyage_api_key,
            openai_api_key,
            request.database,
            request.collection,
            request.openai_base_url,
            request.openai_api_mode,
            request.openai_rag_model,
        )
    except SetupValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/enablement")
def enablement() -> dict:
    return {"modules": source_modules()}


@app.get("/api/documents")
def documents() -> dict:
    try:
        pipeline = [
            {"$match": {"record_type": "chunk"}},
            {
                "$group": {
                    "_id": "$source_id",
                    "filename": {"$first": "$filename"},
                    "title": {"$first": "$document_title"},
                    "pages": {"$max": "$page"},
                    "chunks": {"$sum": 1},
                    "created_at": {"$max": "$created_at"},
                    "selected_model_keys": {"$first": "$selected_model_keys"},
                    "models": {"$first": "$models"},
                }
            },
            {"$sort": {"created_at": -1}},
            {"$limit": 25},
        ]
        items = []
        for item in get_collection().aggregate(pipeline):
            selected = item.pop("selected_model_keys", None)
            models = item.pop("models", {}) or {}
            item["available_model_keys"] = selected or list(models)
            items.append({"source_id": item.pop("_id"), **item})
    except (RuntimeError, PyMongoError) as exc:
        raise service_error(exc) from exc
    return {"documents": items}


@app.post("/api/upload", status_code=202)
async def upload(
    file: UploadFile = File(...), models: list[str] | None = Form(default=None)
) -> dict:
    settings = get_settings()
    try:
        settings.validate()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    filename = _safe_filename(file.filename)
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    maximum = settings.upload_max_mb * 1024 * 1024
    payload = await file.read(maximum + 1)
    await file.close()
    if not payload:
        raise HTTPException(status_code=400, detail="The uploaded PDF is empty.")
    if len(payload) > maximum:
        raise HTTPException(
            status_code=413,
            detail=f"The PDF exceeds the {settings.upload_max_mb} MB upload limit.",
        )
    if not payload.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid PDF.")

    available_keys = [lane.key for lane in settings.lanes]
    requested_keys = models or available_keys
    unknown = sorted(set(requested_keys) - set(available_keys))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported model selection: {', '.join(unknown)}",
        )
    selected_model_keys = [key for key in available_keys if key in set(requested_keys)]
    if not selected_model_keys:
        raise HTTPException(status_code=400, detail="Select at least one Voyage model.")

    source_id = hashlib.sha256(payload).hexdigest()[:24]
    pdf_path = settings.upload_dir / f"{source_id}.pdf"
    pdf_path.write_bytes(payload)
    job = jobs.create(filename, source_id, selected_model_keys)
    executor.submit(
        process_pdf,
        job["id"],
        pdf_path,
        source_id,
        filename,
        selected_model_keys,
    )
    return job


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found.")
    return job


@app.post("/api/search")
async def search(request: SearchRequest) -> dict:
    if request.mode == "lexical" and request.rerank:
        raise HTTPException(
            status_code=400,
            detail="Voyage reranking is available only for Vector and Hybrid searches.",
        )
    if request.rag and not get_settings().openai_api_key:
        raise HTTPException(
            status_code=400,
            detail="Add an OpenAI API key in Connection settings to enable RAG summaries.",
        )
    try:
        pipelines = await run_in_threadpool(
            compare_pipelines,
            request.query.strip(),
            request.source_id,
            request.mode,
            request.limit,
            request.rerank,
        )
        if request.rag:
            pipelines = await run_in_threadpool(
                add_rag_summaries,
                request.query.strip(),
                pipelines,
            )
    except (RuntimeError, ValueError, PyMongoError) as exc:
        raise service_error(exc) from exc
    return {
        "query": request.query.strip(),
        "source_id": request.source_id,
        "mode": request.mode,
        "reranked": request.rerank,
        "rag": request.rag,
        "pipelines": pipelines,
    }
