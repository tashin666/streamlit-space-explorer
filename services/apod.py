import os
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import requests
import streamlit as st
from dateutil.parser import isoparse

APOD_BASE = "https://api.nasa.gov/planetary/apod"
# Earliest APOD date is 1995-06-16
APOD_EARLIEST = date(1995, 6, 16)

logger = logging.getLogger(__name__)

def _api_key() -> str:
    # Fallback to DEMO_KEY if not set (very rate-limited)
    try:
        return st.secrets["api"]["nasa_apod_key"]
    except Exception:
        return os.environ.get("NASA_APOD_KEY", "DEMO_KEY")

@st.cache_data(show_spinner=False, ttl=60 * 60)  # cache for an hour
def get_apod_single(target_date: date, thumbs: bool = True) -> Dict[str, Any]:
    """Fetch single APOD by date; returns JSON. Cached."""
    d = target_date
    if d < APOD_EARLIEST:
        d = APOD_EARLIEST

    params = {
        "api_key": _api_key(),
        "date": d.isoformat(),
        "thumbs": "true" if thumbs else "false"
    }
    logger.info("Fetching APOD for %s", d)
    r = requests.get(APOD_BASE, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

@st.cache_data(show_spinner=False, ttl=60 * 60)
def get_apod_range(start: date, end: date, thumbs: bool = True) -> List[Dict[str, Any]]:
    """Fetch APOD items in a date range (inclusive). Cached."""
    s, e = start, end
    if s < APOD_EARLIEST: s = APOD_EARLIEST
    if e < APOD_EARLIEST: e = APOD_EARLIEST
    if s > e: s, e = e, s  # swap if out of order

    params = {
        "api_key": _api_key(),
        "start_date": s.isoformat(),
        "end_date": e.isoformat(),
        "thumbs": "true" if thumbs else "false"
    }
    logger.info("Fetching APOD range %s -> %s", s, e)
    r = requests.get(APOD_BASE, params=params, timeout=30)
    r.raise_for_status()
    items = r.json()
    # Ensure list
    if isinstance(items, dict):
        items = [items]
    # Sort newest first
    items.sort(key=lambda x: x.get("date", ""), reverse=True)
    return items

def apod_item_id(item: Dict[str, Any]) -> str:
    """Stable ID: use date; APOD is unique per date."""
    return item.get("date", "")

def parse_apod_date(s: str) -> date:
    return isoparse(s).date()
