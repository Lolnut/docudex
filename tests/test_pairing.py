import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app import create_app
from app.models import db


@pytest.fixture
def app():
    os.environ["DOCUDEX_JWT_SECRET"] = "test-secret-for-unit-tests-only"
    app = create_app()
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()
        yield app

        db.session.remove()


@pytest.fixture
def client(app):
    with app.test_client() as client:
        yield client
        with app.app_context():
            db.drop_all()
            db.create_all()


@pytest.fixture
def secret():
    return "test-secret-for-unit-tests-only"


# ── Auth Service Tests ──────────────────────────────────────────────

class TestAuthNonce:
    def test_generate_nonce_returns_string(self, client):
        from app.services.auth import generate_nonce
        nonce = generate_nonce()
        assert isinstance(nonce, str)
        assert len(nonce) == 32  # 16 bytes hex

    def test_generate_nonce_unique(self, client):
        from app.services.auth import generate_nonce
        nonces = {generate_nonce() for _ in range(100)}
        assert len(nonces) == 100


class TestAuthPairingToken:
    def test_generate_pairing_token_prefix(self, client):
        from app.services.auth import generate_pairing_token
        token = generate_pairing_token()
        assert token.startswith("dpx_")
        assert len(token) > 4

    def test_generate_pairing_token_unique(self, client):
        from app.services.auth import generate_pairing_token
        tokens = {generate_pairing_token() for _ in range(100)}
        assert len(tokens) == 100


class TestAuthJWT:
    def test_generate_jwt_returns_string(self, client, secret):
        from app.services.auth import generate_jwt
        token = generate_jwt("test-agent", secret=secret)
        assert isinstance(token, str)
        assert token.count(".") == 2

    def test_decode_jwt_valid(self, client, secret):
        from app.services.auth import generate_jwt, decode_jwt
        token = generate_jwt("test-agent", secret=secret)
        payload = decode_jwt(token, secret=secret)
        assert payload is not None
        assert payload["sub"] == "test-agent"
        assert "iat" in payload
        assert "exp" in payload
        assert "jti" in payload

    def test_decode_jwt_wrong_secret(self, client, secret):
        from app.services.auth import generate_jwt, decode_jwt
        token = generate_jwt("test-agent", secret=secret)
        payload = decode_jwt(token, secret="wrong-secret")
        assert payload is None

    def test_decode_jwt_tampered(self, client, secret):
        from app.services.auth import generate_jwt, decode_jwt
        token = generate_jwt("test-agent", secret=secret)
        parts = token.split(".")
        parts[1] = parts[1] + "X"
        tampered = ".".join(parts)
        payload = decode_jwt(tampered, secret=secret)
        assert payload is None

    def test_decode_jwt_expired(self, client, secret):
        from app.services.auth import decode_jwt
        import base64
        import json
        import hmac
        import hashlib

        now = int(time.time())
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(json.dumps({
            "sub": "test-agent",
            "iat": now - 7200,
            "exp": now - 3600,
            "jti": "test-jti",
        }).encode()).rstrip(b"=").decode()
        signing_input = f"{header}.{payload}"
        signature = base64.urlsafe_b64encode(
            hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
        ).rstrip(b"=").decode()
        expired_token = f"{signing_input}.{signature}"

        result = decode_jwt(expired_token, secret=secret)
        assert result is None

    def test_decode_jwt_malformed(self, client, secret):
        from app.services.auth import decode_jwt
        assert decode_jwt("not.a.jwt.token", secret=secret) is None
        assert decode_jwt("single", secret=secret) is None
        assert decode_jwt("", secret=secret) is None

    def test_jwt_expires_in_one_hour(self, client, secret):
        from app.services.auth import generate_jwt, decode_jwt
        token = generate_jwt("test-agent", secret=secret)
        payload = decode_jwt(token, secret=secret)
        assert payload["exp"] - payload["iat"] == 3600


class TestAuthVerifyToken:
    def test_verify_token_with_bearer(self, client, secret):
        from app.services.auth import generate_jwt, verify_token
        token = generate_jwt("test-agent", secret=secret)
        result = verify_token(f"Bearer {token}")
        assert result is not None
        assert result["sub"] == "test-agent"

    def test_verify_token_without_bearer(self, client, secret):
        from app.services.auth import generate_jwt, verify_token
        token = generate_jwt("test-agent", secret=secret)
        result = verify_token(token)
        assert result is None

    def test_verify_token_null(self, client, secret):
        from app.services.auth import verify_token
        assert verify_token(None) is None

    def test_verify_token_empty(self, client, secret):
        from app.services.auth import verify_token
        assert verify_token("") is None


# ── Pairing Endpoint Tests ─────────────────────────────────────────

class TestGetPairing:
    def test_create_pairing(self, client):
        resp = client.get("/agent/pair?agent_id=test-agent")
        assert resp.status_code == 201
        data = resp.get_json()
        assert "nonce" in data
        assert "pairing_url" in data
        assert data["pairing_url"].startswith("/pair/approve?id=")

    def test_pairing_id_in_url(self, client):
        resp = client.get("/agent/pair?agent_id=my-agent")
        data = resp.get_json()
        pairing_id = data["pairing_url"].split("=")[1]
        assert len(pairing_id) == 16  # 8 bytes hex

    def test_pairing_stored_in_db(self, client):
        from app.models.pairing import PairingRequest
        with client.application.app_context():
            client.get("/agent/pair?agent_id=db-test-agent")
            pairing = PairingRequest.query.filter_by(agent_id="db-test-agent").first()
            assert pairing is not None
            assert pairing.status == "pending"
            assert len(pairing.nonce) == 32

    def test_multiple_pairings_different_nonces(self, client):
        resp1 = client.get("/agent/pair?agent_id=agent1")
        resp2 = client.get("/agent/pair?agent_id=agent2")
        data1 = resp1.get_json()
        data2 = resp2.get_json()
        assert data1["nonce"] != data2["nonce"]


class TestListPairings:
    def test_empty_list(self, client):
        resp = client.get("/admin/pairings")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["pending"] == []
        assert data["recent"] == []

    def test_pending_in_list(self, client):
        client.get("/agent/pair?agent_id=pending-agent")
        resp = client.get("/admin/pairings")
        data = resp.get_json()
        assert len(data["pending"]) == 1
        assert data["pending"][0]["agent_id"] == "pending-agent"
        assert data["pending"][0]["status"] == "pending"

    def test_approved_not_in_pending(self, client):
        # Create and approve a pairing
        resp = client.get("/agent/pair?agent_id=approve-agent")
        data = resp.get_json()
        pairing_id = data["pairing_url"].split("=")[1]
        client.post(f"/admin/pairings/{pairing_id}/approve", data=b"", content_type="application/json")

        resp = client.get("/admin/pairings")
        pdata = resp.get_json()
        assert len(pdata["pending"]) == 0
        assert len(pdata["recent"]) == 1
        assert pdata["recent"][0]["agent_id"] == "approve-agent"


class TestApprovePairing:
    def test_approve_pending(self, client):
        resp = client.get("/agent/pair?agent_id=approve-test")
        data = resp.get_json()
        pairing_id = data["pairing_url"].split("=")[1]

        resp = client.post(f"/admin/pairings/{pairing_id}/approve", data=b"", content_type="application/json")
        assert resp.status_code == 200
        approval = resp.get_json()
        assert "pairing_token" in approval
        assert approval["agent_id"] == "approve-test"
        assert approval["expires_in"] == 3600
        assert approval["pairing_token"].startswith("dpx_")

    def test_approve_nonexistent(self, client):
        resp = client.post("/admin/pairings/nonexistent/approve", data=b"", content_type="application/json")
        assert resp.status_code == 404

    def test_approve_already_approved(self, client):
        resp = client.get("/agent/pair?agent_id=duplicate-approve")
        data = resp.get_json()
        pairing_id = data["pairing_url"].split("=")[1]

        client.post(f"/admin/pairings/{pairing_id}/approve", data=b"", content_type="application/json")
        resp = client.post(f"/admin/pairings/{pairing_id}/approve", data=b"", content_type="application/json")
        assert resp.status_code == 400
        assert "already resolved" in resp.get_json()["error"]

    def test_approve_already_denied(self, client):
        resp = client.get("/agent/pair?agent_id=deny-then-approve")
        data = resp.get_json()
        pairing_id = data["pairing_url"].split("=")[1]

        client.post(f"/admin/pairings/{pairing_id}/deny", data=b"", content_type="application/json")
        resp = client.post(f"/admin/pairings/{pairing_id}/approve", data=b"", content_type="application/json")
        assert resp.status_code == 400

    def test_pairing_token_unique(self, client):
        resp = client.get("/agent/pair?agent_id=token-unique-1")
        data = resp.get_json()
        pid1 = data["pairing_url"].split("=")[1]
        resp = client.get("/agent/pair?agent_id=token-unique-2")
        data = resp.get_json()
        pid2 = data["pairing_url"].split("=")[1]

        r1 = client.post(f"/admin/pairings/{pid1}/approve", data=b"", content_type="application/json")
        r2 = client.post(f"/admin/pairings/{pid2}/approve", data=b"", content_type="application/json")
        t1 = r1.get_json()["pairing_token"]
        t2 = r2.get_json()["pairing_token"]
        assert t1 != t2


class TestDenyPairing:
    def test_deny_pending(self, client):
        resp = client.get("/agent/pair?agent_id=deny-test")
        data = resp.get_json()
        pairing_id = data["pairing_url"].split("=")[1]

        resp = client.post(f"/admin/pairings/{pairing_id}/deny", data=b"", content_type="application/json")
        assert resp.status_code == 200
        assert resp.get_json()["message"] == "Denied"

    def test_deny_nonexistent(self, client):
        resp = client.post("/admin/pairings/nonexistent/deny", data=b"", content_type="application/json")
        assert resp.status_code == 404

    def test_deny_already_approved(self, client):
        resp = client.get("/agent/pair?agent_id=approve-then-deny")
        data = resp.get_json()
        pairing_id = data["pairing_url"].split("=")[1]

        client.post(f"/admin/pairings/{pairing_id}/approve", data=b"", content_type="application/json")
        resp = client.post(f"/admin/pairings/{pairing_id}/deny", data=b"", content_type="application/json")
        assert resp.status_code == 400

    def test_denied_pairing_cannot_verify(self, client):
        resp = client.get("/agent/pair?agent_id=deny-verify")
        data = resp.get_json()
        pairing_id = data["pairing_url"].split("=")[1]

        client.post(f"/admin/pairings/{pairing_id}/deny", data=b"", content_type="application/json")

        payload = json.dumps({
            "pairing_id": pairing_id,
            "nonce": data["nonce"],
            "pairing_token": "dpx_fake",
        }).encode()
        resp = client.post("/agent/pair/verify", data=payload, content_type="application/json")
        assert resp.status_code == 403  # pairing is denied, status != "approved"


class TestVerifyPairing:
    def test_verify_success(self, client):
        # Create and approve pairing
        resp = client.get("/agent/pair?agent_id=verify-test")
        data = resp.get_json()
        pairing_id = data["pairing_url"].split("=")[1]

        approve_resp = client.post(f"/admin/pairings/{pairing_id}/approve", data=b"", content_type="application/json")
        pairing_token = approve_resp.get_json()["pairing_token"]

        # Verify
        payload = json.dumps({
            "pairing_id": pairing_id,
            "nonce": data["nonce"],
            "pairing_token": pairing_token,
        }).encode()
        resp = client.post("/agent/pair/verify", data=payload, content_type="application/json")
        assert resp.status_code == 200
        result = resp.get_json()
        assert "token" in result
        assert result["agent_id"] == "verify-test"
        assert result["expires_in"] == 3600

    def test_verify_missing_fields(self, client):
        payload = json.dumps({}).encode()
        resp = client.post("/agent/pair/verify", data=payload, content_type="application/json")
        assert resp.status_code == 400

    def test_verify_invalid_pairing_id(self, client):
        payload = json.dumps({
            "pairing_id": "nonexistent",
            "nonce": "abc",
            "pairing_token": "dpx_fake",
        }).encode()
        resp = client.post("/agent/pair/verify", data=payload, content_type="application/json")
        assert resp.status_code == 404

    def test_verify_not_approved(self, client):
        resp = client.get("/agent/pair?agent_id=not-approved")
        data = resp.get_json()
        pairing_id = data["pairing_url"].split("=")[1]

        payload = json.dumps({
            "pairing_id": pairing_id,
            "nonce": data["nonce"],
            "pairing_token": "dpx_fake",
        }).encode()
        resp = client.post("/agent/pair/verify", data=payload, content_type="application/json")
        assert resp.status_code == 403
        assert "not approved" in resp.get_json()["error"]

    def test_verify_wrong_nonce(self, client):
        resp = client.get("/agent/pair?agent_id=wrong-nonce")
        data = resp.get_json()
        pairing_id = data["pairing_url"].split("=")[1]

        client.post(f"/admin/pairings/{pairing_id}/approve", data=b"", content_type="application/json")

        payload = json.dumps({
            "pairing_id": pairing_id,
            "nonce": "wrong-nonce-value",
            "pairing_token": "dpx_fake",
        }).encode()
        resp = client.post("/agent/pair/verify", data=payload, content_type="application/json")
        assert resp.status_code == 403
        assert "Invalid nonce" in resp.get_json()["error"]

    def test_verify_wrong_token(self, client):
        resp = client.get("/agent/pair?agent_id=wrong-token")
        data = resp.get_json()
        pairing_id = data["pairing_url"].split("=")[1]

        client.post(f"/admin/pairings/{pairing_id}/approve", data=b"", content_type="application/json")

        payload = json.dumps({
            "pairing_id": pairing_id,
            "nonce": data["nonce"],
            "pairing_token": "dpx_wrong_token_value",
        }).encode()
        resp = client.post("/agent/pair/verify", data=payload, content_type="application/json")
        assert resp.status_code == 403
        assert "Invalid pairing token" in resp.get_json()["error"]

    def test_verify_single_use(self, client):
        # First verify succeeds
        resp = client.get("/agent/pair?agent_id=single-use")
        data = resp.get_json()
        pairing_id = data["pairing_url"].split("=")[1]
        approve_resp = client.post(f"/admin/pairings/{pairing_id}/approve", data=b"", content_type="application/json")
        pairing_token = approve_resp.get_json()["pairing_token"]

        payload = json.dumps({
            "pairing_id": pairing_id,
            "nonce": data["nonce"],
            "pairing_token": pairing_token,
        }).encode()
        resp = client.post("/agent/pair/verify", data=payload, content_type="application/json")
        assert resp.status_code == 200

        # Second verify fails - pairing is now expired (status != "approved")
        resp = client.post("/agent/pair/verify", data=payload, content_type="application/json")
        assert resp.status_code == 403


class TestRequireJWT:
    def test_unauthenticated_access(self, client):
        resp = client.get("/agent/documents")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["error"] == "unauthenticated"
        assert data["pairing_url"] == "/agent/pair"

    def test_unauthenticated_search(self, client):
        resp = client.get("/agent/search?q=test")
        assert resp.status_code == 401

    def test_unauthenticated_categorize(self, client):
        resp = client.post("/agent/categorize")
        assert resp.status_code == 401

    def test_unauthenticated_document(self, client):
        resp = client.get("/agent/documents/1")
        assert resp.status_code == 401

    def test_valid_jwt_access(self, client, secret):
        from app.services.auth import generate_jwt
        token = generate_jwt("test-agent", secret=secret)
        resp = client.get("/agent/documents", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "items" in data
        assert "total" in data

    def test_invalid_jwt_access(self, client):
        resp = client.get("/agent/documents", headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.status_code == 401

    def test_tampered_jwt_access(self, client, secret):
        from app.services.auth import generate_jwt
        token = generate_jwt("test-agent", secret=secret)
        parts = token.split(".")
        parts[1] = parts[1] + "X"
        tampered = ".".join(parts)
        resp = client.get("/agent/documents", headers={"Authorization": f"Bearer {tampered}"})
        assert resp.status_code == 401


class TestFullPairingFlow:
    def test_complete_flow(self, client):
        """Test the complete agent pairing flow from start to finish."""
        # Step 1: Agent makes unauthenticated request
        resp = client.get("/agent/search?q=test")
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "unauthenticated"

        # Step 2: Agent requests pairing
        resp = client.get("/agent/pair?agent_id=flow-agent")
        assert resp.status_code == 201
        pairing_data = resp.get_json()
        nonce = pairing_data["nonce"]
        pairing_id = pairing_data["pairing_url"].split("=")[1]

        # Step 3: Admin approves
        resp = client.post(f"/admin/pairings/{pairing_id}/approve", data=b"", content_type="application/json")
        assert resp.status_code == 200
        approval = resp.get_json()
        pairing_token = approval["pairing_token"]

        # Step 4: Agent verifies pairing
        payload = json.dumps({
            "pairing_id": pairing_id,
            "nonce": nonce,
            "pairing_token": pairing_token,
        }).encode()
        resp = client.post("/agent/pair/verify", data=payload, content_type="application/json")
        assert resp.status_code == 200
        auth_data = resp.get_json()
        jwt_token = auth_data["token"]
        assert auth_data["agent_id"] == "flow-agent"

        # Step 5: Agent uses JWT for authenticated requests
        resp = client.get("/agent/documents", headers={"Authorization": f"Bearer {jwt_token}"})
        assert resp.status_code == 200

        resp = client.get("/agent/search?q=test", headers={"Authorization": f"Bearer {jwt_token}"})
        assert resp.status_code == 200

        # Step 6: Pairing token is single-use (status now "expired", returns 403)
        payload = json.dumps({
            "pairing_id": pairing_id,
            "nonce": nonce,
            "pairing_token": pairing_token,
        }).encode()
        resp = client.post("/agent/pair/verify", data=payload, content_type="application/json")
        assert resp.status_code == 403

    def test_flow_with_deny(self, client):
        """Test that denied pairings cannot authenticate."""
        # Create pairing
        resp = client.get("/agent/pair?agent_id=deny-flow-agent")
        data = resp.get_json()
        pairing_id = data["pairing_url"].split("=")[1]

        # Admin denies
        resp = client.post(f"/admin/pairings/{pairing_id}/deny", data=b"", content_type="application/json")
        assert resp.status_code == 200

        # Agent tries to verify (pairing_token is None for denied, returns 403)
        payload = json.dumps({
            "pairing_id": pairing_id,
            "nonce": data["nonce"],
            "pairing_token": "dpx_fake",
        }).encode()
        resp = client.post("/agent/pair/verify", data=payload, content_type="application/json")
        assert resp.status_code == 403

        # Unauthenticated access still fails
        resp = client.get("/agent/documents")
        assert resp.status_code == 401


class TestPairingExpiry:
    def test_pairing_expired_status(self, client):
        """Verify that after successful verification, pairing status becomes expired."""
        from app.models.pairing import PairingRequest
        with client.application.app_context():
            resp = client.get("/agent/pair?agent_id=expiry-agent")
            data = resp.get_json()
            pairing_id = data["pairing_url"].split("=")[1]

            approve_resp = client.post(f"/admin/pairings/{pairing_id}/approve", data=b"", content_type="application/json")
            pairing_token = approve_resp.get_json()["pairing_token"]

            payload = json.dumps({
                "pairing_id": pairing_id,
                "nonce": data["nonce"],
                "pairing_token": pairing_token,
            }).encode()
            client.post("/agent/pair/verify", data=payload, content_type="application/json")

            pairing = db.session.get(PairingRequest, pairing_id)
            assert pairing.status == "expired"
