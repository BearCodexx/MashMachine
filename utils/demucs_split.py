######################################################################################################################
#                                                                                                                    #
#  БОЛЬШУЮ ЧАСТЬ ПИСАЛ НЕ Я, поскольку не умею пользоваться демуксом в его негуишном виде. Если у вас не NVIDIA GPU  #
#  или мало видеопамяти/устаревшие CUDA, тогда принудительно выставьте CPU-режим (но это будет медленнее в 2-5 раз!) #
#                                                                                                                    #
######################################################################################################################

import os
import torch
import soundfile as sf
import librosa
from demucs import pretrained
from demucs.apply import apply_model
from config import DEMUCS_MODEL

def split_vocals_instrumental(input_audio_path, output_dir):
    # Проверяем доступность GPU. элсе cpu может не работать. Тогда принудительно поставьте cpu
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    # print(f"Используется устройство: {device}") # раскоментите, если обработка кажется медленной

    # загружаем предобученную модель Demucs
    model = pretrained.get_model(DEMUCS_MODEL)
    model.to(device)  # переносим модель на GPU/CPU
    model.eval()

    # загружаем аудио
    audio, sr = librosa.load(input_audio_path, mono=False, sr=model.samplerate)

    # добавляем размерность batch (1, channels, samples)
    audio_tensor = torch.from_numpy(audio).float().unsqueeze(0).to(device)

    # разделение через apply_model
    with torch.no_grad():
        sources = apply_model(model, audio_tensor, device=device, shifts=1, split=True, overlap=0.25)

    # sources - тензор (batch, sources, channels, samples)
    # индексы источников: 0 - drums, 1 - bass, 2 - other, 3 - vocals
    vocal = sources[0, 3].cpu().numpy()      # вокал
    instrumental = sources[0, 2].cpu().numpy()  # инструментал (other)

    # сохраняем
    base_name = os.path.splitext(os.path.basename(input_audio_path))[0]
    vocal_path = os.path.join(output_dir, f"{base_name}_vocals.wav")
    instrumental_path = os.path.join(output_dir, f"{base_name}_instrumental.wav")

    sf.write(vocal_path, vocal.T, sr)
    sf.write(instrumental_path, instrumental.T, sr)

    return vocal_path, instrumental_path