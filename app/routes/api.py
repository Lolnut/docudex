import os
import hashlib

from flask import Blueprint, request, jsonify, current_app

from app.models import db
from app.models.queue import Queue
from app.models.pdf import Pdf, PdfText, PdfTag
from app.services.file_storage import FileStorage
from app.services.pdf_processor import compute_sha256, extract_text

api_bp = Blueprint("api", __name__)


def check_api_key():
    api_key = current_app.config["API_KEY"]
    if not api_key:
        return None
    request_key = request.headers.get("X-API-Key")
    if request_key != api_key:
        return jsonify({"error": "Invalid or missing API key"}), 401
    return None


@api_bp.route("/agent/search", methods=["GET"])
def search():
    auth_error = check_api_key()
    if auth_error:
        return auth_error

    query = request.args.get("q", "")
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400

    results = db.session.execute(db.text("""
        SELECT DISTINCT pdfs.id, pdfs.filename, pdfs.summary, pdfs.total_pages
        FROM pdfs_fts
        JOIN pdfs ON pdfs.rowid = pdfs_fts.rowid
        WHERE pdfs_fts MATCH :query
        ORDER BY rank
    """), {"query": query}).fetchall()

    documents = []
    for row in results:
        pdf = db.session.get(Pdf, row[0])
        if pdf:
            documents.append(pdf.to_dict())

    return jsonify({"items": documents, "total": len(documents)})


@api_bp.route("/agent/documents", methods=["GET"])
def agent_documents():
    auth_error = check_api_key()
    if auth_error:
        return auth_error

    page = request.args.get("page", 1, type=int)
    per_page = current_app.config["PER_PAGE"]

    pagination = Pdf.query.order_by(Pdf.indexed_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "items": [p.to_dict() for p in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "page": page,
    })


@api_bp.route("/agent/documents/<int:pdf_id>", methods=["GET"])
def agent_document(pdf_id):
    auth_error = check_api_key()
    if auth_error:
        return auth_error

    pdf = db.session.get(Pdf, pdf_id)
    if not pdf:
        return jsonify({"error": "Document not found"}), 404

    return jsonify(pdf.to_dict())


@api_bp.route("/agent/categorize", methods=["POST"])
def categorize():
    auth_error = check_api_key()
    if auth_error:
        return auth_error

    queued = Queue.query.filter_by(status="queued").order_by(Queue.added_at).all()

    if not queued:
        return jsonify({"message": "No queued files"}), 200

    results = []
    for queue_item in queued:
        try:
            queue_item.status = "processing"
            db.session.commit()

            sha256_hash = compute_sha256(queue_item.file_path)

            existing = Pdf.query.filter_by(sha256_hash=sha256_hash).first()
            if existing:
                queue_item.status = "done"
                queue_item.error_message = "Duplicate hash"
                db.session.commit()
                results.append({
                    "queue_id": queue_item.id,
                    "filename": queue_item.filename,
                    "status": "skipped_duplicate",
                    "existing_id": existing.id,
                })
                continue

            pages_data, total_pages = extract_text(queue_item.file_path)

            pdf = Pdf(
                filename=queue_item.filename,
                file_path=queue_item.file_path,
                file_size=queue_item.file_size,
                sha256_hash=sha256_hash,
                total_pages=total_pages,
            )
            db.session.add(pdf)
            db.session.flush()

            for page_data in pages_data:
                pdf_text = PdfText(
                    pdf_id=pdf.id,
                    page_number=page_data["page_number"],
                    content=page_data["content"],
                )
                db.session.add(pdf_text)

            db.session.commit()

            queue_item.status = "done"
            db.session.commit()

            results.append({
                "queue_id": queue_item.id,
                "filename": queue_item.filename,
                "status": "indexed",
                "pdf_id": pdf.id,
                "pages": total_pages,
            })
        except Exception as e:
            db.session.rollback()
            queue_item.status = "failed"
            queue_item.error_message = str(e)
            db.session.commit()
            results.append({
                "queue_id": queue_item.id,
                "filename": queue_item.filename,
                "status": "error",
                "error": str(e),
            })

    return jsonify({"results": results})
