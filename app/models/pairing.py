from datetime import datetime, timezone

from app.models import db


class PairingRequest(db.Model):
    __tablename__ = "pairing_requests"

    id = db.Column(db.Text, primary_key=True)
    agent_id = db.Column(db.Text, nullable=False)
    nonce = db.Column(db.Text, nullable=False)
    pairing_token = db.Column(db.Text, nullable=True)
    status = db.Column(db.Text, nullable=False, default="pending")
    ip_address = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    expires_at = db.Column(db.DateTime, nullable=False)
    approved_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "nonce": self.nonce,
            "status": self.status,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
        }
