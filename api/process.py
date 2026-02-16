from yt_dlp import YoutubeDL
import os
import json
import re
from typing import Dict, Optional
from api import get_ytmusic, rate_limit, is_bot_detection_error

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
    
    # Try to get metadata from YTMusic first (works with OAuth)
    title = None
    duration = 0
    artist = "Unknown Artist"
    album = None
    has_lyrics = False
    
    try:
        rate_limit()
        ytmusic = get_ytmusic()
        song_info = ytmusic.get_song(video_id)
        
        if song_info and 'videoDetails' in song_info:
            vd = song_info['videoDetails']
            title = vd.get('title', 'Unknown')
            # Duration might be in lengthSeconds
            if 'lengthSeconds' in vd:
                try:
                    duration = int(vd['lengthSeconds'])
                except:
                    duration = 0
            if 'author' in vd:
                artist = vd['author']
            if 'album' in vd:
                album = vd['album'].get('name') if isinstance(vd['album'], dict) else vd['album']
            
            # Check for lyrics
            if 'lyrics' in song_info and song_info['lyrics']:
                has_lyrics = True
                
    except Exception as e:
        if is_bot_detection_error(e):
            print(f"Bot detection error when getting song info from YTMusic: {e}")
        else:
            print(f"YTMusic get_song error: {e}")
        # Will fall back to yt-dlp below
    
    # If YTMusic didn't provide title, fall back to yt-dlp
    if not title:
        try:
            # Get video info using yt-dlp as fallback
            # Check for cookies to help with bot detection
            cookie_string_meta = None
            if os.path.exists("headers_auth.json"):
                try:
                    with open("headers_auth.json", 'r') as f:
                        headers_data = json.load(f)
                        if 'cookie' in headers_data:
                            cookie_string_meta = headers_data['cookie']
                except:
                    pass
            
            # Check for WARP proxy
            warp_proxy_meta = os.environ.get('WARP_PROXY', 'socks5://127.0.0.1:40000')
            use_warp_meta = os.environ.get('USE_WARP', 'false').lower() == 'true'
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'referer': 'https://www.youtube.com/',
                'proxy': warp_proxy_meta if use_warp_meta else None,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'ios', 'web'],
                        'player_skip': ['webpage', 'configs'],
                    }
                },
                'http_headers': {
                    'Cookie': cookie_string_meta
                } if cookie_string_meta else None,
                'sleep_interval': 1,
            }
            ydl_opts = {k: v for k, v in ydl_opts.items() if v is not None}
            if not cookie_string_meta:
                ydl_opts.pop('http_headers', None)
            
            with YoutubeDL(ydl_opts) as ydl:
                url = f"https://www.youtube.com/watch?v={video_id}"
                info = ydl.extract_info(url, download=False)
                
                if not title:
                    title = info.get('title', 'Unknown')
                if not duration:
                    duration = info.get('duration', 0)
                
                # Use yt-dlp metadata if YTMusic didn't provide it
                if artist == "Unknown Artist":
                    if 'artist' in info:
                        artist = info['artist']
                    elif 'uploader' in info:
                        artist = info['uploader']
                if not album and 'album' in info:
                    album = info['album']
                    
        except Exception as e:
            error_msg = str(e).lower()
            if "bot" in error_msg or "sign in" in error_msg or "confirm" in error_msg:
                print(f"yt-dlp bot detection error for {video_id}: {e}")
                # If we have at least a video ID, return minimal metadata
                if not title:
                    title = f"Video {video_id}"
                # Continue with minimal metadata
            else:
                print(f"yt-dlp error for {video_id}: {e}")
                # Don't fail completely, return minimal metadata
                if not title:
                    title = f"Video {video_id}"
    
    # Create metadata
    metadata = {
        "id": video_id,
        "title": title or "Unknown",
        "artist": artist,
        "duration": duration,
        "hasLyrics": has_lyrics
    }
    
    if album:
        metadata["album"] = album
    
    # Cache metadata
    try:
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Failed to cache metadata: {e}")
    
    # Download audio (this may take a while, but we need it for playback)
    # Start download in background - it will be ready when needed
    import threading
    thread = threading.Thread(target=ensure_audio_downloaded, args=(video_id,))
    thread.daemon = True
    thread.start()
    
    return metadata

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
    
    # Check for cookies to help with bot detection
    # yt-dlp needs cookies in Netscape format, but we can try to extract from headers_auth.json
    cookies_file = None
    cookie_string = None
    if os.path.exists("headers_auth.json"):
        try:
            with open("headers_auth.json", 'r') as f:
                headers_data = json.load(f)
                # Extract cookie string if available
                if 'cookie' in headers_data:
                    cookie_string = headers_data['cookie']
        except:
            pass
    
    # Check for WARP proxy (Cloudflare WARP in proxy mode)
    # Default WARP proxy is SOCKS5 on 127.0.0.1:40000
    warp_proxy = os.environ.get('WARP_PROXY', 'socks5://127.0.0.1:40000')
    use_warp = os.environ.get('USE_WARP', 'false').lower() == 'true'
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Build yt-dlp options optimized for cloud/VPS environments
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': audio_file.replace('.m4a', '.%(ext)s'),
                'quiet': True,
                'no_warnings': True,
                # Better user agent to avoid bot detection
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'referer': 'https://www.youtube.com/',
                # Use WARP proxy if enabled
                'proxy': warp_proxy if use_warp else None,
                # Additional options to reduce bot detection for cloud IPs
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'ios', 'web'],  # Try multiple clients
                        'player_skip': ['webpage', 'configs'],  # Skip some checks
                    }
                },
                # Add cookies via headers if we have them
                'http_headers': {
                    'Cookie': cookie_string
                } if cookie_string else None,
                # Additional options for cloud environments
                'sleep_interval': 1,  # Add small delay between requests
                'sleep_interval_requests': 1,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'm4a',
                    'preferredquality': '192',
                }],
            }
            
            # Remove None values
            ydl_opts = {k: v for k, v in ydl_opts.items() if v is not None}
            # Handle http_headers separately
            if not cookie_string:
                ydl_opts.pop('http_headers', None)
            
            if use_warp:
                print(f"Using WARP proxy: {warp_proxy}")
            
            with YoutubeDL(ydl_opts) as ydl:
                url = f"https://www.youtube.com/watch?v={video_id}"
                ydl.download([url])
                
                # Rename to .m4a if needed
                for ext in ['m4a', 'mp3', 'webm', 'opus']:
                    temp_file = audio_file.replace('.m4a', f'.{ext}')
                    if os.path.exists(temp_file):
                        if ext != 'm4a':
                            os.rename(temp_file, audio_file)
                        print(f"Successfully downloaded audio for {video_id}")
                        return  # Success
                break  # Success
                
        except Exception as e:
            error_msg = str(e).lower()
            if ("bot" in error_msg or "sign in" in error_msg or "confirm" in error_msg) and attempt < max_retries - 1:
                wait_time = (attempt + 1) * 10  # Wait 10, 20, 30 seconds (longer waits)
                print(f"Audio download bot detection error (attempt {attempt + 1}/{max_retries}) for {video_id}, retrying in {wait_time}s...")
                import time
                time.sleep(wait_time)
                continue
            else:
                print(f"Audio download error for {video_id}: {e}")
                if attempt == max_retries - 1:
                    print(f"Failed to download audio for {video_id} after {max_retries} attempts")
                    print("Note: YouTube bot detection is blocking downloads (common on cloud/VPS IPs).")
                    print("Consider:")
                    print("  1. Using headers_auth.json with fresh cookies from a browser")
                    print("  2. Running from a residential IP (not cloud/VPS)")
                    print("  3. Using a VPN or proxy service")
                    print("  4. Pre-downloading audio files manually")
                break

