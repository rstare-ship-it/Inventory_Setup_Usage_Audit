#!/usr/bin/env bash
# run_audit.sh — Run inventory audit for one or more tenant groups and push results.
#
# Usage:
#   ./run_audit.sh "SILA"                  # run one group
#   ./run_audit.sh "SILA" "T3 Services Group"   # run multiple groups
#   ./run_audit.sh all                     # run every group listed in GROUPS below
#   ./run_audit.sh --tenant-id 12345       # run a single tenant by ID
#
# Options (must come before group names):
#   --lookback N     lookback days (default: 90)
#   --no-push        skip git commit + push (useful for testing)
#   --tenant-id ID   run a single tenant instead of a group
#
# Requires: SNOWFLAKE_ACCOUNT and SNOWFLAKE_USER set in .env
# Okta authentication pop-up will appear once per group run.

set -euo pipefail
cd "$(dirname "$0")"

# ─── Configure groups here ────────────────────────────────────────────────────
AUDIT_GROUPS=(
  "SILA"
  "T3 Services Group"
)
# ──────────────────────────────────────────────────────────────────────────────

AGGREGATE="data/audit_aggregate.json"
LOOKBACK=90
PUSH=true
TENANT_ID=""
REPROCESS=false

# Parse flags
while [[ $# -gt 0 && "$1" == --* ]]; do
  case "$1" in
    --lookback)   LOOKBACK="$2"; shift 2 ;;
    --no-push)    PUSH=false; shift ;;
    --tenant-id)  TENANT_ID="$2"; shift 2 ;;
    --reprocess)  REPROCESS=true; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# Determine what to run
if $REPROCESS; then
  RUN_TARGETS=("__reprocess__")
elif [[ -n "$TENANT_ID" ]]; then
  RUN_TARGETS=("__tenant__")
elif [[ $# -eq 0 ]]; then
  echo "Usage: $0 [--lookback N] [--no-push] [--tenant-id ID] [--reprocess] <group> [group2 ...] | all" >&2
  echo "Groups: ${AUDIT_GROUPS[*]}" >&2
  exit 1
elif [[ "$1" == "all" ]]; then
  RUN_TARGETS=("${AUDIT_GROUPS[@]}")
else
  RUN_TARGETS=("$@")
fi

# ─── Helpers ──────────────────────────────────────────────────────────────────

_sanitize() {
  # Match Python's _sanitize_folder_name: keep alnum/underscore/hyphen, collapse runs
  echo "$1" | sed 's/[^A-Za-z0-9_-]/_/g' | sed 's/__*/_/g' | sed 's/^_//;s/_$//'
}

run_group() {
  local group="$1"
  local folder
  folder=$(_sanitize "$group")

  echo ""
  echo "━━━ Running audit: ${group} ━━━"
  echo "  Aggregate : ${AGGREGATE}"
  echo "  Lookback  : ${LOOKBACK} days"
  echo ""

  python3 audit_report.py \
    --from-snowflake \
    --tenant-group "$group" \
    --lookback-days "$LOOKBACK" \
    --output-aggregate "$AGGREGATE"

  echo "  ✓ Audit complete for ${group}"
}

run_tenant() {
  local tid="$1"

  echo ""
  echo "━━━ Running audit: tenant ${tid} ━━━"
  echo "  Aggregate : ${AGGREGATE}"
  echo "  Lookback  : ${LOOKBACK} days"
  echo ""

  python3 audit_report.py \
    --from-snowflake \
    --tenant-id "$tid" \
    --lookback-days "$LOOKBACK" \
    --output-aggregate "$AGGREGATE"

  echo "  ✓ Audit complete for tenant ${tid}"
}

run_reprocess() {
  local tid_arg=""
  [[ -n "$TENANT_ID" ]] && tid_arg="--tenant-id $TENANT_ID"

  echo ""
  echo "━━━ Reprocessing cached audit data ━━━"
  echo "  Aggregate : ${AGGREGATE}"
  [[ -n "$TENANT_ID" ]] && echo "  Tenant ID : ${TENANT_ID}" || echo "  Tenants   : all cached"
  echo ""

  # shellcheck disable=SC2086
  python3 audit_report.py \
    --reprocess \
    $tid_arg \
    --output-aggregate "$AGGREGATE"

  echo "  ✓ Reprocess complete"
}

commit_and_push() {
  local targets=("$@")
  local date_str
  date_str=$(date +"%Y-%m-%d")

  # Build a commit message from what was run
  local subject
  if [[ ${#targets[@]} -eq 1 && "${targets[0]}" == "__tenant__" ]]; then
    subject="Refresh audit: tenant ${TENANT_ID} (${date_str})"
  elif [[ ${#targets[@]} -eq 1 ]]; then
    subject="Refresh audit: ${targets[0]} (${date_str})"
  else
    subject="Refresh audit: ${#targets[@]} groups (${date_str})"
  fi

  echo ""
  echo "━━━ Committing results ━━━"

  # Stage data files — aggregate and groups (groups.json updated on group runs)
  git add "$AGGREGATE" "data/groups.json" 2>/dev/null || true

  # Only commit if there are staged changes
  if git diff --cached --quiet; then
    echo "  No changes to commit."
    return 0
  fi

  git commit -m "$subject"
  echo "  ✓ Committed: ${subject}"

  if $PUSH; then
    git push origin main
    echo "  ✓ Pushed. GitHub Pages will rebuild in ~1 minute."
  else
    echo "  (--no-push: skipping git push)"
  fi
}

# ─── Main ─────────────────────────────────────────────────────────────────────

FAILED=()

if $REPROCESS; then
  run_reprocess || FAILED+=("reprocess")
elif [[ -n "$TENANT_ID" ]]; then
  run_tenant "$TENANT_ID" || FAILED+=("tenant:${TENANT_ID}")
else
  for target in "${RUN_TARGETS[@]}"; do
    run_group "$target" || FAILED+=("$target")
  done
fi

if [[ ${#FAILED[@]} -gt 0 ]]; then
  echo ""
  echo "⚠️  Some runs failed: ${FAILED[*]}" >&2
  echo "   Results from successful runs will still be committed." >&2
fi

commit_and_push "${RUN_TARGETS[@]}"

echo ""
echo "Done."
