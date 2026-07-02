import os

from flask import Flask

from app.config import Config
from app.models import db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    with app.app_context():
        from app.models.queue import Queue
        from app.models.pdf import Pdf, PdfText, PdfTag
        from app.models.pairing import PairingRequest
        db_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        db.create_all()
        _init_fts(app)
        _cleanup_old_pairings()

    from app.routes.ui import ui_bp
    from app.routes.api import api_bp
    app.register_blueprint(ui_bp)
    app.register_blueprint(api_bp)

    return app


def _init_fts(app):
    with app.app_context():
        db.session.execute(db.text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS pdfs_fts USING fts5(
                filename,
                page_content,
                content='pdfs',
                content_rowid='id'
            )
        """))
        db.session.commit()


def _cleanup_old_pairings():
    from datetime import datetime, timezone, timedelta
    from app.models.pairing import PairingRequest
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    deleted = PairingRequest.query.filter(
        PairingRequest.status.in_(["expired", "denied"]),
        PairingRequest.expires_at < cutoff
    ).delete()
    if deleted:
        db.session.commit()
