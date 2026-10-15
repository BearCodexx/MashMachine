import os
import sys
import time
import json
import uuid
import shutil
import requests
import librosa
import soundfile as sf

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BASE_DIR, APPLIO_DIR, APPLIO_URL, SSE_URL, APPLIO_FN_INDEX, APPLIO_TRIGGER_ID, RVC_INDEX_RATE, RVC_F0_METHOD

def preprocess_audio(input_path, output_path): # приводим вокал к моно без обрезки частот до 16 кгц
    audio, sr = librosa.load(input_path, sr=None, mono=True)
    sf.write(output_path, audio, sr)
    return output_path

def resolve_model_paths(applio_dir: str, speaker: str): # гибкий поиск весов модели и индекса в logs
    folder = os.path.join(applio_dir, "logs", speaker)
    if not os.path.exists(folder):
        raise FileNotFoundError(f"папка модели logs/{speaker} не найдена в {applio_dir}")

    # поиск .pth файла модели
    pth_file = os.path.join(folder, f"{speaker}.pth")
    if not os.path.exists(pth_file):
        pths = [f for f in os.listdir(folder) if f.lower().endswith(".pth")]
        if not pths:
            raise FileNotFoundError(f"в папке logs/{speaker} не найден файл .pth")
        pth_file = os.path.join(folder, pths[0])

    # поиск .index файла индекса
    index_file = os.path.join(folder, f"{speaker}.index")
    if not os.path.exists(index_file):
        indices = [f for f in os.listdir(folder) if f.lower().endswith(".index")]
        index_file = os.path.join(folder, indices[0]) if indices else ""

    rel_pth = os.path.relpath(pth_file, applio_dir).replace("/", "\\")
    rel_index = os.path.relpath(index_file, applio_dir).replace("/", "\\") if index_file else ""
    return rel_pth, rel_index

def applio_process_voice(audio_path, speaker="valakas", pitch=0): # инференс голоса через applio api
    task_id = uuid.uuid4().hex[:8]
    preprocessed_path = audio_path.replace(".wav", f"_{task_id}_mono.wav")
    preprocess_audio(audio_path, preprocessed_path)

    applio_assets_dir = os.path.join(APPLIO_DIR, "assets", "audios")
    os.makedirs(applio_assets_dir, exist_ok=True)

    input_filename = f"vocals_{task_id}.wav"
    output_filename = f"vocals_{task_id}_out.wav"

    input_in_applio = os.path.join(applio_assets_dir, input_filename)
    output_in_applio = os.path.join(applio_assets_dir, output_filename)
    shutil.copy2(preprocessed_path, input_in_applio)

    if os.path.exists(output_in_applio):
        os.remove(output_in_applio)

    # автоматический поиск файлов весов и индекса
    model_pth, model_index = resolve_model_paths(APPLIO_DIR, speaker)

    init_session = str(uuid.uuid4())[:12]

    # пейлоад для инференса applio
    payload = {
        "data": [
            True, pitch, RVC_INDEX_RATE, 1, 0.5, RVC_F0_METHOD,
            f"assets\\audios\\{input_filename}",
            f"assets\\audios\\{output_filename}",
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
        queue_response = requests.post(APPLIO_URL, json=payload, timeout=30)
        queue_response.raise_for_status()
        queue_data = queue_response.json()

        if "event_id" not in queue_data:
            raise RuntimeError("applio не вернул event_id в очереди")

        real_session = queue_data.get("session_hash", init_session)
        params = {"session_hash": real_session}
        headers = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}

        with requests.get(SSE_URL, params=params, headers=headers, stream=True, timeout=180) as response:
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
                                        err = data.get("output", {}).get("error") or "неизвестная ошибка"
                                        raise RuntimeError(f"applio вернул ошибку: {err}")

                                    # ждем появления сгенерированного файла
                                    deadline = time.time() + 15
                                    while time.time() < deadline:
                                        if os.path.exists(output_in_applio):
                                            break
                                        time.sleep(0.3)

                                    if not os.path.exists(output_in_applio):
                                        raise FileNotFoundError("файл результата не найден после обработки")

                                    unique_name = f"{task_id}_voice.wav"
                                    temp_output = os.path.join(os.path.dirname(audio_path), unique_name)
                                    shutil.copy2(output_in_applio, temp_output)
                                    return temp_output
                            except json.JSONDecodeError:
                                pass

        raise TimeoutError("превышено время ожидания ответа applio")

    finally:
        # чистим временные файлы инференса
        for p in [preprocessed_path, input_in_applio, output_in_applio]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass