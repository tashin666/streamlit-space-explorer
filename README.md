<div align="center">
  <h1>🛰️ Streamlit Space Explorer</h1>
  <p><i>Explore NASA data in one elegant app: APOD with share cards & favorites, a NASA Images search gallery, a live Earth events map (EONET), and a Near-Earth Objects mini-terminal — built with Streamlit</i></p>
</div>

<br>

<div align="center">
  <a href="https://github.com/brej-29/streamlit-space-explorer">
    <img alt="Last Commit" src="https://img.shields.io/github/last-commit/brej-29/streamlit-space-explorer">
  </a>
  <img alt="Language" src="https://img.shields.io/badge/Language-Python-blue">
  <img alt="Framework" src="https://img.shields.io/badge/Framework-Streamlit-ff4b4b">
  <img alt="APIs" src="https://img.shields.io/badge/APIs-NASA%20APOD%20%7C%20Images%20API%20%7C%20EONET%20v3%20%7C%20NeoWs-8A2BE2">
  <img alt="Database" src="https://img.shields.io/badge/DB-MongoDB-brightgreen">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-black">
</div>

<div align="center">
  <br>
  <b>Built with the tools and technologies:</b>
  <br><br>
  <code>Python</code> | <code>Streamlit</code> | <code>Pandas</code> | <code>PyDeck</code> | <code>Requests</code> | <code>Pillow</code> | <code>qrcode</code> | <code>PyMongo</code>
</div>

---

## **Screenshot**

<!-- Replace with your own screenshots -->
<img width="1260" height="913" alt="image" src="https://github.com/user-attachments/assets/563d8d6f-54d9-4077-b71f-276f980847e0" />

<img width="1260" height="914" alt="image" src="https://github.com/user-attachments/assets/128329da-0359-419f-beff-09207b41ae1e" />

<img width="1256" height="919" alt="image" src="https://github.com/user-attachments/assets/4fd436e5-3418-407c-9ad5-9bb2e61a82c2" />

<img width="1259" height="919" alt="image" src="https://github.com/user-attachments/assets/a70802fc-a377-4402-984f-f8c34a3c4f85" />

---

## **Table of Contents**
* [Overview](#overview)
* [Features](#features)
* [Getting Started](#getting-started)
    * [Project Structure](#project-structure)
    * [Prerequisites](#prerequisites)
    * [Installation](#installation)
    * [Configuration](#configuration)
    * [Usage](#usage)
* [Design Notes](#design-notes)
* [Limitations](#limitations)
* [Roadmap](#roadmap)
* [License](#license)
* [Contact](#contact)
* [References](#references)

---

## **Overview**

**Streamlit Space Explorer** is a recruiter-friendly Streamlit app showcasing practical API integration, caching, and persistence:

- **APOD (Astronomy Picture of the Day)**: browse by date, random picks; export branded share cards; save favorites to MongoDB. 
- **Space Search Gallery (NASA Images & Video Library)**: search 140k+ public assets (no key); open full-resolution originals.
- **Earth Events (EONET v3)**: live natural events (wildfires, storms, volcanoes, sea/ice) with a map and filters. 
- **NEOs This Week (NeoWs)**: digest of near-Earth objects with date search, sizes, miss distance (km/LD), and speed. 

Secrets are stored via **Streamlit `secrets.toml`** locally and through **Streamlit Community Cloud** on deploy. 

<br>

### **Project Highlights**
- **Polished UX**: sidebar page switcher, tabs, expander help, toasts, dark/light toggle, deep links via query params, and PNG share-card export.
- **Robust engineering**: `@st.cache_data` and `@st.cache_resource`, typed helpers, graceful errors, MongoDB indexes, and input validation.
- **Clean architecture**: `services/` for APIs & DB, `components/` for share-card, single entrypoint `app.py`.

---

## **Features**

- 🖼️ **APOD**: daily image/video, description, copyright; share-card export (QR + overlay); MongoDB favorites.
- 🔎 **NASA Images Gallery**: query by keyword; preview grid; open originals; optional favorite save.
- 🌍 **EONET (v3)**: filter by category, status (open/closed), and look-back window; map and list with links to details.
- 🪨 **NeoWs**: choose a single date or ≤7-day range; table with **Potentially Hazardous?**, **diameter min/max (m)**, **closest time**, **miss distance (km/LD)**, **relative speed (km/s)**, and **More info** link; inline glossary.
- 🌓 **Theme toggle**: runtime dark/light switch (demo-friendly).
- 💾 **Persistence**: favorites stored in MongoDB Atlas with unique index (`user_id`, `apod_date`).
- 🚀 **Performance**: strategic caching and pagination; requests tuned with timeouts; minimal reruns.

---

## **Getting Started**

### **Project Structure**

    streamlit-space-explorer/
    ├─ app.py
    ├─ components/
    │  └─ share_card.py
    ├─ services/
    │  ├─ apod.py
    │  ├─ db.py
    ├─ .streamlit/
    │  ├─ config.toml
    │  └─ secrets.toml          # local only; do NOT commit
    ├─ requirements.txt
    └─ README.md

### **Prerequisites**
- Python **3.9+**
- **NASA API key** (free) for APOD/NeoWs/EONET if rate limits apply — generate at api.nasa.gov.
- **MongoDB Atlas** free cluster (optional; used for favorites).

### **Installation**
1) Create & activate a virtual environment:

        python -m venv .venv
        # Windows:
        .venv\Scripts\activate
        # macOS/Linux:
        source .venv/bin/activate

2) Install dependencies:

        pip install -r requirements.txt

### **Configuration**

Create `.streamlit/secrets.toml` (local) and paste your keys (example):

        [api]
        nasa_apod_key = "YOUR_NASA_KEY"

        [mongo]
        uri        = "mongodb+srv://apod_app:YOUR_PASSWORD@cluster0.xxxxx.mongodb.net"
        db_name    = "space_gallery"
        collection = "favorites"

- Access in code with `st.secrets["section"]["key"]` or attribute style (`st.secrets.api.nasa_apod_key`). 
- On **Streamlit Community Cloud**, paste the same TOML content in your app’s **Secrets** (do not commit the file).

### **Usage**

Run locally:

        streamlit run app.py

Workflow:
1. Use the sidebar **Pages** to switch: **APOD**, **Space Search Gallery**, **Earth Events**, **NEOs This Week**.
2. In **APOD**, pick a date or random → preview → export a share card → ⭐ to save in favorites.
3. In **Gallery**, search e.g., “Aurora” → open original → (optional) save as favorite.
4. In **Earth Events**, filter and explore on the map; open event detail links.
5. In **NEOs**, search by single date or a ≤7-day range; sort table; open “More info”.

---

## **Design Notes**

- **APIs chosen for broad appeal & low friction**
  - **APOD**: iconic daily image/video, small JSON schema; great for demos.
  - **NASA Images & Video Library**: no key required; `/search` and `/asset/{nasa_id}` cover most gallery needs.
  - **EONET v3**: human-readable categories & events; works well with maps.
  - **NeoWs**: approachable feed with dates and close-approach details (≤7-day windows).

- **Secrets & deployment**  
  Native `secrets.toml` keeps keys out of your repo locally, and Streamlit Cloud provides a secure Secrets UI on deploy. 

- **Caching strategy**  
  `@st.cache_data` for pure fetch/transform; `@st.cache_resource` for the MongoDB client. This keeps UI snappy while avoiding redundant connections.

- **Share card design**  
  `Pillow` + `qrcode` to render a social-ready PNG (1200×630) with title/date/caption overlay and a QR deep link.

---

## **Limitations**
- **Rate limits**: free NASA keys (and `DEMO_KEY`) may throttle; APOD/NeoWs/EONET calls include timeouts and user-facing errors. :contentReference[oaicite:13]{index=13}
- **Data availability**: some dates have videos (APOD) or no imagery (gallery queries) → UI handles fallbacks gracefully.
- **Local QR links**: on `localhost`, QR deep links are rewritten to LAN IP for phone testing; in Cloud they use the public URL.

---

## **Roadmap**
- Gallery favorites with tags/notes (Mongo).
- EONET cluster markers & time slider.
- NEOs: hazard filters, color-coded LD risk bands, mini charts.
- Optional EPIC “Blue Marble Today” page.

---

## **License**
This project is licensed under the MIT License. See the `LICENSE` file for details.

---

## **Contact**
For questions or feedback:
- LinkedIn: https://www.linkedin.com/in/brejesh-balakrishnan-7855051b9/
- GitHub: https://github.com/brej-29

---

## **References**
- **NASA API Portal** (APIs & key registration): https://api.nasa.gov/
- **NASA Image & Video Library API** (search & asset): example collection docs / Postman overview.
- **EONET v3** (events, categories): https://eonet.gsfc.nasa.gov/docs/v3 and live categories endpoint.
- **Asteroids NeoWs** (feed, lookup, browse): dataset/API description. https://data.nasa.gov/dataset/asteroids-neows-api
- **Streamlit secrets** (secrets.toml & Cloud secrets): docs pages.
