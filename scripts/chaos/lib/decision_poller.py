"""Poll the triage /decisions endpoint for a new row matching a chaos test.

The chaos runner records a baseline decision count + timestamp before
inducing chaos, then polls for a row that:
  - has alert_name matching the test's expected alertname
  - has timestamp newer than the baseline
The first match wins.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from .ssh_actions import http_get

logger = logging.getLogger(__name__)

DECISIONS_URL = "http://adolin-wsl:8090/decisions?limit=20"


async def get_baseline_marker() -> str:
    """Return the ISO timestamp of the most recent decision, or '0000' if none.

    Used as the watermark — anything newer than this is a candidate for
    "alert produced by the chaos action."
    """
    res = await http_get(DECISIONS_URL)
    if not res.ok or not res.stdout:
        logger.warning("Could not get baseline decisions: rc=%s", res.rc)
        return "0000"
    try:
        rows = json.loads(res.stdout)
        if not rows:
            return "0000"
        return rows[0].get("timestamp", "0000")
    except json.JSONDecodeError:
        return "0000"


async def poll_for_decision(
    alert_name: str,
    after_timestamp: str,
    timeout_s: int = 600,
    poll_interval_s: float = 8.0,
) -> dict[str, Any] | None:
    """Poll /decisions until a row appears with alert_name + timestamp > after.

    Returns the decision row dict or None if timeout.
    """
    deadline = asyncio.get_event_loop().time() + timeout_s
    poll_count = 0

    while asyncio.get_event_loop().time() < deadline:
        poll_count += 1
        res = await http_get(DECISIONS_URL)
        if res.ok and res.stdout:
            try:
                rows = json.loads(res.stdout)
            except json.JSONDecodeError:
                rows = []
            for row in rows:
                ts = row.get("timestamp", "")
                name = row.get("alert_name", "")
                if name == alert_name and ts > after_timestamp:
                    elapsed = poll_count * poll_interval_s
                    logger.info(
                        "Decision matched on poll #%d (~%.0fs): id=%s, alert=%s, verdict=%s",
                        poll_count, elapsed, row.get("id"), name, row.get("llm_verdict"),
                    )
                    return row
        await asyncio.sleep(poll_interval_s)

    logger.warning(
        "Polled for %d/%s after %s with no match in %ds (%d polls)",
        poll_count, alert_name, after_timestamp, timeout_s, poll_count,
    )
    return None
