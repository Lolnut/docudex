# Agent Authentication: Challenge-Response Pairing

## Overview

Replace the static `DOCUDAX_API_KEY` env var with an agent-initiated challenge-response pairing flow. No secrets are stored long-term on the server. JWTs are stateless and expire after 1 hour. Server restarts invalidate all tokens.

## Pairing Flow

```
Agent                          Server                      Admin
 │                               │                            │
 │  GET /agent/search            │                            │
 │  (no JWT)                     │                            │
 │──────────────────────────────>│                            │
 │                               │  401 + nonce               │
 │  <───────────────────────────│                            │
 │                               │                            │
 │  GET /pair/nonce              │                            │
 │  (to get pairing URL)         │                            │
 │──────────────────────────────>│                            │
 │                               │                            │
 │  <───────────────────────────│  pairing_url:              │
 │                               │  "/pair/approve?id=abc123" │
 │                               │                            │
 │  (admin visits URL)           │                            │
 │                               │◄───────────────────────────│
 │                               │                            │
 │                               │  Approve request           │
 │                               │───────────────────────────>│
 │                               │                            │
 │                               │  Generate pairing_token    │
 │                               │  Store in DB               │
 │                               │                            │
 │                               │  <─────────────────────────│
 │                               │  pairing_token: dpx_abc... │
 │                               │                            │
 │  POST /pair/verify            │                            │
 │  {nonce, pairing_token}       │                            │
 │──────────────────────────────>│                            │
 │                               │  Verify pairing_token      │
 │                               │  Issue JWT (1hr expiry)    │
 │                               │                            │
 │  <───────────────────────────│  {jwt: "eyJ..."}            │
 │                               │                            │
 │  GET /agent/search            │                            │
 │  Authorization: Bearer <jwt>  │                            │
 │──────────────────────────────>│                            │
 │                               │  Verify JWT                │
 │                               │  Process request           │
 │                               │                            │
 │  <───────────────────────────│  {results: [...]}           │
 │                               │                            │
```

## API Endpoints

### Agent Endpoints (in `api.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/agent/pair` | Get a nonce and pairing URL (replaces 401 response) |
| POST | `/agent/pair/verify` | Exchange nonce + pairing_token for JWT |

### Admin Endpoints (in `ui.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/pairings` | List pending pairing requests |
| POST | `/admin/pairings/<id>/approve` | Approve a pairing request (returns pairing_token) |
| POST | `/admin/pairings/<id>/deny` | Deny a pairing request |

### Existing Agent Endpoints (modified)

All `/agent/*` routes get a new auth check via `@require_jwt` decorator:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/agent/search` | Full-text search |
| GET | `/agent/documents` | Paginated document listing |
| GET | `/agent/documents/<id>` | Single document detail |
| POST | `/agent/categorize` | Process queue |

If no valid JWT is present, returns `401` with:
```json
{
  "error": "unauthenticated",
  "message": "Pair with the server first",
  "pairing_url": "/agent/pair"
}
```

## Data Model: `PairingRequest`

```python
class PairingRequest(db.Model):
    __tablename__ = "pairing_requests"

    id = db.Column(db.Text, primary_key=True)  # UUID
    agent_id = db.Column(db.Text, nullable=False)  # e.g., "search-agent", "bot-1"
    nonce = db.Column(db.Text, nullable=False)  # Challenge nonce
    pairing_token = db.Column(db.Text, nullable=True)  # Set on approval
    status = db.Column(db.Text, nullable=False, default="pending")  # pending, approved, denied
    ip_address = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)  # 15 min expiry
    approved_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "nonce": self.nonce,
            "status": self.status,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
        }
```

**Cleanup:** Expired/denied pairings older than 24 hours are auto-deleted (run on each pairing request or via scheduled task).

## JWT Structure

```json
{
  "alg": "HS256",
  "typ": "JWT"
}
{
  "sub": "search-agent",
  "iat": 1719800000,
  "exp": 1719803600,
  "jti": "random-uuid"
}
```

- **Secret:** Derived from `DOCUDAX_API_KEY` env var (used as HMAC key). If empty, generate a random key at startup and log it.
- **Expiry:** 1 hour (configurable via `DOCUDAX_JWT_EXPIRY_HOURS`)
- **Stateless:** No server-side storage of issued JWTs. Server restart = all tokens invalidated.

## File Changes

### New Files

1. **`app/services/auth.py`** — Auth utilities
   - `generate_nonce()` — 32-byte random hex string
   - `generate_pairing_token()` — 64-byte random hex string
   - `generate_jwt(agent_id, secret)` — Create signed JWT
   - `decode_jwt(token, secret)` — Verify and decode JWT, raises on invalid/expired
   - `get_or_create_secret()` — Get existing secret from env or generate new one

### Modified Files

2. **`app/models/__init__.py`** — Import and register `PairingRequest`
3. **`app/models/pairing.py`** — NEW: `PairingRequest` model
4. **`app/__init__.py`** — Create `PairingRequest` table on startup, clean up old pairings
5. **`app/routes/api.py`** — Add `/agent/pair` endpoints, add `@require_jwt` decorator, replace manual `check_api_key()` calls
6. **`app/routes/ui.py`** — Add `/admin/pairings` endpoints
7. **`app/templates/index.html`** — Add "Agent Auth" section with pending requests list
8. **`app/static/style.css`** — Styles for agent auth section

## Implementation Steps

### Step 1: Create `PairingRequest` model
- Add `app/models/pairing.py` with the model definition
- Register in `app/models/__init__.py`
- Add table creation in `app/__init__.py`

### Step 2: Create auth utilities
- Create `app/services/auth.py` with:
  - JWT encode/decode (using `hmac`, `hashlib`, `base64` — no external deps)
  - Nonce and pairing token generation
  - Secret management (env var or auto-generated)

### Step 3: Add `@require_jwt` decorator
- Check `Authorization: Bearer <token>` header
- Decode and verify JWT
- Return 401 with pairing URL if invalid/missing
- Attach `g.current_agent` for use in route handlers

### Step 4: Add agent pairing endpoints
- `GET /agent/pair` — Create `PairingRequest`, return nonce + pairing URL
- `POST /agent/pair/verify` — Validate nonce + pairing_token, issue JWT

### Step 5: Add admin pairing endpoints
- `GET /admin/pairings` — List pending requests
- `POST /admin/pairings/<id>/approve` — Generate pairing_token, mark approved
- `POST /admin/pairings/<id>/deny` — Mark denied

### Step 6: Update UI
- Add "Agent Auth" section in the documents panel header
- Show pending pairing requests with approve/deny buttons
- Show "Copy" button for pairing token after approval

### Step 7: Cleanup & migration
- Add auto-cleanup of expired/denied pairings
- Deprecate `DOCUDAX_API_KEY` env var (show warning if set)
- Update README with new auth flow docs

## Edge Cases

- **Pairing token leaked:** Token is single-use. If an attacker uses it, the legitimate agent must re-pair.
- **Multiple agents pairing simultaneously:** Each gets a unique nonce and pairing request ID.
- **Admin never approves:** Pairing requests expire after 15 minutes.
- **JWT expires during long operation:** Agent gets 401 on next request and must re-pair.
- **Server restart:** All JWTs invalidated. Agents must re-pair.

## Backward Compatibility

- If `DOCUDAX_API_KEY` is set, show a warning in logs: "DOCUDAX_API_KEY is deprecated. Use agent pairing instead."
- The static API key can be supported as a fallback during a transition period (optional).
