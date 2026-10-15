import subprocess
import os
from config import FFMPEG_PATH

def merge_vocals_instrumental(vocal_path, instrumental_path, output_path): # склейка вокала и инструментала без потери громкости
    cmd = [
        FFMPEG_PATH,
        "-i", vocal_path,
        "-i", instrumental_path,
        "-filter_complex", "amix=inputs=2:duration=longest:dropout_transition=0:weights=1 1",
        "-y", output_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ошибка ffmpeg при склейке: {res.stderr}")
    return output_path