"""
Vertical Reel Video Generator (1080x1920).
Creates 12-20 second vertical reels using pan-and-zoom motion across clipping imagery
and staggered typography overlays via ffmpeg.
Scheduled for deployment in Phase 5 / Week 6.
"""

import os
import shutil
import subprocess
from typing import Dict, Any, Optional

class ReelRenderer:
    def __init__(self, output_dir: Optional[str] = None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.output_dir = output_dir or os.path.join(base_dir, "data", "rendered_reels")
        os.makedirs(self.output_dir, exist_ok=True)
        self.ffmpeg_path = shutil.which("ffmpeg")

    def is_ffmpeg_available(self) -> bool:
        return self.ffmpeg_path is not None

    def render_reel(self, card_image_path: str, post_data: Dict[str, Any], post_id: str) -> Optional[str]:
        """
        Builds vertical 1080x1920 video using ffmpeg zoompan filter.
        """
        if not self.is_ffmpeg_available():
            print("[Reels] ffmpeg not found in PATH. Reels generation will activate when ffmpeg is installed.")
            return None

        output_path = os.path.join(self.output_dir, f"reel_{post_id}.mp4")
        
        # 15 second slow Ken Burns zoom
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-loop", "1",
            "-i", card_image_path,
            "-vf", "scale=1080:1920,zoompan=z='min(zoom+0.0015,1.25)':d=375:s=1080x1920:fps=25",
            "-c:v", "libx264",
            "-t", "15",
            "-pix_fmt", "yuv420p",
            output_path
        ]
        
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"[Reels] Rendered vertical reel to: {output_path}")
            return output_path
        except Exception as e:
            print(f"[Reels] ffmpeg execution error: {e}")
            return None
