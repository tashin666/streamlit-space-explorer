import logging
from typing import Any, Dict, List, Optional

import streamlit as st
from pymongo import MongoClient, errors

logger = logging.getLogger(__name__)

# Cache the Mongo client for the session (resource-level cache)
@st.cache_resource(show_spinner=False)
def get_client() -> Optional[MongoClient]:
    try:
        uri = st.secrets["mongo"]["uri"]
        client = MongoClient(uri, tls=True, serverSelectionTimeoutMS=8000)
        # Ping to confirm connection
        client.admin.command("ping")
        logger.info("Connected to MongoDB")
        return client
    except Exception as e:
        logger.error("MongoDB connection failed: %s", e)
        return None

def get_collection():
    client = get_client()
    if not client:
        return None
    db_name = st.secrets["mongo"].get("db_name", "space_gallery")
    col_name = st.secrets["mongo"].get("collection", "favorites")
    db = client[db_name]
    col = db[col_name]
    # Ensure indexes (id per user unique)
    try:
        col.create_index([("user_id", 1), ("apod_date", 1)], unique=True, name="user_date_unique")
    except errors.PyMongoError as e:
        logger.warning("Index creation warning: %s", e)
    return col

def save_favorite(user_id: str, item: Dict[str, Any]) -> bool:
    col = get_collection()
    if col is None:
        return False
    doc = {
        "user_id": user_id,
        "apod_date": item.get("date"),
        "title": item.get("title"),
        "explanation": item.get("explanation"),
        "media_type": item.get("media_type"),
        "url": item.get("url"),
        "hdurl": item.get("hdurl"),
        "thumbnail_url": item.get("thumbnail_url", item.get("thumbnail_url") or item.get("thumbs")),
        "copyright": item.get("copyright"),
        "service_version": item.get("service_version"),
    }
    try:
        col.update_one(
            {"user_id": user_id, "apod_date": item.get("date")},
            {"$set": doc},
            upsert=True
        )
        return True
    except errors.PyMongoError:
        return False


def remove_favorite(user_id: str, apod_date: str) -> bool:
    col = get_collection()
    if col is None:
        return False
    try:
        col.delete_one({"user_id": user_id, "apod_date": apod_date})
        return True
    except errors.PyMongoError:
        return False


def list_favorites(user_id: str) -> List[Dict[str, Any]]:
    col = get_collection()
    if col is None:
        return []
    try:
        return list(col.find({"user_id": user_id}).sort("apod_date", -1))
    except errors.PyMongoError:
        return []
