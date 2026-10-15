import os
import torch
import soundfile as sf
import librosa
import numpy as np
from demucs import pretrained
from demucs.apply import apply_model
from config import DEMUCS_MODEL

# глобальный кэш модели, чтобы не грузить с диска каждый раз
_cached_demucs_model = None

def get_demucs_model(): # загружаем и кэшируем модель demucs в памяти
    global _cached_demucs_model
    if _cached_demucs_model is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = pretrained.get_model(DEMUCS_MODEL)
        model.to(device)
        model.eval()
        _cached_demucs_model = (model, device)
    return _cached_demucs_model

def split_vocals_instrumental(input_audio_path, output_dir): # разделение трека на вокал и полный инструментал
    model, device = get_demucs_model()
    os.makedirs(output_dir, exist_ok=True)

    # загружаем аудио с целевым samplerate модели
    audio, sr = librosa.load(input_audio_path, mono=False, sr=model.samplerate)
    if audio.ndim == 1:
        audio = np.stack([audio, audio]) # делаем стерео если исходник моно

    # батч размерность (1, channels, samples)
    audio_tensor = torch.from_numpy(audio).float().unsqueeze(0).to(device)

    with torch.no_grad():
        sources = apply_model(model, audio_tensor, device=device, shifts=1, split=True, overlap=0.25)

    # источники в htdemucs: 0 drums, 1 bass, 2 other, 3 vocals
    vocal = sources[0, 3].cpu().numpy()
    instrumental = sources[0, :3].sum(0).cpu().numpy() # собираем полный инструментал с битом и басом

    base_name = os.path.splitext(os.path.basename(input_audio_path))[0]
    vocal_path = os.path.join(output_dir, f"{base_name}_vocals.wav")
    instrumental_path = os.path.join(output_dir, f"{base_name}_instrumental.wav")

    sf.write(vocal_path, vocal.T, sr)
    sf.write(instrumental_path, instrumental.T, sr)

    return vocal_path, instrumental_path