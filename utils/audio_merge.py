import subprocess
import os

def merge_vocals_instrumental(vocal_path, instrumental_path, output_path): # склеиваем через ffmpeg
    cmd = [
        "ffmpeg",
        "-i", vocal_path,
        "-i", instrumental_path,
        "-filter_complex", "amix=inputs=2:duration=longest",
        "-y", output_path
    ]
    subprocess.run(cmd, check=True)
    return output_path