import os
import shutil

def cleanup_files(*paths): # удаляет временные файлы и папки
    for path in paths:
        if path is None:
            continue
        if os.path.isfile(path):
            os.remove(path)
        elif os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)