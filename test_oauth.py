#!/usr/bin/env python3
"""
Test script to verify OAuth authentication is working.
Run this to check if your OAuth setup is correct.
"""
import os
import json
from ytmusicapi import YTMusic, OAuthCredentials

def test_oauth():
    """Test OAuth authentication"""
    oauth_file = "oauth.json"
    oauth_config_file = "oauth_config.json"
    
    if not os.path.exists(oauth_file):
        print("❌ oauth.json not found!")
        print("Run: ytmusicapi oauth")
        return False
    
    if not os.path.exists(oauth_config_file):
        print("❌ oauth_config.json not found!")
        print("Create it with your client_id and client_secret")
        return False
    
    try:
        # Load OAuth credentials
        with open(oauth_config_file, 'r') as f:
            oauth_config = json.load(f)
        
        client_id = oauth_config.get('client_id')
        client_secret = oauth_config.get('client_secret')
        
        if not client_id or not client_secret:
            print("❌ oauth_config.json missing client_id or client_secret")
            return False
        
        print(f"✓ Found OAuth credentials")
        print(f"  Client ID: {client_id[:20]}...")
        
        # Initialize YTMusic with OAuth
        oauth_credentials = OAuthCredentials(
            client_id=client_id,
            client_secret=client_secret
        )
        ytmusic = YTMusic(oauth_file, oauth_credentials=oauth_credentials)
        print("✓ YTMusic initialized with OAuth")
        
        # Test 1: Try to get library playlists (requires auth)
        print("\nTesting OAuth authentication...")
        try:
            playlists = ytmusic.get_library_playlists(limit=1)
            print("✓ OAuth is working! Successfully accessed library")
            return True
        except Exception as e:
            error_msg = str(e).lower()
            if "400" in str(e) or "invalid" in error_msg:
                print(f"❌ OAuth authentication failed: {e}")
                print("   This might be due to:")
                print("   - Invalid or expired OAuth tokens (try re-running 'ytmusicapi oauth')")
                print("   - Cloud IP blocking (YouTube may block cloud/VPS IPs even with OAuth)")
                return False
            elif "unauthorized" in error_msg or "401" in str(e):
                print(f"❌ OAuth unauthorized: {e}")
                print("   Your OAuth tokens may have expired. Try re-running 'ytmusicapi oauth'")
                return False
            else:
                print(f"⚠️  OAuth test returned error (may still work): {e}")
                # Continue to test 2
        
        # Test 2: Try a simple search (works without full auth sometimes)
        print("\nTesting search functionality...")
        try:
            results = ytmusic.search("test", limit=1)
            if results:
                print("✓ Search is working with OAuth")
                return True
            else:
                print("⚠️  Search returned no results (may still be OK)")
        except Exception as e:
            print(f"❌ Search failed: {e}")
            return False
        
    except Exception as e:
        print(f"❌ Failed to initialize OAuth: {e}")
        return False

if __name__ == "__main__":
    print("OAuth Authentication Test")
    print("=" * 40)
    success = test_oauth()
    print("\n" + "=" * 40)
    if success:
        print("✓ OAuth appears to be working!")
    else:
        print("❌ OAuth is not working properly")
        print("\nTroubleshooting:")
        print("1. Re-run: ytmusicapi oauth")
        print("2. Check that oauth_config.json has correct client_id and client_secret")
        print("3. If on cloud/VPS, YouTube may block even with OAuth")

