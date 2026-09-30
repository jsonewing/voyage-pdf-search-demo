from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit, urlunsplit

from dotenv import set_key
from pymongo import MongoClient
import voyageai

from app.config import ROOT, get_settings, reload_settings
from app.db import close_client
from app.embeddings import close_voyage_client
from app.generation import close_openai_client, create_openai_client


ENV_PATH = ROOT / ".env"
NAMESPACE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")
OPENAI_API_MODES = {"responses", "chat_completions"}


class SetupValidationError(ValueError):
    pass


def _atlas_target(uri: str) -> str:
    if not uri:
        return "Not configured"
    authority = uri.split("@", 1)[-1].split("/", 1)[0].split("?", 1)[0]
    return authority or "Configured Atlas cluster"


def setup_summary() -> dict:
    settings = get_settings()
    atlas_configured = bool(settings.atlas_uri)
    voyage_configured = bool(settings.voyage_api_key)
    openai_configured = bool(settings.openai_api_key)
    return {
        "configured": atlas_configured and voyage_configured,
        "atlas_configured": atlas_configured,
        "voyage_configured": voyage_configured,
        "openai_configured": openai_configured,
        "openai_base_url": settings.openai_base_url,
        "openai_api_mode": settings.openai_api_mode,
        "openai_rag_model": settings.openai_rag_model,
        "atlas_target": _atlas_target(settings.atlas_uri),
        "database": settings.atlas_db,
        "collection": settings.atlas_collection,
        "storage": ".env in this application folder",
    }


def _namespace(value: str, label: str) -> str:
    cleaned = value.strip()
    if not NAMESPACE_PATTERN.fullmatch(cleaned):
        raise SetupValidationError(
            f"{label} must contain only letters, numbers, underscores, or hyphens."
        )
    return cleaned


def _openai_base_url(value: str) -> str:
    cleaned = value.strip().rstrip("/")
    for suffix in ("/chat/completions", "/responses"):
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    parsed = urlsplit(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SetupValidationError("OpenAI-compatible base URL must be a valid HTTP URL.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SetupValidationError(
            "OpenAI-compatible base URL cannot contain credentials, query parameters, or fragments."
        )
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def _openai_model(value: str) -> str:
    cleaned = value.strip()
    if not MODEL_PATTERN.fullmatch(cleaned):
        raise SetupValidationError("OpenAI model name contains unsupported characters.")
    return cleaned


def _validate_atlas(uri: str) -> None:
    if not uri.startswith(("mongodb://", "mongodb+srv://")):
        raise SetupValidationError("Atlas URI must begin with mongodb:// or mongodb+srv://.")
    client = MongoClient(
        uri,
        appname="voyage-pdf-search-demo-setup",
        # This temporary client only validates first-run input, so bound the UI wait.
        serverSelectionTimeoutMS=10_000,
        connectTimeoutMS=10_000,
    )
    try:
        client.admin.command("ping")
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).replace(uri, "<redacted>")
        raise SetupValidationError(f"Atlas connection failed: {detail}") from exc
    finally:
        client.close()


def _validate_voyage(api_key: str) -> None:
    if len(api_key) < 12:
        raise SetupValidationError("Voyage API key appears incomplete.")
    try:
        voyageai.Client(api_key=api_key).embed(
            ["Portable setup connection check"],
            model="voyage-4-lite",
            input_type="query",
            output_dimension=1024,
        )
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).replace(api_key, "<redacted>")
        raise SetupValidationError(f"Voyage API validation failed: {detail}") from exc


def _validate_openai(api_key: str, model: str, base_url: str, api_mode: str) -> None:
    if len(api_key) < 20:
        raise SetupValidationError("OpenAI API key appears incomplete.")
    client = create_openai_client(api_key, base_url)
    try:
        if api_mode == "chat_completions":
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "developer", "content": "Return only the word OK."},
                    {"role": "user", "content": "Validate this local demo connection."},
                ],
                max_completion_tokens=128,
                store=False,
            )
            output_text = response.choices[0].message.content
        else:
            response = client.responses.create(
                model=model,
                instructions="Return only the word OK.",
                input="Validate this local demo connection.",
                max_output_tokens=128,
                store=False,
            )
            output_text = response.output_text
        if not (output_text or "").strip():
            raise RuntimeError("OpenAI returned an empty validation response")
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).replace(api_key, "<redacted>")
        raise SetupValidationError(f"OpenAI API validation failed: {detail}") from exc
    finally:
        client.close()


def _persist_env(values: dict[str, str], env_path: Path = ENV_PATH) -> None:
    pending = env_path.with_name(f"{env_path.name}.pending")
    if env_path.exists():
        shutil.copyfile(env_path, pending)
    else:
        pending.write_text("", encoding="utf-8")
    try:
        for key, value in values.items():
            set_key(str(pending), key, value, quote_mode="always")
        os.chmod(pending, 0o600)
        os.replace(pending, env_path)
    finally:
        pending.unlink(missing_ok=True)


def configure_local(
    atlas_uri: str,
    voyage_api_key: str,
    openai_api_key: str,
    database: str,
    collection: str,
    openai_base_url: str,
    openai_api_mode: str,
    openai_rag_model: str,
) -> dict:
    current = get_settings()
    resolved_uri = atlas_uri.strip() or current.atlas_uri
    resolved_key = voyage_api_key.strip() or current.voyage_api_key
    resolved_openai_key = openai_api_key.strip() or current.openai_api_key
    resolved_openai_base_url = _openai_base_url(
        openai_base_url.strip() or current.openai_base_url
    )
    resolved_openai_mode = openai_api_mode.strip() or current.openai_api_mode
    if resolved_openai_mode not in OPENAI_API_MODES:
        raise SetupValidationError("OpenAI API mode must be responses or chat_completions.")
    resolved_openai_model = _openai_model(
        openai_rag_model.strip() or current.openai_rag_model
    )
    if not resolved_uri or not resolved_key:
        raise SetupValidationError("Atlas URI and Voyage API key are required.")

    resolved_database = _namespace(database, "Database")
    resolved_collection = _namespace(collection, "Collection")
    _validate_atlas(resolved_uri)
    _validate_voyage(resolved_key)
    if resolved_openai_key:
        _validate_openai(
            resolved_openai_key,
            resolved_openai_model,
            resolved_openai_base_url,
            resolved_openai_mode,
        )

    values = {
        "ATLAS_URI": resolved_uri,
        "ATLAS_DB": resolved_database,
        "ATLAS_COLLECTION": resolved_collection,
        "VOYAGE_API_KEY": resolved_key,
        "OPENAI_BASE_URL": resolved_openai_base_url,
        "OPENAI_API_MODE": resolved_openai_mode,
        "OPENAI_RAG_MODEL": resolved_openai_model,
    }
    if resolved_openai_key:
        values["OPENAI_API_KEY"] = resolved_openai_key
    _persist_env(values)
    close_client()
    close_voyage_client()
    close_openai_client()
    reload_settings(values)
    return {**setup_summary(), "message": "Connection verified and saved locally."}
