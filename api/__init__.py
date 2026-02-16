# API package
import os
import time
import json
from ytmusicapi import YTMusic, OAuthCredentials

_ytmusic_instance = None
_last_request_time = 0
_min_request_delay = 0.5  # Minimum delay between requests (seconds)

def get_ytmusic():
    """
    Initialize YTMusic with OAuth authentication (preferred) or headers_auth.json fallback.
    OAuth is more reliable and less prone to bot detection errors.
    
    Priority:
    1. OAuth (oauth.json + oauth_config.json with client_id/client_secret)
    2. headers_auth.json (cookie-based, may expire)
    3. No authentication (may trigger bot detection)
    """
    global _ytmusic_instance
    if _ytmusic_instance is None:
        # Try OAuth first (preferred method)
        oauth_file = "oauth.json"
        oauth_config_file = "oauth_config.json"
        
        if os.path.exists(oauth_file) and os.path.exists(oauth_config_file):
            try:
                # Load OAuth credentials
                with open(oauth_config_file, 'r') as f:
                    oauth_config = json.load(f)
                
                client_id = oauth_config.get('client_id')
                client_secret = oauth_config.get('client_secret')
                
                if client_id and client_secret:
                    oauth_credentials = OAuthCredentials(
                        client_id=client_id,
                        client_secret=client_secret
                    )
                    _ytmusic_instance = YTMusic(oauth_file, oauth_credentials=oauth_credentials)
                    print("Using OAuth authentication")
                    
                    # Test OAuth by trying a simple operation
                    try:
                        # Try to get library (this will fail if OAuth isn't working)
                        # But we'll catch the error and continue anyway
                        test_result = _ytmusic_instance.get_library_playlists(limit=1)
                        print("OAuth verified: Authentication is working")
                    except Exception as test_error:
                        error_msg = str(test_error).lower()
                        if "400" in str(test_error) or "invalid" in error_msg or "unauthorized" in error_msg:
                            print(f"Warning: OAuth may not be working properly: {test_error}")
                            print("OAuth credentials may be invalid or expired. Try re-running 'ytmusicapi oauth'")
                        else:
                            # Other errors are OK, OAuth is probably working
                            print("OAuth initialized (test skipped due to non-auth error)")
                    
                    return _ytmusic_instance
                else:
                    print("Warning: oauth_config.json missing client_id or client_secret")
            except Exception as e:
                print(f"Warning: Failed to use OAuth authentication: {e}")
                print("Falling back to headers_auth.json...")
        
        # Fallback to headers_auth.json
        auth_file = "headers_auth.json"
        if os.path.exists(auth_file):
            try:
                _ytmusic_instance = YTMusic(auth_file)
                print("Using headers_auth.json authentication")
                return _ytmusic_instance
            except Exception as e:
                print(f"Warning: Failed to use {auth_file}, falling back to default: {e}")
                print("Your cookies may have expired. Try refreshing headers_auth.json or setting up OAuth")
                _ytmusic_instance = YTMusic()
        else:
            # Try without auth (may trigger bot detection)
            print("Warning: No authentication found. Bot detection errors may occur.")
            print("Set up OAuth (recommended) or headers_auth.json (see README.md)")
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

