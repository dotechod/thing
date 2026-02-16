# API package
import os
import time
from ytmusicapi import YTMusic

_ytmusic_instance = None
_last_request_time = 0
_min_request_delay = 0.5  # Minimum delay between requests (seconds)

def get_ytmusic():
    """
    Initialize YTMusic with authentication if headers_auth.json exists.
    This helps avoid bot detection errors.
    
    Note: If you're still getting bot detection errors even with headers_auth.json,
    your cookies may have expired. You need to refresh them by:
    1. Going to https://music.youtube.com in your browser
    2. Exporting fresh cookies using the ytmusicapi setup instructions
    3. Replacing your headers_auth.json file
    """
    global _ytmusic_instance
    if _ytmusic_instance is None:
        auth_file = "headers_auth.json"
        if os.path.exists(auth_file):
            try:
                _ytmusic_instance = YTMusic(auth_file)
            except Exception as e:
                print(f"Warning: Failed to use {auth_file}, falling back to default: {e}")
                print("Your cookies may have expired. Try refreshing headers_auth.json")
                _ytmusic_instance = YTMusic()
        else:
            # Try without auth (may trigger bot detection)
            _ytmusic_instance = YTMusic()
    return _ytmusic_instance

def reset_ytmusic():
    """Reset YTMusic instance (useful if cookies expire)"""
    global _ytmusic_instance
    _ytmusic_instance = None

def rate_limit():
    """Add a small delay between requests to avoid triggering bot detection"""
    global _last_request_time
    current_time = time.time()
    time_since_last = current_time - _last_request_time
    if time_since_last < _min_request_delay:
        time.sleep(_min_request_delay - time_since_last)
    _last_request_time = time.time()

def is_bot_detection_error(error: Exception) -> bool:
    """Check if an error is related to bot detection"""
    error_msg = str(error).lower()
    error_type = type(error).__name__.lower()
    
    # Common bot detection indicators
    bot_indicators = [
        "bot", "captcha", "verify", "verification", 
        "unusual traffic", "automated", "rate limit",
        "429", "403", "forbidden", "blocked"
    ]
    
    return any(indicator in error_msg for indicator in bot_indicators) or "httperror" in error_type

