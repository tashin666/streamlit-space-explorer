import logging
import os
import random
import uuid
from datetime import date, timedelta
from typing import Dict, List
import socket
from urllib.parse import urlparse, urlunparse
import pandas as pd
import pydeck as pdk
from datetime import datetime
import streamlit as st
import requests

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

# ---- SIDEBAR PAGES SWITCHER (place before the Controls section) ----
st.sidebar.title("🧭 Pages")
PAGE = st.sidebar.radio(
    "Go to",
    ["APOD", "Space Search Gallery", "Earth Events (EONET)", "NEOs This Week"],
    index=0,
    key="nav_page"
)
st.sidebar.markdown("---")  # separator before your existing Controls

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

def _clamp_neows_window(start: date, end: date) -> tuple[date, date]:
    """NeoWs feed supports windows up to 7 days. Normalize order and clamp to 7 days."""
    if start > end:
        start, end = end, start
    if (end - start).days > 6:
        end = start + timedelta(days=6)
    return start, end

def page_gallery():
    st.header("🖼️ Space Search Gallery")
    q = st.text_input("Search NASA media", value="nebula", placeholder="Try: aurora, Saturn rings, Apollo 11")
    colA, colB = st.columns([1, 3])
    with colA:
        page = st.number_input("Page", min_value=1, value=1, step=1)
    with colB:
        media_type = st.selectbox("Media type", ["image", "video", "audio"], index=0)

    if st.button("Search", type="primary"):
        st.session_state["gallery_q"] = q
        st.session_state["gallery_page"] = int(page)
        st.session_state["gallery_media_type"] = media_type
        st.rerun()

    q = st.session_state.get("gallery_q", q)
    page = int(st.session_state.get("gallery_page", page))
    media_type = st.session_state.get("gallery_media_type", media_type)

    with st.spinner("Searching…"):
        data = nasa_images_search(q=q, page=page, media_type=media_type)

    items = (data.get("collection", {}) or {}).get("items", [])
    if not items:
        st.info("No results. Try a different query.")
        return

    cols = st.columns(3, gap="small")
    for i, it in enumerate(items):
        data_block = (it.get("data") or [{}])[0]
        title = data_block.get("title", "Untitled")
        nasa_id = data_block.get("nasa_id", "")
        desc = data_block.get("description", "") or ""
        links = it.get("links") or []
        thumb = None
        for ln in links:
            if ln.get("rel") == "preview" or ln.get("render") == "image":
                thumb = ln.get("href"); break
        with cols[i % 3].container(border=True):
            st.caption(nasa_id)
            st.markdown(f"**{title}**")
            if thumb:
                st.image(thumb, width='stretch')
            st.write(desc[:180] + ("…" if len(desc) > 180 else ""))
            c1, c2 = st.columns(2)
            if c1.button("Open", key=f"gal_open_{nasa_id}"):
                assets = nasa_images_assets(nasa_id)
                hrefs = [i.get("href") for i in (assets.get("collection", {}) or {}).get("items", []) if i.get("href")]
                # Heuristic: prefer the largest JPG/PNG
                original = next((h for h in hrefs if h.lower().endswith((".png", ".jpg", ".jpeg")) and "orig" in h.lower()), hrefs[-1] if hrefs else None)
                if original:
                    st.image(original, width='stretch')
                    st.link_button("Open Original", original)
            if c2.button("⭐ Favorite", key=f"gal_fav_{nasa_id}"):
                doc = {
                    "date": datetime.utcnow().date().isoformat(),
                    "title": title,
                    "url": thumb,
                    "hdurl": thumb,
                    "media_type": "image",
                    "explanation": f"NASA Image Library: {title}",
                }
                ok = dbsvc.save_favorite(st.session_state.client_id, doc)
                st.toast("Saved to favorites" if ok else "Save failed", icon="⭐" if ok else "⚠️")


# ---- PAGE: Earth Events (EONET) ----
def page_eonet():
    st.header("🌍 Live Natural Events (EONET)")
    cats_json = eonet_categories()
    cats = cats_json.get("categories", [])
    cat_map = {c["title"]: c["id"] for c in cats}
    colA, colB, colC = st.columns([2, 1, 1])
    with colA:
        chosen_cat = st.selectbox("Category (optional)", ["All"] + list(cat_map.keys()))
    with colB:
        days = st.number_input("Days (lookback)", min_value=1, max_value=60, value=10, step=1)
    with colC:
        status = st.selectbox("Status", ["open", "closed"], index=0)

    with st.spinner("Loading events…"):
        cat_id = None if chosen_cat == "All" else cat_map[chosen_cat]
        data = eonet_events(status=status, days=int(days), category=cat_id)

    events = data.get("events", [])
    if not events:
        st.info("No events for the selected filters.")
        return

    # Build map dataframe
    rows = []
    for ev in events:
        title = ev.get("title", "Event")
        cat_title = (ev.get("categories") or [{}])[0].get("title", "")
        link = (ev.get("links") or [{}])[0].get("href", "")
        # grab last geometry point
        geos = ev.get("geometry") or []
        if not geos: 
            continue
        coords = geos[-1].get("coordinates", [])
        if len(coords) >= 2:
            lon, lat = coords[0], coords[1]
            rows.append({"title": title, "category": cat_title, "lon": lon, "lat": lat, "link": link})

    df = pd.DataFrame(rows)
    if df.empty:
        st.info("No mappable events.")
        return

    st.map(df[["lat", "lon"]], zoom=1)  # quick base map

    # PyDeck layer for nicer styling
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[lon, lat]",
        get_radius=400000,
        get_color=[255, 140, 0, 140],
        pickable=True,
    )
    view = pdk.ViewState(latitude=0, longitude=0, zoom=0.8)
    st.pydeck_chart(pdk.Deck(map_style=None, initial_view_state=view, layers=[layer], tooltip={"text": "{title}\n{category}"}))

    st.subheader("Events")
    for _, r in df.iterrows():
        with st.container(border=True):
            st.markdown(f"**{r['title']}** · {r['category']}")
            st.write(f"Location: {r['lat']:.2f}, {r['lon']:.2f}")
            if r["link"]:
                st.link_button("Details", r["link"])


# ---- PAGE: NEOs This Week (NeoWs) ----
# --- Replace the whole page_neows() with this version ---
def page_neows():
    st.header("🪨 Near-Earth Objects")

    # ---- Search UI ----
    with st.form("neows_search", clear_on_submit=False):
        mode = st.segmented_control("Search by", options=["Single date", "Date range"], default="Single date")
        today = date.today()
        default_start = today - timedelta(days=6)
        col1, col2, col3 = st.columns([1.4, 1.4, 1])
        if mode == "Single date":
            with col1:
                single_day = st.date_input("Date", value=today, max_value=today, format="YYYY-MM-DD", key="neows_single")
        else:
            with col1:
                start = st.date_input("Start date", value=default_start, max_value=today, format="YYYY-MM-DD", key="neows_start")
            with col2:
                end = st.date_input("End date", value=today, max_value=today, format="YYYY-MM-DD", key="neows_end")

        with col3:
            submitted = st.form_submit_button("Search", type="primary", width='stretch')

    # Default (first render) – last 7 days
    if not submitted and "neows_last" not in st.session_state:
        st.session_state.neows_last = (today - timedelta(days=6), today)

    # Resolve chosen window
    if submitted:
        if mode == "Single date":
            start = end = st.session_state["neows_single"]
        else:
            start = st.session_state["neows_start"]
            end = st.session_state["neows_end"]
        start, end = _clamp_neows_window(start, end)
        st.session_state.neows_last = (start, end)
    else:
        start, end = st.session_state.neows_last

    # ---- Fetch ----
    with st.status(f"Fetching NEOs {start} → {end} …", expanded=False) as status:
        try:
            data = neows_feed(start, end)
            status.update(state="complete", label=f"Loaded NEOs for {start} → {end}")
        except Exception as e:
            status.update(state="error", label=f"NeoWs error: {e}")
            st.error("Could not load NEO feed. Try a smaller window (≤7 days) or check your API key in secrets.")
            return

    near = (data or {}).get("near_earth_objects", {})
    if not near:
        st.info("No objects returned for that window.")
        return

    # ---- Flatten rows ----
    rows: list[dict] = []
    for day, objs in sorted(near.items()):
        for o in objs:
            name = o.get("name", "")
            hazardous = o.get("is_potentially_hazardous_asteroid", False)
            est = o.get("estimated_diameter", {}).get("meters", {})
            dmin = est.get("estimated_diameter_min")
            dmax = est.get("estimated_diameter_max")
            approaches = o.get("close_approach_data", [])
            if approaches:
                ca = approaches[0]  # first is usually the relevant Earth pass in feed
                when = ca.get("close_approach_date_full") or ca.get("close_approach_date")
                dist_km = float(ca.get("miss_distance", {}).get("kilometers", "0"))
                vel_kps = float(ca.get("relative_velocity", {}).get("kilometers_per_second", "0"))
                ld = dist_km / 384000.0  # LD ≈ 384,000 km
                url = o.get("nasa_jpl_url") or o.get("links", {}).get("self")
            else:
                when, dist_km, vel_kps, ld, url = "", 0.0, 0.0, 0.0, o.get("links", {}).get("self")

            rows.append({
                "date": day,
                "name": name,
                "hazardous": hazardous,
                "diameter_m_min": dmin,
                "diameter_m_max": dmax,
                "closest_time": when,
                "miss_km": dist_km,
                "miss_ld": ld,
                "speed_km_s": vel_kps,
                "more": url
            })

    df = pd.DataFrame(rows)
    if df.empty:
        st.info("No objects to display.")
        return

    # ---- Table ----
    st.caption("Tip: Click column headers to sort.")
    st.dataframe(
        df.sort_values(["date", "miss_km"], ascending=[False, True]).reset_index(drop=True),
        width='stretch',
        hide_index=True,
        column_config={
            "hazardous": st.column_config.CheckboxColumn("Potentially hazardous?"),
            "diameter_m_min": st.column_config.NumberColumn("Estimated diameter (min, m)", format="%.0f"),
            "diameter_m_max": st.column_config.NumberColumn("Estimated diameter (max, m)", format="%.0f"),
            "miss_km": st.column_config.NumberColumn("Miss distance (km)", format="%.0f"),
            "miss_ld": st.column_config.NumberColumn("Miss distance (LD)", format="%.2f"),
            "speed_km_s": st.column_config.NumberColumn("Relative speed (km/s)", format="%.2f"),
            "more": st.column_config.LinkColumn("More info"),
        },
    )

    # ---- Explanations ----
    with st.expander("What do these values mean?"):
        st.markdown(
            """
- **Estimated diameter (min/max)** — range derived from brightness with assumed albedo bounds (NeoWs `estimated_diameter`).  
- **Potentially hazardous?** — objects with **MOID < 0.05 AU** and **H ≤ 22** are flagged PHAs (size ≳ 140 m).  
- **Closest approach time** — modeled moment of closest approach for that pass.  
- **Miss distance (km)** — closest separation between centers during the pass.  
- **Miss distance (LD)** — **Lunar Distance**, ~384,000 km (Earth–Moon average).  
- **Relative speed (km/s)** — object speed relative to Earth at closest approach.
"""
        )


@st.cache_data(show_spinner=False, ttl=60*15)
def nasa_images_search(q: str, page: int = 1, media_type: str = "image") -> dict:
    # NASA Image & Video Library search (no API key needed)
    r = requests.get(
        "https://images-api.nasa.gov/search",
        params={"q": q, "page": page, "media_type": media_type},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()

@st.cache_data(show_spinner=False, ttl=60*15)
def nasa_images_assets(nasa_id: str) -> dict:
    r = requests.get(f"https://images-api.nasa.gov/asset/{nasa_id}", timeout=20)
    r.raise_for_status()
    return r.json()

@st.cache_data(show_spinner=False, ttl=60*10)
def eonet_events(status: str = "open", days: int | None = None, category: int | None = None) -> dict:
    # EONET v3 — status=open|closed; optional days + category filtering
    params = {"status": status}
    if days:
        params["days"] = days
    if category:
        params["category"] = category
    r = requests.get("https://eonet.gsfc.nasa.gov/api/v3/events", params=params, timeout=20)
    r.raise_for_status()
    return r.json()

@st.cache_data(show_spinner=False, ttl=60*20)
def eonet_categories() -> dict:
    r = requests.get("https://eonet.gsfc.nasa.gov/api/v3/categories", timeout=20)
    r.raise_for_status()
    return r.json()

@st.cache_data(show_spinner=False, ttl=60*20)
def neows_feed(start_date: date, end_date: date) -> dict:
    # Feed supports up to 7 days window
    key = (st.secrets.get("api", {}) or {}).get("nasa_apod_key", os.getenv("NASA_APOD_KEY", "DEMO_KEY"))
    r = requests.get(
        "https://api.nasa.gov/neo/rest/v1/feed",
        params={"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "api_key": key},
        timeout=25,
    )
    r.raise_for_status()
    return r.json()

# ---------------------------
# Header
# ---------------------------
# ---- ROUTER ----
if PAGE == "APOD":
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
    # ---- PAGE: NASA Image & Video Library (Space Search Gallery) ----
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
            if st.button("🎲 Random Day", key="rand_btn", width='stretch'):
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
                min_value=APOD_EARLIEST,
                max_value=TEN_DAYS_AGO,
                format="YYYY-MM-DD",
                key="browse_date",
            )

        with choose_col3:
            if st.button("🔗 Copy Link", key="copy_btn", width='stretch'):
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
elif PAGE == "Space Search Gallery":
    page_gallery()
elif PAGE == "Earth Events (EONET)":
    page_eonet()
elif PAGE == "NEOs This Week":
    page_neows()