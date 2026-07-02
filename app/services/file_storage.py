import os
import shutil


class FileStorage:
    def __init__(self, base_path):
        self.base_path = base_path

    def ensure_dir(self):
        os.makedirs(self.base_path, exist_ok=True)

    def save(self, file_storage, filename):
        self.ensure_dir()
        dest = os.path.join(self.base_path, filename)
        file_storage.save(dest)
        return dest

    def delete(self, file_path):
        if os.path.exists(file_path):
            os.remove(file_path)

    def exists(self, file_path):
        return os.path.exists(file_path)
