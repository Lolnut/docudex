from datetime import datetime, timezone

from app.models import db


class Queue(db.Model):
    __tablename__ = "queue"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    filename = db.Column(db.Text, nullable=False)
    file_path = db.Column(db.Text, nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    added_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    status = db.Column(db.Text, nullable=False, default="queued")
    error_message = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "added_at": self.added_at.isoformat() if self.added_at else None,
            "status": self.status,
            "error_message": self.error_message,
        }
