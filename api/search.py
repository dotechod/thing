from typing import List, Dict
import re
import time
from api import get_ytmusic, rate_limit, is_bot_detection_error, reset_ytmusic

async def search_youtube_music(query: str, max_results: int = 10) -> List[Dict]:
    """
    Search YouTube Music and return results in the format expected by the Lua client.
    Returns: List of {id, title, artist, duration}
    """
    # Check if query is a direct video ID or URL
    video_id = extract_video_id(query)
    if video_id:
        # Return single result for direct video ID
        return [{"id": video_id, "title": query, "artist": "Unknown", "duration": "?"}]
    
    # Try YTMusic with retry logic
    max_retries = 2
    for attempt in range(max_retries):
        try:
            rate_limit()  # Add delay between requests
            ytmusic = get_ytmusic()  # Get fresh instance
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
            if is_bot_detection_error(e):
                print(f"Bot detection error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    # Wait before retry with exponential backoff
                    wait_time = (attempt + 1) * 2
                    print(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    # Try resetting YTMusic instance
                    reset_ytmusic()
                    continue
                else:
                    # Final attempt failed, try yt-dlp fallback
                    print("YTMusic failed, trying yt-dlp fallback...")
                    return await search_youtube_music_ytdlp(query, max_results)
            else:
                print(f"Search error: {e}")
                return []
    
    return []

async def search_youtube_music_ytdlp(query: str, max_results: int = 10) -> List[Dict]:
    """Fallback: Search using yt-dlp"""
    try:
        from yt_dlp import YoutubeDL
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch',
            'playlistend': max_results,
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            # Search using yt-dlp
            search_query = f"ytsearch{max_results}:{query}"
            info = ydl.extract_info(search_query, download=False)
            
            if not info or 'entries' not in info:
                return []
            
            formatted_results = []
            for entry in info.get('entries', []):
                if entry and 'id' in entry:
                    formatted_results.append({
                        "id": entry['id'],
                        "title": entry.get('title', 'Unknown'),
                        "artist": entry.get('uploader', 'Unknown Artist'),
                        "duration": entry.get('duration_string', '?')
                    })
            
            return formatted_results
    except Exception as e:
        print(f"yt-dlp search error: {e}")
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

