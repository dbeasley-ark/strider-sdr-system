#!/usr/bin/env bash
# Re-run the plan's 8-company validation sample. Prints one TSV line per
# company so the deltas are easy to eyeball.
#
# Usage: scripts/rerun_sample.sh

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

PY="$ROOT/.venv/bin/python"

# company<TAB>domain pairs
read -r -d '' SAMPLE <<'EOF' || true
Tanium	tanium.com
Swarm Aero	swarm.aero
Second Front Systems	secondfront.com
Forterra	forterra.com
Aetherflux	aetherflux.com
Astro Mechanica	astromecha.co
Bedrock Ocean Exploration	bedrockocean.com
Castelion	castelion.com
EOF

printf '%s\t%s\t%s\t%s\t%s\t%s\n' company verdict track cost_usd wall_s tool_calls

while IFS=$'\t' read -r COMPANY DOMAIN; do
  [ -z "$COMPANY" ] && continue

  echo "→ $COMPANY ($DOMAIN)" >&2
  OUT="$("$PY" -m agent --company "$COMPANY" --domain "$DOMAIN" --quiet 2>/dev/null || true)"
  if [ -z "$OUT" ]; then
    printf '%s\t%s\t-\t-\t-\t-\n' "$COMPANY" "no-stdout"
    continue
  fi
  # Parse fields from the brief JSON on stdout.
  VERDICT=$(printf '%s' "$OUT" | "$PY" -c 'import json,sys; b=json.loads(sys.stdin.read()); print(b.get("verdict","?"))')
  TRACK=$(printf '%s' "$OUT" | "$PY" -c 'import json,sys; b=json.loads(sys.stdin.read()); print(b.get("track","?"))')
  COST=$(printf '%s' "$OUT" | "$PY" -c 'import json,sys; b=json.loads(sys.stdin.read()); print(b.get("cost_usd","?"))')
  WALL=$(printf '%s' "$OUT" | "$PY" -c 'import json,sys; b=json.loads(sys.stdin.read()); print(b.get("wall_seconds","?"))')
  TC=$(printf '%s' "$OUT" | "$PY" -c 'import json,sys; b=json.loads(sys.stdin.read()); print(b.get("tool_calls_used","?"))')
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$COMPANY" "$VERDICT" "$TRACK" "$COST" "$WALL" "$TC"
done <<< "$SAMPLE"
