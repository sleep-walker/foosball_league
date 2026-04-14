#!/usr/bin/env bash
# Simulate: Sleepy shares QR for a tournament, Zlatan scans it and registers.
#
# Usage:
#   bash scripts/simulate_zlatan_qr.sh <tournament-uuid>
#
# Prerequisites:
#   - Server running (make run)
#   - DB seeded (make seed-reset)
#   - For QR decode: pip install pyzbar  +  apt install libzbar0
#     (falls back to JSON endpoint if pyzbar is not available)

set -euo pipefail
BASE="${FOOSBALL_URL:-http://127.0.0.1:8000}"

blue()  { echo -e "\033[1;34m$*\033[0m"; }
green() { echo -e "\033[1;32m$*\033[0m"; }
red()   { echo -e "\033[1;31m$*\033[0m"; }

T_ID="${1:?Usage: $0 <tournament-uuid>}"
blue "Tournament: $T_ID"

# ── Helper: login and return token ─────────────────────────────
login() {
  local email="$1" pass="$2"
  local resp
  resp=$(curl -sf -X POST "$BASE/api/v1/users/login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=$email&password=$pass") || { red "   ✗ Login failed for $email"; exit 1; }
  echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

# ── 1. Sleepy logs in (organizer) ──────────────────────────────
blue "\n1. Sleepy logs in..."
SLEEPY_TOKEN=$(login froser@gmail.com veverka007)
green "   ✓ Logged in as Sleepy"

# ── 2. Sleepy downloads QR code as PNG ─────────────────────────
blue "\n2. Sleepy downloads QR code..."
QR_FILE=$(mktemp /tmp/qr_XXXX.png)
HTTP_CODE=$(curl -s -o "$QR_FILE" -w "%{http_code}" \
  "$BASE/v1/public/tournaments/$T_ID/qr?format=png")
if [ "$HTTP_CODE" != "200" ]; then
  red "   ✗ QR download failed (HTTP $HTTP_CODE)"
  exit 1
fi
QR_SIZE=$(wc -c < "$QR_FILE")
green "   ✓ QR saved to $QR_FILE ($QR_SIZE bytes)"

# ── 3. Decode QR → extract registration URL with token ────────
blue "\n3. Decoding QR code..."
REG_URL=$(python3 -c "
try:
    from pyzbar.pyzbar import decode
    from PIL import Image
    results = decode(Image.open('$QR_FILE'))
    if results:
        print(results[0].data.decode())
    else:
        raise RuntimeError('no QR found in image')
except ImportError:
    import sys
    print('FALLBACK', file=sys.stderr)
" 2>/tmp/qr_decode_err.txt || true)

if [ -z "$REG_URL" ] || grep -q FALLBACK /tmp/qr_decode_err.txt 2>/dev/null; then
  blue "   (pyzbar not available — falling back to JSON endpoint)"
  REG_URL=$(curl -sf "$BASE/v1/public/tournaments/$T_ID/qr?format=json" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['registration_url'])")
fi

TOKEN=$(echo "$REG_URL" | grep -oP 'token=\K[^&]+')
green "   ✓ Decoded URL: $REG_URL"
green "   ✓ Token: ${TOKEN:0:16}..."

# ── 4. Zlatan logs in ─────────────────────────────────────────
blue "\n4. Zlatan logs in..."
ZLATAN_TOKEN=$(login zlatan@devnull.com zlatanjede)
green "   ✓ Logged in as Zlatan"

# ── 5. Zlatan self-registers using decoded token ───────────────
blue "\n5. Zlatan registers via QR token..."
REG_RESULT=$(curl -sf -X POST "$BASE/v1/public/tournaments/$T_ID/register" \
  -H "Content-Type: application/json" \
  -d "{\"nickname\": \"Zlatan\", \"token\": \"$TOKEN\"}")
echo "$REG_RESULT" | python3 -m json.tool
green "   ✓ Zlatan is on the list!"

# ── 6. Verify: Sleepy sees Zlatan as applicant ─────────────────
blue "\n6. Sleepy checks tournament..."
curl -sf "$BASE/api/v1/tournaments/$T_ID" \
  -H "Authorization: Bearer $SLEEPY_TOKEN" \
  | python3 -c "
import sys, json
t = json.load(sys.stdin)
print(f\"   Tournament: {t['name']} ({t['status']})\")
for a in t.get('applicants', []):
    print(f\"   ✋ {a['nickname']} wants to play\")
for r in t.get('registrations', []):
    p = r.get('player', {})
    print(f\"   ✓ {p.get('nickname', '?')} registered\")
if not t.get('applicants') and not t.get('registrations'):
    print('   (empty)')
"

# ── Cleanup ────────────────────────────────────────────────────
rm -f "$QR_FILE" /tmp/qr_decode_err.txt
green "\n🎉 Done! Zlatan registered via QR scan."
blue  "   Sleepy can accept him in the UI → ✋ Accept tab."
