from datetime import datetime, timezone

from app.models import db


class Pdf(db.Model):
    __tablename__ = "pdfs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    filename = db.Column(db.Text, nullable=False)
    file_path = db.Column(db.Text, nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    sha256_hash = db.Column(db.Text, unique=True, nullable=False)
    total_pages = db.Column(db.Integer, nullable=False)
    summary = db.Column(db.Text, nullable=True)
    uploaded_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    indexed_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    pages = db.relationship("PdfText", back_populates="pdf", cascade="all, delete-orphan")
    tags = db.relationship("PdfTag", back_populates="pdf", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "sha256_hash": self.sha256_hash,
            "total_pages": self.total_pages,
            "summary": self.summary,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "indexed_at": self.indexed_at.isoformat() if self.indexed_at else None,
            "tags": [t.tag for t in self.tags],
        }


class PdfText(db.Model):
    __tablename__ = "pdf_text"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pdf_id = db.Column(db.Integer, db.ForeignKey("pdfs.id"), nullable=False)
    page_number = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)

    pdf = db.relationship("Pdf", back_populates="pages")

    def to_dict(self):
        return {
            "id": self.id,
            "pdf_id": self.pdf_id,
            "page_number": self.page_number,
            "content": self.content,
        }


class PdfTag(db.Model):
    __tablename__ = "pdf_tags"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pdf_id = db.Column(db.Integer, db.ForeignKey("pdfs.id"), nullable=False)
    tag = db.Column(db.Text, nullable=False)

    pdf = db.relationship("Pdf", back_populates="tags")

    def to_dict(self):
        return {
            "id": self.id,
            "pdf_id": self.pdf_id,
            "tag": self.tag,
        }
