import logging
import os
import random
import uuid
from datetime import date, timedelta
from typing import Dict, List
import socket
from urllib.parse import urlparse, urlunparse

import streamlit as st

from services.apod import (
    get_apod_single, get_apod_range, apod_item_id, parse_apod_date, APOD_EARLIEST
)
from services import db as dbsvc
from components.share_card import build_share_card

TEN_DAYS_AGO = date.today() - timedelta(days=10)

# ---------------------------
# Logging
# ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
)
logger = logging.getLogger("apod_app")

# ---------------------------
# Page config
# ---------------------------
st.set_page_config(
    page_title="Space Pic of the Day & Archive",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------
# Session bootstrap
# ---------------------------
if "client_id" not in st.session_state:
    st.session_state.client_id = str(uuid.uuid4())  # anonymous per-session ID

if "favorites" not in st.session_state:
    st.session_state.favorites = set()  # local cache of favorite dates

if "last_seen_date" not in st.session_state:
    st.session_state.last_seen_date = date.today()

# ---------------------------
# Sidebar — Theme toggle, Filters
# ---------------------------
st.sidebar.title("⚙️ Controls")

# Your requested live theme toggle (uses private API; fine for demo)
toggle_dark = st.sidebar.toggle("Dark Mode", value=True)
if st.get_option("theme.base") == "light" and toggle_dark:
    st._config.set_option("theme.base", "dark")  # type: ignore # noqa: SLF001
    st.rerun()
elif st.get_option("theme.base") == "dark" and not toggle_dark:
    st._config.set_option("theme.base", "light")  # type: ignore # noqa: SLF001
    st.rerun()

st.sidebar.caption("Tip: This toggle uses a private API—great for demos, may change in future Streamlit versions.")

with st.sidebar.expander("🔐 Status"):
    # Show Mongo connectivity
    col = dbsvc.get_collection()
    st.write("MongoDB:", "Connected ✅" if col is not None else "Not connected ⚠️")

    st.write("NASA Key:", "Provided ✅" if "api" in st.secrets and st.secrets["api"].get("nasa_apod_key") else "Using DEMO_KEY ⚠️")

# ---------------------------
# Header
# ---------------------------
st.markdown(
    """
    <div style="display:flex;align-items:center;gap:12px;">
      <h1 style="margin:0;">🛰️ Space Pic of the Day</h1>
      <span style="opacity:.8;">— Explore APOD, build your personal space gallery</span>
    </div>
    """,
    unsafe_allow_html=True
)

# Tabs for Browse | Archive | Favorites | About
tab_browse, tab_archive, tab_favs, tab_about = st.tabs(["🌟 Browse", "🗃️ Archive", "⭐ Favorites", "ℹ️ About"])

# ---------------------------
# Utilities
# ---------------------------
def celebrate_if_image(item: Dict):
    if item.get("media_type") == "image":
        st.snow()

def make_permalink(target_date: date) -> str:
    base = st.context.url  # e.g., http://localhost:8501
    parsed = urlparse(base)
    netloc = parsed.netloc

    if "localhost" in netloc or "127.0.0.1" in netloc:
        try:
            lan_ip = socket.gethostbyname(socket.gethostname())
            host, _, port = netloc.partition(":")
            netloc = f"{lan_ip}:{port}" if port else lan_ip
        except Exception:
            pass

    rebuilt = parsed._replace(netloc=netloc)
    return urlunparse(rebuilt._replace(query=f"date={target_date.isoformat()}"))

def render_item(item: Dict, wide: bool = True):
    d = item.get("date", "")
    title = item.get("title", "Astronomy Picture of the Day")
    media_type = item.get("media_type", "image")
    url = item.get("hdurl") or item.get("url")
    thumb = item.get("thumbnail_url") or item.get("thumbnail_url") or item.get("url")

    st.subheader(f"{title}  ·  {d}")
    if media_type == "image" and url:
        st.image(url, width='stretch')
    elif media_type == "video" and url:
        st.video(url)
    else:
        st.info("No preview available.")

    with st.expander("📄 Description"):
        st.write(item.get("explanation", ""))
        if item.get("copyright"):
            st.caption(f"© {item.get('copyright')}")

    # Actions row
    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    user_id = st.session_state.client_id

    if c1.button("⭐ Favorite", key=f"fav_btn_{d}"):
        ok = dbsvc.save_favorite(user_id, item)
        if ok:
            st.session_state.favorites.add(d)
            st.toast("Saved to favorites", icon="⭐")
            celebrate_if_image(item)
        else:
            st.toast("Could not save favorite (DB issue)", icon="⚠️")

    if c2.button("🗑️ Remove", key=f"rm_btn_{d}"):
        ok = dbsvc.remove_favorite(user_id, d)
        if ok and d in st.session_state.favorites:
            st.session_state.favorites.remove(d)
        st.toast("Removed (if existed)", icon="🗑️")

    permalink = f"{st.request.url}?date={d}" if hasattr(st, "request") and hasattr(st.request, "url") else make_permalink(parse_apod_date(d))

    # Use a different widget key AND a different session_state key to avoid conflicts
    if c3.button("🖼️ Export Share Card", key=f"export_btn_{d}"):
        try:
            buf = build_share_card(item, permalink=permalink)
            st.session_state[f"cardbuf_{d}"] = buf  # <-- session key distinct from widget key
            st.toast("Share card ready below ⬇️", icon="🖼️")
        except Exception as e:
            st.error(f"Share card failed: {e}")

    # Only show download if buffer exists and is bytes-like
    ss_key = f"cardbuf_{d}"
    if ss_key in st.session_state and hasattr(st.session_state[ss_key], "read"):
        buf = st.session_state[ss_key]
        st.download_button(
            "⬇️ Download Card (PNG)",
            data=buf,
            file_name=f"apod_{d}.png",
            mime="image/png",
            key=f"dl_btn_{d}"
        )

# ---------------------------
# 🌟 Browse tab (Today / Specific Date / Random)
# ---------------------------
with tab_browse:
    st.write("Pick a date or let fate decide. You can also share a link to a specific date via the URL query parameter.")

    # read ?date=YYYY-MM-DD
    if "browse_date" not in st.session_state:
        qp = st.query_params
        if "date" in qp:
            try:
                st.session_state.browse_date = parse_apod_date(qp["date"])
            except Exception:
                st.session_state.browse_date = TEN_DAYS_AGO
        else:
            st.session_state.browse_date = TEN_DAYS_AGO

    # Columns first
    choose_col1, choose_col2, choose_col3 = st.columns([2, 1, 1])

    # ---- Handle Random button *before* rendering the date_input ----
    with choose_col2:
        if st.button("🎲 Random Day", key="rand_btn", use_container_width=True):
            days = (TEN_DAYS_AGO - APOD_EARLIEST).days
            rnd = APOD_EARLIEST + timedelta(days=random.randint(0, days))
            st.query_params.update({"date": rnd.isoformat()})
            st.rerun()  # stop here; next run will pick up the new query param

    # ---- Sync state from query params BEFORE creating the widget ----
    qp = st.query_params
    if "date" in qp:
        try:
            st.session_state["browse_date"] = parse_apod_date(qp["date"])
        except Exception:
            st.session_state["browse_date"] = TEN_DAYS_AGO
    else:
        st.session_state.setdefault("browse_date", TEN_DAYS_AGO)

    # ---- Now render the date_input bound to session_state ----
    with choose_col1:
        st.date_input(
            "Choose a date",
            value=st.session_state["browse_date"],
            min_value=APOD_EARLIEST,
            max_value=TEN_DAYS_AGO,
            format="YYYY-MM-DD",
            key="browse_date",
        )

    with choose_col3:
        if st.button("🔗 Copy Link", key="copy_btn", use_container_width=True):
            deep_link = f"{st.context.url.split('?')[0]}?date={st.session_state['browse_date'].isoformat()}"
            st.text_input("Link (Ctrl/Cmd+C to copy)", value=deep_link, key=f"link_{st.session_state['browse_date']}", label_visibility="collapsed")
            st.markdown(f"[Open link in a new tab]({deep_link})")
            st.toast("Link generated below. Copy from the field.", icon="🔗")

    # ---- Fetch then render (keep fetch/render try/except separate) ----
    with st.status("Fetching APOD…", expanded=False) as status:
        item = None
        try:
            item = get_apod_single(st.session_state["browse_date"])
            status.update(label=f"Loaded APOD for {st.session_state['browse_date']}", state="complete")
        except Exception as e:
            status.update(label=f"Failed to load APOD: {e}", state="error")

    if item:
        try:
            render_item(item)
        except Exception as e:
            st.error(f"Render failed: {e}")
# ---------------------------
# 🗃️ Archive tab (range search, masonry layout)
# ---------------------------
with tab_archive:
    st.write("Search a date range and browse results in a responsive masonry layout.")
    with st.form("archive_form", clear_on_submit=False):
        colA, colB, colC = st.columns(3)
        with colA:
            start_date = st.date_input("Start", value=date.today() - timedelta(days=14), min_value=APOD_EARLIEST, max_value=date.today(), format="YYYY-MM-DD")
        with colB:
            end_date = st.date_input("End", value=date.today(), min_value=APOD_EARLIEST, max_value=date.today(), format="YYYY-MM-DD")
        with colC:
            random_count = st.number_input("Or random N", min_value=0, max_value=30, value=0, help="Leave 0 to ignore. If >0, ignores the date range and fetches N random APODs.")
        submitted = st.form_submit_button("Search")

    items: List[Dict] = []
    if submitted:
        if random_count and random_count > 0:
            # NASA APOD supports ?count=N
            import requests
            with st.spinner(f"Fetching {random_count} random APODs…"):
                r = requests.get(
                    "https://api.nasa.gov/planetary/apod",
                    params={"api_key": os.environ.get("NASA_APOD_KEY", st.secrets.get("api", {}).get("nasa_apod_key", "DEMO_KEY")),
                            "count": int(random_count), "thumbs": "true"},
                    timeout=30
                )
                r.raise_for_status()
                items = r.json()
                if isinstance(items, dict):
                    items = [items]
        else:
            with st.spinner("Fetching range…"):
                items = get_apod_range(start_date, end_date)

        if not items:
            st.info("No items found.")
        else:
            # Masonry: 3 columns, round-robin
            cols = st.columns(3, gap="small")
            for idx, it in enumerate(items):
                with cols[idx % 3].container(border=True):
                    # Compact card
                    d = it.get("date", "")
                    title = it.get("title", "APOD")
                    media_type = it.get("media_type", "image")
                    url = it.get("thumbnail_url") or it.get("url") or it.get("hdurl")
                    st.caption(d)
                    st.markdown(f"**{title}**")
                    if media_type == "image" and url:
                        st.image(url, width='stretch')
                    elif media_type == "video" and url:
                        st.video(url)
                    else:
                        st.info("No preview.")
                    if st.button("Open", key=f"open_{d}"):
                        st.query_params.update({"date": d})
                        st.switch_page("") if hasattr(st, "switch_page") else st.rerun()

# ---------------------------
# ⭐ Favorites tab (session + MongoDB)
# ---------------------------
with tab_favs:
    st.write("Your saved favorites (persisted in MongoDB if configured).")
    user_id = st.session_state.client_id
    docs = dbsvc.list_favorites(user_id)
    if not docs:
        st.info("No favorites yet. Add some from the Browse or Archive tabs.")
    else:
        cols = st.columns(3, gap="small")
        for i, doc in enumerate(docs):
            with cols[i % 3].container(border=True):
                d = doc.get("apod_date", "")
                title = doc.get("title", "APOD")
                url = doc.get("hdurl") or doc.get("url") or doc.get("thumbnail_url")
                st.caption(d)
                st.markdown(f"**{title}**")
                if url:
                    st.image(url, width='stretch')
                if st.button("Open", key=f"fav_open_{d}"):
                    st.query_params.update({"date": d})
                    st.rerun()
                if st.button("Remove", key=f"fav_rm_{d}"):
                    dbsvc.remove_favorite(user_id, d)
                    st.rerun()

# ---------------------------
# ℹ️ About tab
# ---------------------------
with tab_about:
    st.write("""
    **Space Pic of the Day & Archive** showcases NASA's APOD using Streamlit:
    - `st.date_input`, `st.tabs`, `st.form`, `st.columns`, `st.expander`, `st.toast`, `st.snow`, `st.status`, `st.download_button`
    - Caching with `st.cache_data` / `st.cache_resource`
    - MongoDB persistence (favorites), with indexes
    - Shareable cards (PNG) with title/date/QR
    - Query-param deep links and a live Dark/Light toggle
    """)
    st.caption("APOD © NASA | Built for learning and to impress recruiters with practical Streamlit patterns.")
