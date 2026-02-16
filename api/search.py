from typing import List, Dict
import re
import time
import os
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
            
            # Check if using OAuth - OAuth may not support filter parameter
            using_oauth = os.path.exists("oauth.json") and os.path.exists("oauth_config.json")
            
            # Try search - OAuth may not support filter parameter
            results = None
            if using_oauth:
                # With OAuth, try without filter first (filter may cause 400 error)
                try:
                    results = ytmusic.search(query, limit=max_results)
                    # Filter results to songs manually - keep only results with videoId
                    if results:
                        results = [r for r in results if r.get("videoId")]
                        # Limit to max_results
                        results = results[:max_results]
                except Exception as oauth_error:
                    # If that fails, try with filter as fallback
                    error_msg = str(oauth_error).lower()
                    if "400" not in str(oauth_error) and "invalid" not in error_msg:
                        # Not a 400 error, try with filter
                        results = ytmusic.search(query, filter="songs", limit=max_results)
                    else:
                        raise
            else:
                # With headers auth, try with filter first
                try:
                    results = ytmusic.search(query, filter="songs", limit=max_results)
                except Exception as filter_error:
                    # If filter fails, try without filter
                    error_msg = str(filter_error).lower()
                    if "400" in str(filter_error) or "invalid" in error_msg or "bad request" in error_msg:
                        print(f"Search with filter failed, trying without filter...")
                        results = ytmusic.search(query, limit=max_results)
                        # Filter results to songs manually
                        if results:
                            results = [r for r in results if r.get("videoId")]
                            results = results[:max_results]
                    else:
                        raise
            
            if not results:
                raise Exception("No search results returned")
            
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
                # For HTTP 400 errors, try yt-dlp fallback immediately
                error_msg = str(e).lower()
                if "400" in str(e) or "bad request" in error_msg or "invalid argument" in error_msg:
                    print(f"Search error (HTTP 400): {e}")
                    print("Falling back to yt-dlp...")
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

