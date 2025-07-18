from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pydantic import BaseModel
from typing import Optional
import requests
import urllib.parse
import logging
import google.generativeai as genai

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- FastAPI App ---
app = FastAPI()

# --- CORS Configuration ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MongoDB Connection ---
MONGODB_URL = "mongodb+srv://sahana:sahana-123@cluster0.hl7kiqb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(MONGODB_URL)

# --- Gemini API Setup ---
GEMINI_API_KEY = "AIzaSyBA7bd5_kL352A0eGYIlPRz5qxpeYmQ5PI"
genai.configure(api_key=GEMINI_API_KEY)

# --- OMDb API Key ---
OMDB_API_KEY = "766a3905"

# --- Database Dependency ---
def get_db():
    return client["movies_db"]["movies"]

# --- Pydantic Models ---
class MovieRequest(BaseModel):
    title: str
    plot: str

class UpdateMovieModel(BaseModel):
    Title: Optional[str]
    Year: Optional[str]
    Genre: Optional[str]
    Director: Optional[str]
    Plot: Optional[str]
    Poster: Optional[str]
    gemini_summary: Optional[str]

# --- Home Route ---
@app.get("/")
def home():
    return {"message": "🎬 Welcome to IMDb Movie API with MongoDB & Gemini AI"}

# --- Search Movies ---
@app.get("/search/{movie_name}")
def search_movies(movie_name: str):
    encoded = urllib.parse.quote(movie_name)
    url = f"https://www.omdbapi.com/?s={encoded}&apikey={OMDB_API_KEY}"
    try:
        res = requests.get(url)
        res.raise_for_status()
        data = res.json()
        if data.get("Response") == "True":
            return {"results": data["Search"]}
        raise HTTPException(status_code=404, detail="No movies found.")
    except Exception:
        logger.exception("OMDb API search failed")
        raise HTTPException(status_code=502, detail="Failed to fetch from OMDb API.")

# --- Get Movie by IMDb ID ---
@app.get("/movie/{movie_id}")
def get_movie(movie_id: str, collection=Depends(get_db)):
    if not movie_id.startswith("tt"):
        movie_id = f"tt{movie_id}"

    # Check MongoDB
    record = collection.find_one({"imdbID": movie_id})
    if record:
        record.pop("_id", None)
        record["source"] = "MongoDB"
        return record

    # Fetch from OMDb API
    url = f"https://www.omdbapi.com/?i={movie_id}&apikey={OMDB_API_KEY}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        movie = response.json()

        if movie.get("Response") == "False":
            raise HTTPException(status_code=404, detail="Movie not found.")

        movie.pop("Response", None)

        # Generate summary using Gemini
        prompt = f"Give me a brief, engaging summary for a movie titled '{movie.get('Title', '')}'. Here's its plot: {movie.get('Plot', 'No plot available.')}"
        try:
            model = genai.GenerativeModel("gemini-1.5-pro-latest")
            response = model.generate_content(prompt)
            movie["gemini_summary"] = response.text
        except Exception as e:
            logger.warning(f"Gemini failed: {e}")
            movie["gemini_summary"] = None

        collection.update_one({"imdbID": movie["imdbID"]}, {"$set": movie}, upsert=True)
        movie["source"] = "IMDb"
        return movie

    except Exception:
        logger.exception("OMDb movie fetch failed")
        raise HTTPException(status_code=502, detail="Failed to fetch movie data.")

# --- Update Movie ---
@app.patch("/update/{movie_id}")
def update_movie(movie_id: str, data: UpdateMovieModel, collection=Depends(get_db)):
    if not movie_id.startswith("tt"):
        movie_id = f"tt{movie_id}"

    updates = {k: v for k, v in data.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No data provided.")

    # Generate summary if Plot is updated
    if "Plot" in updates and "Title" in updates:
        prompt = f"Give me a brief, engaging summary for a movie titled '{updates['Title']}'. Here's its plot: {updates['Plot']}"
        try:
            model = genai.GenerativeModel("gemini-1.5-pro-latest")
            result = model.generate_content(prompt)
            updates["gemini_summary"] = result.text
        except Exception as e:
            logger.warning(f"Gemini summary update failed: {e}")
    elif "Plot" in updates:
        existing = collection.find_one({"imdbID": movie_id})
        if existing and "Title" in existing:
            prompt = f"Give me a brief, engaging summary for a movie titled '{existing['Title']}'. Here's its plot: {updates['Plot']}"
            try:
                model = genai.GenerativeModel("gemini-1.5-pro-latest")
                result = model.generate_content(prompt)
                updates["gemini_summary"] = result.text
            except Exception:
                logger.warning("Gemini summary skipped.")

    result = collection.update_one({"imdbID": movie_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Movie not found.")
    return {"message": f"Movie {movie_id} updated."}

# --- Delete Movie ---
@app.delete("/delete/{movie_id}")
def delete_movie(movie_id: str, collection=Depends(get_db)):
    if not movie_id.startswith("tt"):
        movie_id = f"tt{movie_id}"
    result = collection.delete_one({"imdbID": movie_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Movie not found.")
    return {"message": f"Movie {movie_id} deleted."}

# --- List Movies ---
@app.get("/movies")
def list_movies(skip: int = 0, limit: int = 10, collection=Depends(get_db)):
    results = list(collection.find({}, {"_id": 0}).skip(skip).limit(limit))
    return {"count": len(results), "results": results}

# --- Manual Gemini Summary ---
@app.post("/gemini-summary")
def get_summary(req: MovieRequest):
    prompt = f"Give me a brief, engaging summary for a movie titled '{req.title}'. Here's its plot: {req.plot}"
    try:
        model = genai.GenerativeModel("gemini-1.5-pro-latest")
        response = model.generate_content(prompt)
        return {"summary": response.text}
    except Exception:
        logger.exception("Gemini summary generation failed.")
        raise HTTPException(status_code=500, detail="Gemini API error.")
