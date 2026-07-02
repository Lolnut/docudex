import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    STORAGE_PATH = os.environ.get("DOCUDAX_STORAGE_PATH", os.path.join(BASE_DIR, "uploads"))
    API_KEY = os.environ.get("DOCUDAX_API_KEY", "")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "SQLALCHEMY_DATABASE_URI",
        f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'docudex.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PER_PAGE = 20
