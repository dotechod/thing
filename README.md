# CC:Tweaked YouTube Music Backend

Backend server for the CC:Tweaked YouTube Music Player. Provides API endpoints for searching, processing, and streaming YouTube Music content.

## Features

- YouTube Music search
- Audio processing and DFPWM conversion
- Lyrics extraction
- ASCII artwork generation
- Playlist support
- Audio chunk streaming

## Requirements

- Python 3.8+
- FFmpeg (for audio processing)

### Installing FFmpeg

**Windows:**
- Download from https://ffmpeg.org/download.html
- Extract and add to PATH

**Linux:**
```bash
sudo apt-get install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. **Set up authentication** (required to avoid bot detection errors):

   **Option A: OAuth (Recommended - More Reliable)**
   
   As of November 2024, YouTube Music requires OAuth authentication for best results:
   
   1. Get OAuth credentials from Google Cloud Console:
      - Go to [Google Cloud Console](https://console.cloud.google.com/)
      - Create a new project or select an existing one
      - Enable the YouTube Data API v3
      - Go to "Credentials" → "Create Credentials" → "OAuth client ID"
      - Select "TVs and Limited Input devices" as the application type
      - Save your `client_id` and `client_secret`
   
   2. Run the OAuth setup:
      ```bash
      ytmusicapi oauth
      ```
      Follow the instructions to complete the OAuth flow. This creates `oauth.json`.
   
   3. Create `oauth_config.json` in the backend directory:
      ```json
      {
        "client_id": "YOUR_CLIENT_ID_HERE.apps.googleusercontent.com",
        "client_secret": "YOUR_CLIENT_SECRET_HERE"
      }
      ```
      You can copy `oauth_config.json.example` and fill in your credentials.
   
   **Option B: Headers Auth (Fallback - May Expire)**
   
   If you prefer cookie-based authentication:
   - Create `headers_auth.json` in the backend directory
   - Follow instructions at https://ytmusicapi.readthedocs.io/en/latest/setup/browser.html
   - **Note:** Cookies expire after a few weeks/months and need to be refreshed
   
   The backend will automatically use OAuth if available, otherwise falls back to `headers_auth.json`.

## Usage

Start the server:
```bash
python main.py
```

The server will run on `http://localhost:3000`

## API Endpoints

### POST `/api/search`
Search YouTube Music
```json
{
  "query": "search term",
  "maxResults": 10
}
```

### POST `/api/process`
Process a video/playlist
```json
{
  "url": "video_id_or_url"
}
```

### GET `/api/lyrics/{video_id}`
Get lyrics for a video

### GET `/api/artwork/{video_id}`
Get ASCII artwork for a video

### GET `/api/audio/{video_id}/chunk`
Get audio chunk
- Query params: `offset`, `size`, `channel` (optional: "left" or "right")

### POST `/api/playlist`
Get playlist tracks
```json
{
  "playlistId": "playlist_id"
}
```

## Cache

The backend caches:
- Audio files in `cache/audio/`
- DFPWM files in `cache/dfpwm/`
- Metadata in `cache/metadata/`
- Lyrics in `cache/lyrics/`
- Artwork in `cache/artwork/`

## Notes

- First-time processing of a video may take a while as it downloads and converts audio
- DFPWM encoding is done on-the-fly
- The backend supports both mono and stereo audio

## Cloud/VPS Limitations

**Important:** If you're running this on a cloud/VPS provider (AWS, Google Cloud, Oracle Cloud, DigitalOcean, etc.), YouTube's bot detection will likely block audio downloads. Cloud IPs are heavily flagged by YouTube.

**Solutions:**
1. **Use Cloudflare WARP (Recommended for Cloud)** - WARP can help mask your cloud IP:
   ```bash
   # Install WARP
   curl -fsSL https://pkg.cloudflareclient.com/pubkey.gpg | sudo gpg --yes --dearmor --output /usr/share/keyrings/cloudflare-warp-archive-keyring.gpg
   echo "deb [arch=amd64 signed-by=/usr/share/keyrings/cloudflare-warp-archive-keyring.gpg] https://pkg.cloudflareclient.com/ $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflare-client.list
   sudo apt-get update && sudo apt-get install cloudflare-warp
   
   # Set up WARP in proxy mode
   warp-cli register
   warp-cli set-mode proxy
   warp-cli connect
   
   # Enable WARP in the backend (set before starting)
   export USE_WARP=true
   export WARP_PROXY=socks5://127.0.0.1:40000  # Default WARP proxy
   python main.py
   ```

2. **Use a residential IP** - Run the backend on a home computer or residential internet connection
3. **Use a VPN/proxy** - Route traffic through a residential VPN or proxy service
4. **Pre-download audio** - Manually download audio files and place them in `cache/audio/` with the format `{video_id}.m4a`
5. **Use fresh cookies** - If using `headers_auth.json`, export very fresh cookies from your browser while logged into YouTube

**Testing OAuth:**
Run `python test_oauth.py` to verify your OAuth authentication is working correctly.

Even with OAuth authentication, YouTube may still block requests from cloud IPs. This is a limitation of YouTube's bot detection system, not the backend code.

