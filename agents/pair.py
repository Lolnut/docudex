#!/usr/bin/env python3
"""Pair an agent with the Docudex server via the CLI.

Automates the challenge-response pairing flow:
  1. Create a pairing request (GET /agent/pair)
  2. Approve it (POST /admin/pairings/<id>/approve)
  3. Verify and get a JWT (POST /agent/pair/verify)

If the agent is already paired, the script auto-renews the JWT without admin involvement.

Usage:
  # Full pairing flow (create + approve + verify)
  python agents/pair.py my-agent

  # Just create a pairing request (or get info if already paired)
  python agents/pair.py my-agent --create

  # Approve an existing pairing request
  python agents/pair.py my-agent --approve --pairing-id xyz

  # Verify with a pairing_id, nonce, and token
  python agents/pair.py my-agent --verify --pairing-id xyz --nonce abc --token dpx_...

  # List pending pairings
  python agents/pair.py --list

  # Deny a pairing request
  python agents/pair.py my-agent --deny --pairing-id xyz

  # Auto-renew JWT for an already-paired agent
  python agents/pair.py my-agent --renew

Environment:
  DOCUDEX_BASE_URL  Base URL of the server (default: http://127.0.0.1:5000)
"""

import argparse
import json
import sys
import urllib.request
import urllib.error

BASE_URL = (
    "http://127.0.0.1:5000"
    if not (base_url := __import__("os").environ.get("DOCUDEX_BASE_URL"))
    else base_url
)


def api(method, path, data=None):
    url = f"{BASE_URL}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status == 204 or resp.status == 201:
                return None
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = json.loads(e.read()) if e.read else {}
        print(f"  ✗ {e.code} {error_body.get('error', e.reason)}", file=sys.stderr)
        sys.exit(1)


def create_pairing(agent_id):
    print("[1/3] Creating pairing request...")
    result = api("GET", f"/agent/pair?agent_id={agent_id}")

    if result.get("message") == "Already paired":
        print(f"  Already paired (verified at: {result.get('verified_at')})")
        return None, None

    nonce = result["nonce"]
    pairing_id = result["pairing_url"].split("=")[1]
    print(f"  nonce:       {nonce}")
    print(f"  pairing_id:  {pairing_id}")
    return nonce, pairing_id


def approve_pairing(pairing_id):
    print("[2/3] Approving pairing...")
    result = api("POST", f"/admin/pairings/{pairing_id}/approve")
    token = result["pairing_token"]
    print(f"  pairing_token: {token}")
    return token


def verify_pairing(agent_id, pairing_id, nonce, token):
    print("[3/3] Verifying and getting JWT...")
    result = api("POST", "/agent/pair/verify", {
        "pairing_id": pairing_id,
        "nonce": nonce,
        "pairing_token": token,
    })
    jwt = result["token"]
    print(f"\n  ✓ Paired successfully!")
    print(f"  agent_id:      {agent_id}")
    print(f"  token:         {jwt}")
    print(f"  expires_in:    {result['expires_in']}s")
    print(f"\n  # Use with curl:")
    print(f"  # curl {BASE_URL}/agent/search?q=test \\")
    print(f"  #   -H \"Authorization: Bearer {jwt}\"")
    return jwt


def renew_jwt(agent_id):
    print("Renewing JWT...")
    result = api("GET", f"/agent/pair?agent_id={agent_id}")
    jwt = result["token"]
    print(f"\n  ✓ JWT renewed!")
    print(f"  agent_id:      {agent_id}")
    print(f"  token:         {jwt}")
    print(f"  expires_in:    {result['expires_in']}s")
    print(f"\n  # Use with curl:")
    print(f"  # curl {BASE_URL}/agent/search?q=test \\")
    print(f"  #   -H \"Authorization: Bearer {jwt}\"")
    return jwt


def list_pairings():
    print("Listing pairing requests...\n")
    result = api("GET", "/admin/pairings")

    pending = result.get("pending", [])
    recent = result.get("recent", [])

    if pending:
        print("Pending:")
        for p in pending:
            print(f"  {p['id'][:12]}...  agent={p['agent_id']}  ip={p['ip_address']}  created={p['created_at']}")
        print()

    if recent:
        print("Recent:")
        for r in recent:
            print(f"  {r['id'][:12]}...  agent={r['agent_id']}  status={r['status']}  created={r['created_at']}")
        print()

    if not pending and not recent:
        print("  No pairing requests found.")


def deny_pairing(pairing_id):
    print(f"Denying pairing request {pairing_id[:12]}...")
    api("POST", f"/admin/pairings/{pairing_id}/deny")
    print("  Done.")


def main():
    parser = argparse.ArgumentParser(description="Pair an agent with the Docudex server")
    parser.add_argument("agent_id", nargs="?", help="Agent identifier")
    parser.add_argument("--create", action="store_true", help="Only create a pairing request")
    parser.add_argument("--approve", action="store_true", help="Only approve a pairing request")
    parser.add_argument("--verify", action="store_true", help="Only verify and get JWT")
    parser.add_argument("--renew", action="store_true", help="Auto-renew JWT for an already-paired agent")
    parser.add_argument("--list", action="store_true", help="List pairing requests")
    parser.add_argument("--deny", action="store_true", help="Deny a pairing request")
    parser.add_argument("--pairing-id", help="Pairing request ID (hex string)")
    parser.add_argument("--nonce", help="Nonce from create step")
    parser.add_argument("--token", help="Pairing token from approve step")
    args = parser.parse_args()

    if args.list:
        list_pairings()
        return

    if not args.agent_id:
        parser.print_help()
        sys.exit(1)

    if args.renew:
        renew_jwt(args.agent_id)
        return

    if args.create:
        nonce, pairing_id = create_pairing(args.agent_id)
        if nonce is None:
            print("\n  Agent is already paired. No action needed.")
        return

    if args.approve:
        if not args.pairing_id:
            print("  --pairing-id is required for approve", file=sys.stderr)
            sys.exit(1)
        approve_pairing(args.pairing_id)
        return

    if args.verify:
        if not all([args.pairing_id, args.nonce, args.token]):
            print("  --pairing-id, --nonce, and --token are required for verify", file=sys.stderr)
            sys.exit(1)
        verify_pairing(args.agent_id, args.pairing_id, args.nonce, args.token)
        return

    if args.deny:
        if not args.pairing_id:
            print("  --pairing-id is required for deny", file=sys.stderr)
            sys.exit(1)
        deny_pairing(args.pairing_id)
        return

    # Default: full flow
    nonce, pairing_id = create_pairing(args.agent_id)
    if nonce is None:
        print("\n  Agent is already paired. Use --renew to get a new JWT.")
        return
    token = approve_pairing(pairing_id)
    verify_pairing(args.agent_id, pairing_id, nonce, token)


if __name__ == "__main__":
    main()
