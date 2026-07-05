import os
import hashlib

from flask import Blueprint, request, jsonify, current_app, g

from app.models import db
from app.models.queue import Queue
from app.models.pdf import Pdf, PdfText, PdfTag
from app.models.pairing import PairingRequest
from app.services.file_storage import FileStorage
from app.services.pdf_processor import compute_sha256, extract_text
from app.services.auth import generate_nonce, generate_pairing_token, verify_token

api_bp = Blueprint("api", __name__)


def check_api_key():
    api_key = current_app.config["API_KEY"]
    if api_key:
        print("[docudex] Warning: DOCUDEX_API_KEY is deprecated. Use agent pairing instead.")
        request_key = request.headers.get("X-API-Key")
        if request_key != api_key:
            return jsonify({"error": "Invalid or missing API key"}), 401
    return None


def require_jwt(f):
    from functools import wraps
    import json
    import base64

    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")
        payload = verify_token(token)
        if not payload:
            agent_id = None
            try:
                actual = token[7:] if token and token.startswith("Bearer ") else token
                parts = actual.split(".")
                if len(parts) == 3:
                    raw_payload = parts[1]
                    padding = 4 - len(raw_payload) % 4
                    if padding != 4:
                        raw_payload += "=" * padding
                    decoded = json.loads(base64.urlsafe_b64decode(raw_payload))
                    agent_id = decoded.get("sub")
            except Exception:
                pass

            if agent_id:
                pairing = PairingRequest.query.filter_by(
                    agent_id=agent_id, status="verified"
                ).order_by(PairingRequest.verified_at.desc()).first()
                if pairing:
                    new_token = generate_jwt(agent_id)
                    return jsonify({"token": new_token}), 200

            return jsonify({
                "error": "unauthenticated",
                "message": "Pair with the server first",
                "pairing_url": "/agent/pair",
            }), 401
        g.current_agent = payload["sub"]
        return f(*args, **kwargs)

    return decorated


@api_bp.route("/agent/search", methods=["GET"])
@require_jwt
def search():
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
@require_jwt
def agent_documents():
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
@require_jwt
def agent_document(pdf_id):
    pdf = db.session.get(Pdf, pdf_id)
    if not pdf:
        return jsonify({"error": "Document not found"}), 404

    return jsonify(pdf.to_dict())


@api_bp.route("/agent/categorize", methods=["POST"])
@require_jwt
def categorize():
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


@api_bp.route("/agent/pair", methods=["GET"])
def get_pairing():
    agent_id = request.args.get("agent_id", "unknown")

    existing = PairingRequest.query.filter_by(
        agent_id=agent_id, status="verified"
    ).order_by(PairingRequest.verified_at.desc()).first()
    if existing:
        return jsonify({
            "message": "Already paired",
            "pairing_id": existing.id,
            "verified_at": existing.verified_at.isoformat(),
        }), 200

    nonce = generate_nonce()
    pairing_id = os.urandom(8).hex()

    from datetime import datetime, timezone, timedelta
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    pairing = PairingRequest(
        id=pairing_id,
        agent_id=agent_id,
        nonce=nonce,
        status="pending",
        ip_address=request.remote_addr,
        expires_at=expires_at,
    )
    db.session.add(pairing)
    db.session.commit()

    return jsonify({
        "nonce": nonce,
        "pairing_url": f"/pair/approve?id={pairing_id}",
    }), 201


@api_bp.route("/agent/pair/verify", methods=["POST"])
def verify_pairing():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body required"}), 400

    pairing_id = data.get("pairing_id")
    nonce = data.get("nonce")
    pairing_token = data.get("pairing_token")

    if not all([pairing_id, nonce, pairing_token]):
        return jsonify({"error": "pairing_id, nonce, and pairing_token are required"}), 400

    pairing = db.session.get(PairingRequest, pairing_id)
    if not pairing:
        return jsonify({"error": "Invalid pairing request"}), 404

    if pairing.status != "approved":
        return jsonify({"error": "Pairing request not approved"}), 403

    if pairing.nonce != nonce:
        return jsonify({"error": "Invalid nonce"}), 403

    if pairing.pairing_token != pairing_token:
        return jsonify({"error": "Invalid pairing token"}), 403

    from datetime import datetime, timezone
    from app.services.auth import generate_jwt
    token = generate_jwt(pairing.agent_id)

    pairing.status = "verified"
    pairing.verified_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        "token": token,
        "agent_id": pairing.agent_id,
        "expires_in": 3600,
    })
