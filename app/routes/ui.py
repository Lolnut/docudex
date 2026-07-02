import os

from flask import Blueprint, request, jsonify, render_template, current_app
from werkzeug.utils import secure_filename

from app.models import db
from app.models.queue import Queue
from app.models.pdf import Pdf, PdfText, PdfTag
from app.services.file_storage import FileStorage

ui_bp = Blueprint("ui", __name__)


def get_storage():
    return FileStorage(current_app.config["STORAGE_PATH"])


@ui_bp.route("/")
def index():
    return render_template("index.html")


@ui_bp.route("/api/upload", methods=["POST"])
def upload():
    files = request.files.getlist("files")
    if not files or files[0].filename == "":
        return jsonify({"error": "No files provided"}), 400

    results = []
    for file in files:
        filename = secure_filename(file.filename)
        if not filename.lower().endswith(".pdf"):
            results.append({"filename": filename, "status": "rejected", "error": "Only PDF files allowed"})
            continue

        try:
            file_path = get_storage().save(file, filename)
            file_size = os.path.getsize(file_path)

            queue_item = Queue(
                filename=filename,
                file_path=file_path,
                file_size=file_size,
            )
            db.session.add(queue_item)
            db.session.commit()

            results.append({"filename": filename, "status": "queued", "id": queue_item.id})
        except Exception as e:
            db.session.rollback()
            results.append({"filename": filename, "status": "error", "error": str(e)})

    return jsonify({"items": results}), 201


@ui_bp.route("/api/queue", methods=["GET"])
def get_queue():
    items = Queue.query.order_by(Queue.added_at.desc()).all()
    return jsonify({"items": [i.to_dict() for i in items]})


@ui_bp.route("/api/queue/<int:item_id>", methods=["DELETE"])
def delete_queue_item(item_id):
    item = db.session.get(Queue, item_id)
    if not item:
        return jsonify({"error": "Queue item not found"}), 404

    get_storage().delete(item.file_path)
    db.session.delete(item)
    db.session.commit()

    return jsonify({"message": "Deleted"}), 200


@ui_bp.route("/api/documents", methods=["GET"])
def get_documents():
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


@ui_bp.route("/api/documents/<int:pdf_id>", methods=["DELETE"])
def delete_document(pdf_id):
    pdf = db.session.get(Pdf, pdf_id)
    if not pdf:
        return jsonify({"error": "Document not found"}), 404

    get_storage().delete(pdf.file_path)

    db.session.delete(pdf)
    db.session.commit()

    return jsonify({"message": "Deleted"}), 200
