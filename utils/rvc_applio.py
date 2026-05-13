################################################################################################################
#                                                                                                              #
#  Тут мы просто общаемся с rvc клиентом. Вся програмная часть уже есть в Applio. Мы обращаемся к rvc сервису  #
#  по его эндпоинтам с точным пейлоадом из 60 параметров, кормим ему вокал и получаем меш. Советую не редачить #
#                                                                                                              #
################################################################################################################

import requests
import time
import json
import uuid
import sys
import os
import shutil
import librosa
import soundfile as sf

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import *

base = os.path.dirname(os.path.abspath(__file__)) # получаем корень репозитория

def preprocess_audio(input_path, output_path, target_sr=16000):
    audio, sr = librosa.load(input_path, sr=target_sr, mono=True)
    sf.write(output_path, audio, target_sr)
    return output_path

def applio_process_voice(audio_path, speaker="valakas", pitch=0):

    preprocessed_path = audio_path.replace(".wav", "_preprocessed.wav")
    preprocess_audio(audio_path, preprocessed_path)

    applio_assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "applio", "assets", "audios")
    os.makedirs(applio_assets_dir, exist_ok=True)
    input_in_applio = os.path.join(applio_assets_dir, "vocals.wav")
    shutil.copy2(preprocessed_path, input_in_applio)

    output_in_applio = os.path.join(applio_assets_dir, "vocals_output.wav")
    if os.path.exists(output_in_applio):
        os.remove(output_in_applio)

    model_pth = f"applio\\logs\\{speaker}\\{speaker}.pth"
    model_index = f"applio\\logs\\{speaker}\\{speaker}.index"

    if not os.path.exists(os.path.join(base, model_pth)):
        print(f"Модель {model_pth} не найдена")

    init_session = str(uuid.uuid4())[:12]


    # пэйлоад
    payload = {
        "data": [
            True, pitch, RVC_INDEX_RATE, 1, 0.5, RVC_F0_METHOD,
            "assets\\audios\\vocals.wav",
            "assets\\audios\\vocals_output.wav",
            model_pth,
            model_index,
            False, False, 1, False, 155, False, 0.5, "WAV",
            "contentvec", None, False, 1, 1, False, False, False, False, False, False,
            False, False, False, False, False, 0.5, 0.5, 0.33, 0.4, 1, 0, 0,
            -6, 0.05, 0, 25, 1, 0.25, 7, 0, 0.5, 8,
            -6, 0, 1, 1, 100, 0.5, 0, 0.5, 0
        ],
        "fn_index": APPLIO_FN_INDEX,
        "trigger_id": APPLIO_TRIGGER_ID,
        "session_hash": init_session
    }

    try:
        queue_response = requests.post(
            APPLIO_URL,
            json=payload,
            timeout=30
        )
        queue_response.raise_for_status()
        queue_data = queue_response.json()

        if "event_id" not in queue_data:
            raise Exception("Applio не вернул event_id")

        real_session = queue_data.get("session_hash", init_session)

        params = {"session_hash": real_session}
        headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}

        with requests.get(SSE_URL, params=params, headers=headers, stream=True, timeout=120) as response:
            response.raise_for_status()
            buffer = ""
            for chunk in response.iter_content(chunk_size=1, decode_unicode=True):
                if chunk:
                    buffer += chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            try:
                                data = json.loads(data_str)
                                if data.get("msg") == "process_completed":
                                    if data.get("success") is False:
                                        error_msg = data.get("output", {}).get("error") or "Неизвестная ошибка"
                                        raise Exception(f"Applio вернул ошибку: {error_msg}")

                                    timeout_file = time.time() + 10
                                    while time.time() < timeout_file:
                                        if os.path.exists(output_in_applio):
                                            break
                                        time.sleep(0.5)

                                    if not os.path.exists(output_in_applio):
                                        raise Exception("Файл не появился после завершения процесса")

                                    unique_name = str(uuid.uuid4())[:8] + "_voice.wav"
                                    temp_output = os.path.join(os.path.dirname(audio_path), unique_name)
                                    shutil.copy2(output_in_applio, temp_output)

                                    os.remove(input_in_applio)
                                    os.remove(output_in_applio)

                                    return temp_output

                            except json.JSONDecodeError:
                                pass

        raise Exception("Не дождались")

    except Exception as e:
        raise Exception(f"Ошибка: {e}")

    finally:
        if os.path.exists(preprocessed_path):
            os.remove(preprocessed_path)