# API package
import os
from ytmusicapi import YTMusic

def get_ytmusic():
    """
    Initialize YTMusic with authentication if headers_auth.json exists.
    This helps avoid bot detection errors.
    """
    auth_file = "headers_auth.json"
    if os.path.exists(auth_file):
        try:
            return YTMusic(auth_file)
        except Exception as e:
            print(f"Warning: Failed to use {auth_file}, falling back to default: {e}")
            return YTMusic()
    else:
        # Try without auth (may trigger bot detection)
        return YTMusic()

