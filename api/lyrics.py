import os
import json
from typing import List, Dict
from api import get_ytmusic, rate_limit, is_bot_detection_error

LYRICS_CACHE_DIR = os.path.join("cache", "lyrics")
os.makedirs(LYRICS_CACHE_DIR, exist_ok=True)

async def get_lyrics(video_id: str) -> List[Dict]:
    """
    Get lyrics for a video.
    Returns: List of {time: float, text: str}
    """
    # Check cache
    cache_file = os.path.join(LYRICS_CACHE_DIR, f"{video_id}.json")
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    try:
        # Get lyrics from YTMusic
        rate_limit()  # Add delay between requests
        ytmusic = get_ytmusic()
        song_info = ytmusic.get_song(video_id)
        
        if not song_info or 'lyrics' not in song_info or not song_info['lyrics']:
            return []
        
        lyrics_data = song_info['lyrics']
        
        # Parse lyrics - YTMusic returns lyrics in different formats
        formatted_lyrics = []
        
        if isinstance(lyrics_data, str):
            # Simple text lyrics - split by lines and assign timestamps
            lines = lyrics_data.split('\n')
            time_per_line = 3.0  # Default 3 seconds per line
            current_time = 0.0
            for line in lines:
                line = line.strip()
                if line:
                    formatted_lyrics.append({
                        "time": current_time,
                        "text": line
                    })
                    current_time += time_per_line
        elif isinstance(lyrics_data, list):
            # Already formatted as list
            for item in lyrics_data:
                if isinstance(item, dict):
                    time = item.get('time', 0)
                    text = item.get('text', '')
                    if text:
                        formatted_lyrics.append({
                            "time": float(time),
                            "text": str(text)
                        })
        elif isinstance(lyrics_data, dict):
            # Try to extract from dict structure
            if 'lines' in lyrics_data:
                for line in lyrics_data['lines']:
                    if isinstance(line, dict):
                        time = line.get('time', 0)
                        text = line.get('text', '')
                        if text:
                            formatted_lyrics.append({
                                "time": float(time),
                                "text": str(text)
                            })
        
        # Cache lyrics
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(formatted_lyrics, f, ensure_ascii=False)
        
        return formatted_lyrics
        
    except Exception as e:
        if is_bot_detection_error(e):
            print(f"Bot detection error: {e}")
            print("To fix this, create headers_auth.json with your YouTube Music authentication.")
        else:
            print(f"Lyrics error for {video_id}: {e}")
        return []

