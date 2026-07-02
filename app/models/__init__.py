from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from app.models.pdf import Pdf, PdfText, PdfTag
from app.models.queue import Queue
from app.models.pairing import PairingRequest

__all__ = ["db", "Pdf", "PdfText", "PdfTag", "Queue", "PairingRequest"]
