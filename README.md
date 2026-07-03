# docudex

Document indexing API with full-text search and AI agent tooling.

## Setup

```bash
# Install dependencies
uv sync

# Configure environment variables
cp .env.example .env  # edit as needed
```

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DOCUDEX_JWT_SECRET` | Secret for signing agent JWT tokens | Auto-generated on first run |
| `DOCUDEX_STORAGE_PATH` | Directory for uploaded PDFs | `./uploads` |

## Run

```bash
uv run python run.py
```

The app starts on `http://127.0.0.1:5000`.

## Usage

### UI

Open `http://127.0.0.1:5000` in a browser. Drag and drop PDF files or use the queue panel to manage uploads.

### Agent Authentication (Pairing)

Agents authenticate via a challenge-response pairing flow. This replaces the deprecated `DOCUDEX_API_KEY` method.

**How it works:**

1. **Agent requests pairing** — makes an unauthenticated request to any `/agent/*` endpoint, receives a 401 with a pairing URL
2. **Admin approves** — opens the pairing URL in the browser (or calls `/admin/pairings/<id>/approve`)
3. **Agent verifies** — sends the pairing ID, nonce, and pairing token to `/agent/pair/verify`
4. **JWT issued** — agent receives a JWT valid for 1 hour, uses it for all subsequent requests

**Example flow:**

```bash
# Step 1: Agent makes unauthenticated request
curl http://127.0.0.1:5000/agent/search?q=test
# → 401: {"error": "unauthenticated", "pairing_url": "/agent/pair"}

# Step 2: Agent requests pairing
curl "http://127.0.0.1:5000/agent/pair?agent_id=my-agent"
# → 201: {"nonce": "abc123", "pairing_url": "/pair/approve?id=xyz"}

# Step 3: Admin approves (via UI or API)
curl -X POST http://127.0.0.1:5000/admin/pairings/xyz/approve
# → 200: {"pairing_token": "dpx_...", "agent_id": "my-agent", "expires_in": 3600}

# Step 4: Agent verifies and gets JWT
curl -X POST http://127.0.0.1:5000/agent/pair/verify \
  -H "Content-Type: application/json" \
  -d '{"pairing_id": "xyz", "nonce": "abc123", "pairing_token": "dpx_..."}'
# → 200: {"token": "eyJ...", "agent_id": "my-agent", "expires_in": 3600}

# Step 5: Agent uses JWT
curl http://127.0.0.1:5000/agent/documents \
  -H "Authorization: Bearer eyJ..."
```

**Key properties:**

- Pairing tokens are single-use and expire after 15 minutes
- JWTs are valid for 1 hour
- Server restart invalidates all JWTs (agents must re-pair)
- Denied pairings cannot be used to authenticate

### Agent API

All `/agent/*` endpoints require the `Authorization: Bearer <jwt>` header:

```bash
# Process queue
curl -X POST http://127.0.0.1:5000/agent/categorize \
  -H "Authorization: Bearer <jwt>"

# Search
curl "http://127.0.0.1:5000/agent/search?q=query" \
  -H "Authorization: Bearer <jwt>"

# List documents
curl http://127.0.0.1:5000/agent/documents \
  -H "Authorization: Bearer <jwt>"
```

### Admin Pairings

```bash
# List pending and recent pairings
curl http://127.0.0.1:5000/admin/pairings

# Approve a pairing
curl -X POST http://127.0.0.1:5000/admin/pairings/<id>/approve

# Deny a pairing
curl -X POST http://127.0.0.1:5000/admin/pairings/<id>/deny
```

### Commit & Push

```bash
git add -A
git commit -m "feat: your description"
git push origin main
```
