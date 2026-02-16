import os
import requests
from PIL import Image
import io
from typing import Optional

ARTWORK_CACHE_DIR = os.path.join("cache", "artwork")
os.makedirs(ARTWORK_CACHE_DIR, exist_ok=True)

# Color mapping for CC:Tweaked colors
CC_COLORS = {
    0: '0',  # black
    1: '1',  # blue
    2: '2',  # brown
    3: '3',  # cyan
    4: '4',  # gray
    5: '5',  # green
    6: '6',  # lightBlue
    7: '7',  # lightGray
    8: '8',  # lime
    9: '9',  # magenta
    10: 'a', # orange
    11: 'b', # pink
    12: 'c', # purple
    13: 'd', # red
    14: 'e', # yellow
    15: 'f', # white
}

def rgb_to_cc_color(r: int, g: int, b: int) -> str:
    """Convert RGB to closest CC:Tweaked color"""
    # Simple color distance calculation
    colors = {
        (0, 0, 0): '0',      # black
        (0, 0, 170): '1',    # blue
        (102, 67, 0): '2',   # brown
        (0, 170, 170): '3',  # cyan
        (85, 85, 85): '4',   # gray
        (0, 170, 0): '5',    # green
        (102, 102, 255): '6', # lightBlue
        (170, 170, 170): '7', # lightGray
        (170, 255, 0): '8',  # lime
        (170, 0, 170): '9',  # magenta
        (255, 102, 0): 'a',  # orange
        (255, 192, 203): 'b', # pink
        (170, 0, 170): 'c',  # purple
        (255, 0, 0): 'd',    # red
        (255, 255, 0): 'e',  # yellow
        (255, 255, 255): 'f', # white
    }
    
    min_dist = float('inf')
    closest = '0'
    
    for (cr, cg, cb), color in colors.items():
        dist = ((r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2) ** 0.5
        if dist < min_dist:
            min_dist = dist
            closest = color
    
    return closest

async def get_artwork(video_id: str) -> str:
    """
    Get ASCII artwork for a video.
    Returns: Multi-line string with format "text|fg|bg" per line
    """
    cache_file = os.path.join(ARTWORK_CACHE_DIR, f"{video_id}.txt")
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            return f.read()
    
    try:
        # Try to get thumbnail from YouTube
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        
        # Try maxresdefault first, fallback to hqdefault
        response = requests.get(thumbnail_url, timeout=5)
        if response.status_code != 200:
            thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
            response = requests.get(thumbnail_url, timeout=5)
        
        if response.status_code == 200:
            # Convert image to ASCII art
            img = Image.open(io.BytesIO(response.content))
            
            # Resize to fit terminal (typical monitor is ~51x19 for scale 0.5)
            # Use a reasonable size for artwork
            target_width = 20
            target_height = 10
            
            img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
            img = img.convert('RGB')
            
            # Convert to ASCII with colors
            ascii_lines = []
            pixels = img.load()
            
            # ASCII characters from dark to light
            ascii_chars = " .:-=+*#%@"
            
            for y in range(target_height):
                line_text = ""
                line_fg = ""
                line_bg = ""
                
                for x in range(target_width):
                    r, g, b = pixels[x, y]
                    
                    # Calculate brightness
                    brightness = (r + g + b) / 3.0
                    char_idx = int((brightness / 255.0) * (len(ascii_chars) - 1))
                    char = ascii_chars[char_idx]
                    
                    # Use background color based on pixel color
                    bg_color = rgb_to_cc_color(r, g, b)
                    fg_color = '0' if brightness > 128 else 'f'  # Black text on light, white on dark
                    
                    line_text += char
                    line_fg += fg_color
                    line_bg += bg_color
                
                # Format: text|fg|bg
                ascii_lines.append(f"{line_text}|{line_fg}|{line_bg}")
            
            artwork_text = "\n".join(ascii_lines)
            
            # Cache artwork
            with open(cache_file, 'w', encoding='utf-8') as f:
                f.write(artwork_text)
            
            return artwork_text
        else:
            return ""
            
    except Exception as e:
        print(f"Artwork error for {video_id}: {e}")
        return ""

