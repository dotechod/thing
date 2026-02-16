from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import uvicorn
import os
import json

from api.search import search_youtube_music
from api.process import process_video
from api.lyrics import get_lyrics
from api.artwork import get_artwork
from api.audio import get_audio_chunk
from api.playlist import get_playlist

app = FastAPI(title="CC:Tweaked YouTube Music Backend")

# CORS middleware to allow requests from CC:Tweaked
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request models
class SearchRequest(BaseModel):
    query: str
    maxResults: int = 10

class ProcessRequest(BaseModel):
    url: str

class PlaylistRequest(BaseModel):
    playlistId: str

# Endpoints
@app.post("/api/search")
async def search(request: SearchRequest):
    """Search YouTube Music"""
    try:
        results = await search_youtube_music(request.query, request.maxResults)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/process")
async def process(request: ProcessRequest):
    """Process a video/playlist ID or URL"""
    try:
        result = await process_video(request.url)
        return result
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/lyrics/{video_id}")
async def lyrics(video_id: str):
    """Get lyrics for a video"""
    try:
        lyrics_data = await get_lyrics(video_id)
        return lyrics_data
    except Exception as e:
        return []

@app.get("/api/artwork/{video_id}")
async def artwork(video_id: str):
    """Get ASCII artwork for a video"""
    try:
        artwork_data = await get_artwork(video_id)
        return artwork_data
    except Exception as e:
        return ""

@app.get("/api/audio/{video_id}/chunk")
async def audio_chunk(video_id: str, offset: int = 0, size: int = 4096, channel: Optional[str] = None):
    """Get audio chunk in DFPWM format"""
    try:
        result = await get_audio_chunk(video_id, offset, size, channel)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/playlist")
async def playlist(request: PlaylistRequest):
    """Get playlist tracks"""
    try:
        result = await get_playlist(request.playlistId)
        return result
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
async def root():
    return {"status": "CC:Tweaked YouTube Music Backend", "version": "1.0.0"}

if __name__ == "__main__":
    # Create cache directories if they don't exist
    os.makedirs("cache", exist_ok=True)
    os.makedirs("cache/audio", exist_ok=True)
    os.makedirs("cache/artwork", exist_ok=True)
    os.makedirs("cache/lyrics", exist_ok=True)
    os.makedirs("cache/metadata", exist_ok=True)
    os.makedirs("cache/dfpwm", exist_ok=True)
    
    print("Starting CC:Tweaked YouTube Music Backend on http://localhost:3000")
    uvicorn.run(app, host="0.0.0.0", port=3000)

