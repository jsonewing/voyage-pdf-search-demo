from __future__ import annotations

from functools import lru_cache

from pymongo import MongoClient
from pymongo.collection import Collection

from app.config import get_settings


@lru_cache
def get_client() -> MongoClient:
    settings = get_settings()
    settings.validate()
    # One process-wide client keeps the Atlas connection pool warm for this demo.
    return MongoClient(
        settings.atlas_uri,
        appname="voyage-pdf-search-demo",
        serverSelectionTimeoutMS=10_000,
        connectTimeoutMS=10_000,
    )


def get_collection() -> Collection:
    settings = get_settings()
    return get_client()[settings.atlas_db][settings.atlas_collection]


def close_client() -> None:
    if get_client.cache_info().currsize:
        get_client().close()
        get_client.cache_clear()
