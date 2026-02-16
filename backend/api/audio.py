import os
import subprocess
import struct
from typing import Optional, Dict

AUDIO_CACHE_DIR = os.path.join("cache", "audio")
DFPWM_CACHE_DIR = os.path.join("cache", "dfpwm")
os.makedirs(DFPWM_CACHE_DIR, exist_ok=True)

# DFPWM encoding parameters
SAMPLE_RATE = 48000
BYTES_PER_SAMPLE = 1  # DFPWM is 8-bit

async def get_audio_chunk(video_id: str, offset: int, size: int, channel: Optional[str] = None) -> Dict:
    """
    Get audio chunk in DFPWM format.
    offset: byte offset in DFPWM file
    size: chunk size in bytes
    channel: "left" or "right" for stereo, None for mono
    
    Returns: {data: hex_string, done: bool}
    """
    try:
        # Ensure audio is converted to DFPWM
        dfpwm_file = ensure_dfpwm_ready(video_id, channel)
        
        if not dfpwm_file or not os.path.exists(dfpwm_file):
            return {"data": "", "done": True}
        
        file_size = os.path.getsize(dfpwm_file)
        
        # Check if we're past the end
        if offset >= file_size:
            return {"data": "", "done": True}
        
        # Read chunk
        with open(dfpwm_file, 'rb') as f:
            f.seek(offset)
            chunk_data = f.read(size)
        
        # Convert to hex string
        hex_data = chunk_data.hex()
        
        # Check if this is the last chunk
        done = (offset + len(chunk_data)) >= file_size
        
        return {
            "data": hex_data,
            "done": done
        }
        
    except Exception as e:
        print(f"Audio chunk error for {video_id}: {e}")
        return {"data": "", "done": True}

def ensure_dfpwm_ready(video_id: str, channel: Optional[str] = None) -> Optional[str]:
    """Ensure DFPWM file exists, create if needed"""
    if channel:
        dfpwm_file = os.path.join(DFPWM_CACHE_DIR, f"{video_id}_{channel}.dfpwm")
    else:
        dfpwm_file = os.path.join(DFPWM_CACHE_DIR, f"{video_id}.dfpwm")
    
    if os.path.exists(dfpwm_file):
        return dfpwm_file
    
    # Find source audio file
    audio_file = None
    for ext in ['m4a', 'mp3', 'webm', 'opus']:
        test_file = os.path.join(AUDIO_CACHE_DIR, f"{video_id}.{ext}")
        if os.path.exists(test_file):
            audio_file = test_file
            break
    
    if not audio_file:
        # Audio not downloaded yet, return None
        return None
    
    try:
        # Convert to DFPWM using ffmpeg
        # DFPWM is a specific format - we'll convert to raw PCM first, then to DFPWM
        # For now, we'll use a simpler approach: convert to mono/stereo PCM and encode
        
        if channel:
            # Extract specific channel for stereo
            pcm_file = dfpwm_file.replace('.dfpwm', f'_{channel}.pcm')
            if channel == 'left':
                pan_filter = 'pan=mono|c0=0.5*c0'
            else:  # right
                pan_filter = 'pan=mono|c0=0.5*c1'
        else:
            # Mono - mix both channels
            pcm_file = dfpwm_file.replace('.dfpwm', '.pcm')
            pan_filter = 'pan=mono|c0=0.5*c0+0.5*c1'
        
        # Convert to PCM first
        cmd_pcm = [
            'ffmpeg', '-i', audio_file,
            '-f', 's16le',  # 16-bit signed little-endian PCM
            '-ar', str(SAMPLE_RATE),
            '-af', pan_filter,
            '-y',  # Overwrite
            pcm_file
        ]
        
        subprocess.run(cmd_pcm, capture_output=True, check=True)
        
        # Convert PCM to DFPWM
        # DFPWM (Differential Pulse-Width Modulation) encoder
        # This is a simplified DFPWM1a encoder
        with open(pcm_file, 'rb') as f_in, open(dfpwm_file, 'wb') as f_out:
            # DFPWM state
            charge = 0
            strength = 0
            
            # Read 16-bit PCM samples
            while True:
                chunk = f_in.read(2)
                if len(chunk) < 2:
                    break
                
                # Convert 16-bit PCM to signed sample (-32768 to 32767)
                sample = struct.unpack('<h', chunk)[0]
                # Normalize to -128 to 127 range
                target = (sample >> 8) & 0xFF
                if sample < 0:
                    target = target | 0x80
                
                # DFPWM encoding
                diff = target - charge
                if diff > 0:
                    output = 0xFF
                    charge += min(diff, strength + 1)
                else:
                    output = 0x00
                    charge += max(diff, -strength - 1)
                
                # Update strength (simplified)
                if abs(diff) > 0:
                    strength = min(127, strength + 1)
                else:
                    strength = max(0, strength - 1)
                
                f_out.write(bytes([output]))
        
        # Clean up PCM file
        if os.path.exists(pcm_file):
            os.remove(pcm_file)
        
        return dfpwm_file
        
    except Exception as e:
        print(f"DFPWM conversion error for {video_id}: {e}")
        return None

