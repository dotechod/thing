from ytmusicapi import YTMusic
from typing import List, Dict
import re

# Initialize YTMusic (no auth needed for search)
ytmusic = YTMusic()

async def search_youtube_music(query: str, max_results: int = 10) -> List[Dict]:
    """
    Search YouTube Music and return results in the format expected by the Lua client.
    Returns: List of {id, title, artist, duration}
    """
    try:
        # Check if query is a direct video ID or URL
        video_id = extract_video_id(query)
        if video_id:
            # Return single result for direct video ID
            return [{"id": video_id, "title": query, "artist": "Unknown", "duration": "?"}]
        
        # Perform search
        results = ytmusic.search(query, filter="songs", limit=max_results)
        
        formatted_results = []
        for result in results:
            if result.get("videoId"):
                # Extract duration
                duration = "?"
                if "duration" in result:
                    duration = result["duration"]
                elif "length" in result:
                    duration = result["length"]
                
                # Extract artist
                artist = "Unknown Artist"
                if "artists" in result and len(result["artists"]) > 0:
                    artist = result["artists"][0]["name"]
                
                formatted_results.append({
                    "id": result["videoId"],
                    "title": result.get("title", "Unknown"),
                    "artist": artist,
                    "duration": duration
                })
        
        return formatted_results
    except Exception as e:
        print(f"Search error: {e}")
        return []

def extract_video_id(query: str) -> str:
    """Extract YouTube video ID from URL or return if it's already an ID"""
    # Check if it's already an 11-character video ID
    if len(query) == 11 and re.match(r'^[a-zA-Z0-9_-]{11}$', query):
        return query
    
    # Extract from YouTube URL
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, query)
        if match:
            return match.group(1)
    
    return None

