from ytmusicapi import YTMusic
from yt_dlp import YoutubeDL
import os
import json
import re
from typing import Dict, Optional

ytmusic = YTMusic()

# Cache directory
CACHE_DIR = "cache"
AUDIO_CACHE_DIR = os.path.join(CACHE_DIR, "audio")
METADATA_CACHE_DIR = os.path.join(CACHE_DIR, "metadata")

os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
os.makedirs(METADATA_CACHE_DIR, exist_ok=True)

async def process_video(video_id_or_url: str) -> Dict:
    """
    Process a video ID or URL and return metadata.
    Downloads audio if not cached.
    Returns: {id, title, artist, album?, duration, hasLyrics}
    """
    # Extract video ID
    video_id = extract_video_id(video_id_or_url)
    if not video_id:
        return {"error": "Invalid video ID or URL"}
    
    # Check metadata cache
    metadata_file = os.path.join(METADATA_CACHE_DIR, f"{video_id}.json")
    if os.path.exists(metadata_file):
        with open(metadata_file, 'r', encoding='utf-8') as f:
            cached_metadata = json.load(f)
            # Still ensure audio is downloaded
            await ensure_audio_downloaded(video_id)
            return cached_metadata
    
    try:
        # Get video info using yt-dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            # Try to get info
            url = f"https://www.youtube.com/watch?v={video_id}"
            info = ydl.extract_info(url, download=False)
            
            # Extract metadata
            title = info.get('title', 'Unknown')
            duration = info.get('duration', 0)
            
            # Get artist and album from YTMusic if possible
            artist = "Unknown Artist"
            album = None
            has_lyrics = False
            
            try:
                # Try to get more detailed info from YTMusic
                song_info = ytmusic.get_song(video_id)
                if song_info and 'videoDetails' in song_info:
                    vd = song_info['videoDetails']
                    if 'author' in vd:
                        artist = vd['author']
                    if 'album' in vd:
                        album = vd['album'].get('name') if isinstance(vd['album'], dict) else vd['album']
            except:
                # Fallback to yt-dlp metadata
                if 'artist' in info:
                    artist = info['artist']
                elif 'uploader' in info:
                    artist = info['uploader']
                if 'album' in info:
                    album = info['album']
            
            # Check for lyrics availability (YTMusic sometimes has this)
            try:
                song_info = ytmusic.get_song(video_id)
                if song_info and 'lyrics' in song_info:
                    has_lyrics = song_info['lyrics'] is not None
            except:
                pass
            
            metadata = {
                "id": video_id,
                "title": title,
                "artist": artist,
                "duration": duration,
                "hasLyrics": has_lyrics
            }
            
            if album:
                metadata["album"] = album
            
            # Cache metadata
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False)
            
            # Download audio (this may take a while, but we need it for playback)
            # Start download in background - it will be ready when needed
            import threading
            thread = threading.Thread(target=ensure_audio_downloaded, args=(video_id,))
            thread.daemon = True
            thread.start()
            
            return metadata
            
    except Exception as e:
        print(f"Process error for {video_id}: {e}")
        return {"error": str(e)}

def extract_video_id(video_id_or_url: str) -> Optional[str]:
    """Extract YouTube video ID from URL or return if it's already an ID"""
    # Check if it's already an 11-character video ID
    if len(video_id_or_url) == 11 and re.match(r'^[a-zA-Z0-9_-]{11}$', video_id_or_url):
        return video_id_or_url
    
    # Extract from YouTube URL
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, video_id_or_url)
        if match:
            return match.group(1)
    
    return None

def ensure_audio_downloaded(video_id: str):
    """Download audio file if not already cached"""
    audio_file = os.path.join(AUDIO_CACHE_DIR, f"{video_id}.m4a")
    if os.path.exists(audio_file):
        return
    
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': audio_file.replace('.m4a', '.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'm4a',
                'preferredquality': '192',
            }],
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            url = f"https://www.youtube.com/watch?v={video_id}"
            ydl.download([url])
            
            # Rename to .m4a if needed
            for ext in ['m4a', 'mp3', 'webm', 'opus']:
                temp_file = audio_file.replace('.m4a', f'.{ext}')
                if os.path.exists(temp_file):
                    if ext != 'm4a':
                        os.rename(temp_file, audio_file)
                    break
    except Exception as e:
        print(f"Audio download error for {video_id}: {e}")

