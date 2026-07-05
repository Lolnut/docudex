# Agent Pairing

## Quick Reference

The pairing flow authenticates AI agents to the Docudex server via a challenge-response process.

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/agent/pair?agent_id=<name>` | None | Create pairing request, returns nonce + pairing ID |
| POST | `/agent/pair/verify` | None | Exchange nonce + token for JWT |
| GET | `/agent/search?q=<query>` | JWT | Full-text search |
| GET | `/agent/documents` | JWT | Paginated document listing |
| GET | `/agent/documents/<id>` | JWT | Single document detail |
| POST | `/agent/categorize` | JWT | Process queue |

### Full Flow (3 steps)

```
1. GET /agent/pair?agent_id=my-agent
   → 201: { "nonce": "abc...", "pairing_url": "/pair/approve?id=xyz" }
   (or 200 if already paired: { "message": "Already paired" })

2. POST /agent/pair/verify
   Body: { "pairing_id": "xyz", "nonce": "abc...", "pairing_token": "dpx_..." }
   → 200: { "token": "eyJ...", "agent_id": "my-agent", "expires_in": 3600 }

3. Use JWT: Authorization: Bearer eyJ...
```

The `pairing_token` is provided by an admin who approves the request at the pairing URL.
After the first successful pairing, the agent is permanently paired and never needs admin approval again.

### Key IDs to Know

- **`pairing_id`** — the `id` field on `PairingRequest` (hex text, e.g. `"a3f2b1c4d5e6f7a8"`). This is what goes in URL paths and verify requests.
- **`agent_id`** — the agent's identifier (freeform text, e.g. `"search-agent"`). Used as the JWT `sub` claim.
- **`pairing_token`** — generated on approval, starts with `dpx_`. Single-use.
- **`nonce`** — random challenge from step 1. Must match in the verify call.

### Common Debugging

| Problem | Cause | Fix |
|---------|-------|-----|
| `404: Pairing request not found` | Wrong `pairing_id` — not the `agent_id` | Use the hex ID from the pairing URL |
| `403: Pairing request not approved` | Status is not `"approved"` | Ask admin to approve the request |
| `403: Invalid nonce` | Nonce doesn't match | Use the exact nonce from step 1 |
| `403: Invalid pairing token` | Wrong or already-used token | Ask admin to re-approve for a new token |
| `401: unauthenticated` | No JWT or expired | Auto-renews: call `GET /agent/pair?agent_id=<name>` to get a new JWT |

### Auto-Renewal

Once an agent is paired and verified, JWTs auto-renew without admin involvement:

```bash
# When your JWT expires, just call:
GET /agent/pair?agent_id=my-agent
→ 200: { "token": "eyJ_new..." }

# Then use the new token:
Authorization: Bearer eyJ_new...
```

The server checks for a verified pairing by `agent_id` and issues a fresh JWT automatically.

### Key Files

- `app/routes/api.py` — agent pairing endpoints + `@require_jwt` decorator
- `app/services/auth.py` — JWT, nonce, pairing token generation
- `app/models/pairing.py` — PairingRequest model
