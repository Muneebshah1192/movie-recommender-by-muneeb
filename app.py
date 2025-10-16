# app.py
import pickle, joblib, json, math, random, requests
import pandas as pd
import streamlit as st
from io import StringIO

# ================= CONFIG =================
st.set_page_config(
    page_title="🎬 Muneeb's Movie Recommender",
    page_icon="🎥",
    layout="wide"
)

API_KEY = st.secrets.get("TMDB_API_KEY", "")
PLACEHOLDER = "https://via.placeholder.com/500x750.png?text=No+Image"

st.markdown(
    "<h1 style='text-align:center;'>🎬 Muneeb's Movie Recommender</h1>",
    unsafe_allow_html=True
)
st.write("Pick a movie, view **recommendations**, and save favorites ❤️.")

# ================= HELPERS =================
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
    """Fetch movie details, poster, credits, trailer."""
    base = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={API_KEY}&language=en-US"
    data = fetch_json(base)

    poster_path = data.get("poster_path")
    poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else PLACEHOLDER
    overview = data.get("overview", "No description available.")
    release_date = data.get("release_date", "")
    year = release_date.split("-")[0] if release_date else "N/A"
    rating = data.get("vote_average", "N/A")
    genres = [g["name"] for g in data.get("genres", [])]
    language = (data.get("original_language") or "N/A").upper()

    credits = fetch_json(f"https://api.themoviedb.org/3/movie/{movie_id}/credits?api_key={API_KEY}&language=en-US")
    cast = [c["name"] for c in credits.get("cast", [])[:3]] if credits else []
    director = next((c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"), "Unknown")

    videos = fetch_json(f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={API_KEY}&language=en-US")
    trailer = next((f"https://www.youtube.com/watch?v={v.get('key')}" for v in videos.get("results", [])
                    if v.get("site") == "YouTube" and v.get("type") == "Trailer"), None)

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
        "tmdb": f"https://www.themoviedb.org/movie/{movie_id}"
    }

# ================= LOAD DATA =================
try:
    movies_dict = pickle.load(open("movies_dict.pkl", "rb"))
    movies = pd.DataFrame(movies_dict)

    # Try compressed first, fallback to pickle
    try:
        similarity = joblib.load("similarity_compressed.pkl")
    except Exception:
        similarity = pickle.load(open("similarity.pkl", "rb"))
except Exception as e:
    st.error(f"Data files missing or corrupted: {e}")
    st.stop()

# ================= STATE INIT =================
if "favorites" not in st.session_state:
    st.session_state.favorites = {}

# ================= SIDEBAR =================
st.sidebar.header("⚙️ Options & Favorites")
top_n = st.sidebar.slider("Recommendations", 5, 12, 5)
cols_per_row = st.sidebar.slider("Cards per row", 1, 5, 4)
surprise = st.sidebar.button("🎲 Surprise Me")

if st.sidebar.button("💾 Save Favorites"):
    try:
        with open("favorites.json", "w", encoding="utf-8") as f:
            json.dump(list(st.session_state.favorites.values()), f, ensure_ascii=False, indent=2)
        st.sidebar.success("Saved to favorites.json")
    except Exception as e:
        st.sidebar.error(f"Save failed: {e}")

if st.sidebar.button("📂 Load Favorites"):
    try:
        with open("favorites.json", "r", encoding="utf-8") as f:
            loaded = json.load(f)
        st.session_state.favorites = {str(item["id"]): item for item in loaded}
        st.sidebar.success("Favorites loaded")
    except Exception as e:
        st.sidebar.error(f"Load failed: {e}")

show_favs = st.sidebar.checkbox("Show Favorites panel", value=False)

if st.session_state.favorites:
    def favorites_csv_bytes():
        df = pd.DataFrame(list(st.session_state.favorites.values()))
        return df.to_csv(index=False).encode("utf-8")
    st.sidebar.download_button("📥 Download Favorites CSV", favorites_csv_bytes(),
                               file_name="favorites.csv", mime="text/csv")

# ================= RECOMMEND =================
@st.cache_data(show_spinner=False)
def recommend(movie_title: str, top_n: int = 5):
    if movie_title not in movies["title"].values:
        return []
    idx = int(movies[movies["title"] == movie_title].index[0])
    distances = list(enumerate(similarity[idx]))
    distances_sorted = sorted(distances, key=lambda x: x[1], reverse=True)
    recs = []
    for i, _ in distances_sorted[1: top_n + 1]:
        movie_id = int(movies.iloc[i].movie_id)
        recs.append(fetch_movie_details(movie_id))
    return recs

# ================= MOVIE SELECT =================
movie_list = movies["title"].values.tolist()
if surprise:
    selected_movie = random.choice(movie_list)
    st.sidebar.success(f"Surprise: {selected_movie}")
else:
    selected_movie = st.selectbox("🎥 Select a movie", movie_list)

# ================= MAIN =================
if st.button("✨ Show Recommendations"):
    with st.spinner("Fetching recommendations..."):
        recs = recommend(selected_movie, top_n=top_n)

    if not recs:
        st.error("No recommendations found.")
    else:
        total = len(recs)
        rows = math.ceil(total / cols_per_row)
        idx = 0
        for r in range(rows):
            cols = st.columns(cols_per_row, gap="small")
            for c in range(cols_per_row):
                if idx >= total:
                    cols[c].empty()
                    idx += 1
                    continue

                details = recs[idx]
                col = cols[c]

                # poster
                link = details.get("trailer") or details.get("tmdb")
                img_html = f"<a href='{link}' target='_blank'><img src='{details['poster']}' style='width:100%; border-radius:6px;'/></a>"
                col.markdown(img_html, unsafe_allow_html=True)

                # title/meta
                col.markdown(f"**{details['title']} ({details['year']})**")
                col.markdown(f"⭐ {details['rating']} • {', '.join(details.get('genres', [])[:2])}")
                col.markdown(f"Cast: {', '.join(details['cast'])}")
                col.markdown(f"Director: {details['director']}")

                mid = str(details["id"])
                if mid in st.session_state.favorites:
                    if col.button("❌ Remove", key=f"rem_{mid}"):
                        st.session_state.favorites.pop(mid, None)
                        st.experimental_rerun()
                else:
                    if col.button("❤️ Add", key=f"add_{mid}"):
                        st.session_state.favorites[mid] = details
                        st.experimental_rerun()

                if details.get("trailer"):
                    col.markdown(f"[▶ Trailer]({details['trailer']})")
                col.markdown(f"<details><summary>📖 Overview</summary>{details['overview'][:400]}</details>", unsafe_allow_html=True)

                idx += 1

# ================= FAVORITES PANEL =================
if show_favs:
    st.markdown("---")
    st.markdown("## ❤️ Your Favorites")
    favs = list(st.session_state.favorites.values())
    if not favs:
        st.info("No favorites yet. Add some from recommendations.")
    else:
        for fav in favs:
            cols = st.columns([1, 4, 2])
            with cols[0]:
                link = fav.get("trailer") or fav.get("tmdb")
                st.markdown(f"[![img]({fav['poster']})]({link})", unsafe_allow_html=True)
            with cols[1]:
                st.markdown(f"**{fav['title']} ({fav['year']})**")
                st.markdown(f"⭐ {fav['rating']} • {', '.join(fav['genres'][:3])}")
                st.markdown(f"Cast: {', '.join(fav['cast'])}")
            with cols[2]:
                if st.button("Remove", key=f"fav_{fav['id']}"):
                    st.session_state.favorites.pop(str(fav['id']), None)
                    st.experimental_rerun()

        csv_bytes = pd.DataFrame(favs).to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download favorites CSV", csv_bytes,
                           file_name="favorites.csv", mime="text/csv")
        share_text = "\n".join([f"{f['title']} ({f['year']}) - {f['tmdb']}" for f in favs])
        st.text_area("Copy favorites list:", value=share_text, height=120)

# ================= FOOTER =================
st.markdown("---")
st.markdown("Made with ❤️ by Muneeb — Posters link to trailers or TMDB pages. Favorites persist while the app runs (session). Use Save/Load in sidebar to keep them.")
