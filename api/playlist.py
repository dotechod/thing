from typing import Dict, List
import re
import time
from api import get_ytmusic, rate_limit, is_bot_detection_error

async def get_playlist(playlist_id: str) -> Dict:
    """
    Get playlist tracks.
    Returns: {title: str, tracks: [{id, title}]} or {error: str}
    """
    try:
        # Clean playlist ID (remove PL prefix if present in some formats)
        clean_id = playlist_id
        
        # Try to get playlist from YTMusic
        try:
            rate_limit()  # Add delay between requests
            ytmusic = get_ytmusic()
            playlist = ytmusic.get_playlist(playlist_id, limit=None)
            
            if not playlist or 'tracks' not in playlist:
                return {"error": "Playlist not found"}
            
            tracks = []
            for track in playlist['tracks']:
                if 'videoId' in track:
                    tracks.append({
                        "id": track['videoId'],
                        "title": track.get('title', 'Unknown')
                    })
            
            return {
                "title": playlist.get('title', 'Playlist'),
                "tracks": tracks
            }
        except Exception as e:
            # If YTMusic fails, try yt-dlp
            return await get_playlist_ytdlp(playlist_id)
            
    except Exception as e:
        if is_bot_detection_error(e):
            print(f"Bot detection error: {e}")
            print("To fix this, create headers_auth.json with your YouTube Music authentication.")
            return {"error": "Bot detection error. Please set up headers_auth.json (see README.md)"}
        else:
            print(f"Playlist error for {playlist_id}: {e}")
            return {"error": str(e)}

async def get_playlist_ytdlp(playlist_id: str) -> Dict:
    """Fallback: Get playlist using yt-dlp"""
    try:
        from yt_dlp import YoutubeDL
        import os
        
        # Check for WARP proxy
        warp_proxy = os.environ.get('WARP_PROXY', 'socks5://127.0.0.1:40000')
        use_warp = os.environ.get('USE_WARP', 'false').lower() == 'true'
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'playlistend': 200,  # Limit to 200 tracks
            'proxy': warp_proxy if use_warp else None,
        }
        ydl_opts = {k: v for k, v in ydl_opts.items() if v is not None}
        
        url = f"https://www.youtube.com/playlist?list={playlist_id}"
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info or 'entries' not in info:
                return {"error": "Playlist not found"}
            
            tracks = []
            for entry in info['entries']:
                if entry and 'id' in entry:
                    tracks.append({
                        "id": entry['id'],
                        "title": entry.get('title', 'Unknown')
                    })
            
            return {
                "title": info.get('title', 'Playlist'),
                "tracks": tracks
            }
    except Exception as e:
        return {"error": str(e)}

