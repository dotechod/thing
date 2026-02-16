from ytmusicapi import YTMusic
from typing import Dict, List
import re

ytmusic = YTMusic()

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
        print(f"Playlist error for {playlist_id}: {e}")
        return {"error": str(e)}

async def get_playlist_ytdlp(playlist_id: str) -> Dict:
    """Fallback: Get playlist using yt-dlp"""
    try:
        from yt_dlp import YoutubeDL
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'playlistend': 200,  # Limit to 200 tracks
        }
        
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

