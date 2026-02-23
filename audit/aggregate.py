"""
Merge one or more tenant audit runs into a single aggregated JSON file for the site.
Designed for: Snowflake produces JSON → script merges into aggregate → hosted page loads by tenant.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path


def _json_safe(obj):
    """Recursively convert date/datetime to ISO strings so aggregate is JSON-serializable."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def _slug(name: str) -> str:
    """Lowercase alphanumeric + hyphen for name-based lookup."""
    if not name or not isinstance(name, str):
        return ""
    s = "".join(c if c.isalnum() or c in " -" else " " for c in name.strip())
    return "-".join(s.lower().split())[:80]


def merge_into_aggregate(
    aggregate_path: Path,
    tenants: list[dict],
    lookback_days: int = 90,
) -> None:
    """
    Read existing aggregate JSON (if any), merge in the given tenant runs by tenant_id,
    write back. Each item in `tenants` must have: tenant_id, tenant_name, lookback_days,
    is_live, results, findings_by_area, area_statuses, action_plan.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out: dict = {
        "updated_at": now,
        "lookback_days": lookback_days,
        "tenants_by_id": {},
        "tenants_by_slug": {},
    }
    if aggregate_path.is_file():
        try:
            raw = json.loads(aggregate_path.read_text(encoding="utf-8"))
            out["tenants_by_id"] = dict(raw.get("tenants_by_id") or {})
            out["tenants_by_slug"] = dict(raw.get("tenants_by_slug") or {})
            if raw.get("lookback_days") is not None:
                out["lookback_days"] = raw["lookback_days"]
        except (json.JSONDecodeError, OSError):
            pass
    for t in tenants:
        tid = t.get("tenant_id")
        if tid is None:
            continue
        tid_str = str(tid)
        slug = _slug(t.get("tenant_name") or "")
        payload = {
            "tenant_id": tid,
            "tenant_name": (t.get("tenant_name") or "").strip() or f"Tenant {tid}",
            "lookback_days": t.get("lookback_days", lookback_days),
            "is_live": bool(t.get("is_live")),
            "area_statuses": t.get("area_statuses") or {},
            "action_plan": t.get("action_plan") or [],
            "results": _json_safe(t.get("results") or {}),
            "findings_by_area": _json_safe(t.get("findings_by_area") or {}),
            "updated_at": now,
        }
        out["tenants_by_id"][tid_str] = payload
        if slug:
            out["tenants_by_slug"][slug] = tid_str
    aggregate_path.parent.mkdir(parents=True, exist_ok=True)
    aggregate_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
