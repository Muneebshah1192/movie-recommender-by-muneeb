# app.py
import pickle
import pandas as pd
import streamlit as st
import requests
import random
import json
import math
from io import StringIO

# ====== CONFIG ======
API_KEY = "8265bd1679663a7ea12ac168da84d2e8"  # keep as-is or replace with your own
PLACEHOLDER = "https://via.placeholder.com/500x750.png?text=No+Image"

# ====== PAGE ======
st.set_page_config(page_title="🎬 Movie Recommender By Syed", page_icon="🎥", layout="wide")
st.markdown(
    "<h1 style='text-align:center;'>🎬 Muneeb's Movie Recommender </h1>",
    unsafe_allow_html=True,
)
st.write("Select a movie, click **Show Recommendations**, and click **Add to Favorites ❤️** on any card to save it.")

# ====== CACHING HELPERS ======
@st.cache_data(show_spinner=False)
def fetch_json(url: str):
    try:
        r = requests.get(url, timeout=6)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}

@st.cache_data(show_spinner=False)
def fetch_movie_details(movie_id: int):
    """Fetch movie details, poster, credits and trailer (cached)."""
    base = "https://api.themoviedb.org/3/movie/{}?api_key={}&language=en-US"
    data = fetch_json(base.format(movie_id, API_KEY))
    # poster
    poster_path = data.get("poster_path")
    poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else PLACEHOLDER
    # overview, rating, release
    overview = data.get("overview", "No description available.")
    release_date = data.get("release_date", "")
    year = release_date.split("-")[0] if release_date else "N/A"
    rating = data.get("vote_average", "N/A")
    genres = [g["name"] for g in data.get("genres", [])]
    language = (data.get("original_language") or "N/A").upper()

    # credits
    credits = fetch_json(f"https://api.themoviedb.org/3/movie/{movie_id}/credits?api_key={API_KEY}&language=en-US")
    cast = [c["name"] for c in credits.get("cast", [])[:3]] if credits else []
    director = next((c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"), "Unknown") if credits else "Unknown"

    # videos -> trailer
    videos = fetch_json(f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={API_KEY}&language=en-US")
    trailer = None
    for v in videos.get("results", []):
        if v.get("site") == "YouTube" and v.get("type") == "Trailer":
            trailer = f"https://www.youtube.com/watch?v={v.get('key')}"
            break

    # tmdb page fallback
    tmdb_url = f"https://www.themoviedb.org/movie/{movie_id}"

    return {
        "id": int(movie_id),
        "title": data.get("title", "Unknown"),
        "poster": poster,
        "overview": overview,
        "rating": rating,
        "year": year,
        "genres": genres,
        "language": language,
        "cast": cast,
        "director": director,
        "trailer": trailer,
        "tmdb": trailer or tmdb_url,
    }

# ====== LOAD DATA ======
movies_dict = pickle.load(open("movies_dict.pkl", "rb"))
movies = pd.DataFrame(movies_dict)  # ensure DataFrame
similarity = pickle.load(open("similarity.pkl", "rb"))

# session_state init
if "favorites" not in st.session_state:
    # store favorites as dict keyed by movie_id (string) to avoid duplicates
    st.session_state.favorites = {}

# show small top status message for last action
if "last_action" in st.session_state:
    action = st.session_state.last_action
    if action:
        st.success(action)
    st.session_state.last_action = None

# ====== SIDEBAR ======
st.sidebar.header("Options & Favorites")
top_n = st.sidebar.slider("Number of recommendations", min_value=5, max_value=12, value=5, step=1)
cols_per_row = st.sidebar.slider("Cards per row (grid width)", min_value=1, max_value=5, value=4)
surprise = st.sidebar.button("🎲 Surprise me (random movie)")
if st.sidebar.button("💾 Save Favorites to disk"):
    try:
        with open("favorites.json", "w", encoding="utf-8") as f:
            json.dump(list(st.session_state.favorites.values()), f, ensure_ascii=False, indent=2)
        st.sidebar.success("Favorites saved to favorites.json")
    except Exception as e:
        st.sidebar.error(f"Save failed: {e}")

if st.sidebar.button("📂 Load Favorites from disk"):
    try:
        with open("favorites.json", "r", encoding="utf-8") as f:
            loaded = json.load(f)
        st.session_state.favorites = {str(item["id"]): item for item in loaded}
        st.sidebar.success("Loaded favorites from favorites.json")
    except Exception as e:
        st.sidebar.error(f"Load failed: {e}")

show_favs = st.sidebar.checkbox("Show Favorites panel", value=False)

# Download favorites button (visible when favorites exist)
def favorites_csv_bytes():
    df = pd.DataFrame(list(st.session_state.favorites.values()))
    return df.to_csv(index=False).encode("utf-8")

if st.session_state.favorites:
    st.sidebar.download_button("📥 Download Favorites CSV", favorites_csv_bytes(), file_name="favorites.csv", mime="text/csv")

# ====== MOVIE SELECT ======
movie_list = movies["title"].values.tolist()
if surprise:
    selected_movie = random.choice(movie_list)
    st.sidebar.success(f"Surprise: {selected_movie}")
else:
    selected_movie = st.selectbox("🎥 Select a movie ", movie_list)

# ====== RECOMMENDATION LOGIC ======
def recommend(movie_title: str, top_n: int = 5):
    if movie_title not in movies["title"].values:
        return []
    idx = int(movies[movies["title"] == movie_title].index[0])
    distances = list(enumerate(similarity[idx]))
    distances_sorted = sorted(distances, key=lambda x: x[1], reverse=True)
    recs = []
    for i, _score in distances_sorted[1 : top_n + 1]:
        try:
            movie_id = int(movies.iloc[i].movie_id)
        except Exception:
            movie_id = int(movies.iloc[i]["movie_id"])
        recs.append(fetch_movie_details(movie_id))
    return recs

# ====== SMALL STYLES (card look) ======
st.markdown(
    """
    <style>
    .card-title { font-weight:700; font-size:14px; margin:6px 0 0 0; }
    .muted { color: #888; font-size:12px; }
    .card-wrap { padding:6px; border-radius:8px; box-shadow: 0 6px 18px rgba(0,0,0,0.08); background: linear-gradient(180deg, #ffffff 0%, #fbfbfb 100%); margin-bottom:8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ====== MAIN: Show Recommendations ======
if st.button("✨ Show Recommendations"):
    with st.spinner("Finding similar movies and fetching details..."):
        recs = recommend(selected_movie, top_n=top_n)

    if not recs:
        st.error("No recommendations found for that selection.")
    else:
        # build multi-row grid with cols_per_row
        total = len(recs)
        rows = math.ceil(total / cols_per_row)
        idx = 0
        for r in range(rows):
            cols = st.columns(cols_per_row, gap="small")
            for c in range(cols_per_row):
                if idx >= total:
                    # empty column
                    cols[c].empty()
                    idx += 1
                    continue
                details = recs[idx]
                col = cols[c]

                # clickable poster (trailer if available, else TMDB)
                link = details.get("trailer") or details.get("tmdb") or "#"
                poster = details.get("poster") or PLACEHOLDER
                title = details.get("title") or "Unknown"

                img_html = f"<a href='{link}' target='_blank'><img src='{poster}' style='width:100%; height:auto; border-radius:6px;'/></a>"
                col.markdown(f"<div class='card-wrap'>{img_html}", unsafe_allow_html=True)

                # Title / meta
                col.markdown(
                    f"<div class='card-wrap'><div class='card-title'>{title} <span class='muted'>({details.get('year')})</span></div>"
                    f"<div class='muted'>⭐ {details.get('rating')} • {', '.join(details.get('genres', [])[:2])}</div>",
                    unsafe_allow_html=True,
                )

                # Cast & director
                col.markdown(f"<div class='muted'>Cast: {', '.join(details.get('cast', []))}</div>", unsafe_allow_html=True)
                col.markdown(f"<div class='muted'>Director: {details.get('director')}</div>", unsafe_allow_html=True)

                # Add/Remove favorites button
                mid = str(details["id"])
                if mid in st.session_state.favorites:
                    if col.button("Remove from Favorites ❌", key=f"rem_{mid}"):
                        st.session_state.favorites.pop(mid, None)
                        st.session_state.last_action = f"Removed '{title}' from favorites."
                        st.experimental_rerun()
                else:
                    if col.button("Add to Favorites ❤️", key=f"add_{mid}"):
                        st.session_state.favorites[mid] = details
                        st.session_state.last_action = f"Added '{title}' to favorites."
                        st.experimental_rerun()

                # Trailer / details
                if details.get("trailer"):
                    col.markdown(f"[▶ Watch Trailer]({details['trailer']})")
                col.markdown("<details><summary>📖 Overview</summary>" + (details.get("overview") or "")[:500] + "</details>", unsafe_allow_html=True)
                col.markdown("</div>", unsafe_allow_html=True)

                idx += 1

# ====== FAVORITES PANEL ======
if show_favs:
    st.markdown("---")
    st.markdown("## ❤️ Your Favorites")
    favs = list(st.session_state.favorites.values())
    if not favs:
        st.info("Your favorites list is empty. Add items by clicking 'Add to Favorites' on any recommendation card.")
    else:
        # show favorites in a simple list with remove button
        for fav in favs:
            cols = st.columns([1, 4, 2])
            with cols[0]:
                # clickable poster to TMDB/trailer
                lk = fav.get("trailer") or fav.get("tmdb") or "#"
                st.markdown(f"[![img]({fav.get('poster')})]({lk})", unsafe_allow_html=True)
            with cols[1]:
                st.markdown(f"**{fav.get('title')} ({fav.get('year')})**")
                st.markdown(f"⭐ {fav.get('rating')} • {', '.join(fav.get('genres', [])[:3])}")
                st.markdown(f"Cast: {', '.join(fav.get('cast', []))}")
            with cols[2]:
                if st.button("Remove", key=f"fav_rem_{fav.get('id')}"):
                    st.session_state.favorites.pop(str(fav.get('id')), None)
                    st.session_state.last_action = f"Removed '{fav.get('title')}' from favorites."
                    st.experimental_rerun()

        # download & quick share text area
        df_favs = pd.DataFrame(favs)
        csv_bytes = df_favs.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download favorites CSV", csv_bytes, file_name="favorites.csv", mime="text/csv")

        share_text = "\n".join([f"{f['title']} ({f['year']}) - {f.get('tmdb')}" for f in favs])
        st.text_area("Share your favorites (copy to clipboard):", value=share_text, height=120)

# ====== FOOTER ======
st.markdown("---")
st.markdown("Made with ❤️ — click posters for trailers or TMDB pages. Favorites persist while the app runs (session). Use Save/Load in the sidebar to persist between runs.")
