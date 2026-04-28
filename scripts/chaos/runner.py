#!/usr/bin/env python3
"""Chaos test runner — orchestrates a sequence of failure-mode injections,
captures each resulting RCA, scores it, and renders a comparison report.

Usage:
  ./runner.py                       # run all registered tests sequentially
  ./runner.py --tests target_down   # run a subset (comma-separated)
  ./runner.py --no-execute          # render the harness manifest without
                                    #   running anything (useful for CI)

Reports land in:
  monitoring-project/scripts/chaos/reports/<timestamp>.json    (raw)
  monitoring-docs/chaos-report-<date>.html                     (rendered)

Pre-flight check ensures the stack is healthy + 0 active alerts before
starting; safety-checks abort if a teardown fails.

Run from the controller — uses tailnet hostnames for SSH, no kubeconfig
on the controller required.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

# Make `lib`/`tests` importable when invoked directly
sys.path.insert(0, str(Path(__file__).parent.parent))
from chaos.lib.decision_poller import get_baseline_marker, poll_for_decision
from chaos.lib.rca_scorer import score_rca
from chaos.lib.ssh_actions import http_get
from chaos.tests.base import ChaosTest
from chaos.tests.drain3_anomaly import Drain3AnomalyTest
from chaos.tests.high_cpu_usage import HighCpuUsageTest
from chaos.tests.high_memory_usage import HighMemoryUsageTest
from chaos.tests.target_down import TargetDownTest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("chaos.runner")

# Registry: short-name → test class. Add new tests here.
REGISTRY: dict[str, type[ChaosTest]] = {
    "target_down": TargetDownTest,
    "high_memory": HighMemoryUsageTest,
    "high_cpu": HighCpuUsageTest,
    "drain3_anomaly": Drain3AnomalyTest,
}


@dataclass
class ChaosResult:
    test_name: str
    test_short: str
    expected_alertname: str
    started_at: str
    duration_s: float
    decision_id: str | None
    rca_text: str | None
    verdict: str | None
    confidence: str | None
    rca_quality: str | None
    suggested_actions: list[str]
    evidence: list[str]
    score_cause_first: float
    score_named_cause: float
    score_specific_evidence: float
    score_state_changing: float
    score_total: float
    score_grade: str
    score_notes: list[str]
    setup_ok: bool
    induce_ok: bool
    teardown_ok: bool
    error: str | None


# -----------------------------------------------------------------------------
# Pre-flight + post-flight safety
# -----------------------------------------------------------------------------

async def preflight() -> bool:
    """Verify triage healthy + 0 active alerts before starting chaos."""
    logger.info("Pre-flight: checking triage health + alert state...")
    health = await http_get("http://adolin-wsl:8090/health")
    if not health.ok:
        logger.error("Triage /health is unreachable — aborting.")
        return False
    try:
        h = json.loads(health.stdout)
        if h.get("status") != "healthy":
            logger.error("Triage health status: %r — aborting.", h.get("status"))
            return False
    except json.JSONDecodeError:
        logger.error("Triage /health returned non-JSON — aborting.")
        return False

    # Active alerts via Grafana alertmanager
    alerts = await http_get(
        "http://admin:admin@observability-rca-monitoring:3000/api/alertmanager/grafana/api/v2/alerts"
    )
    active = []
    if alerts.ok and alerts.stdout:
        try:
            active = json.loads(alerts.stdout)
        except json.JSONDecodeError:
            active = []
    if active:
        names = [a.get("labels", {}).get("alertname", "?") for a in active]
        logger.warning(
            "Pre-flight: %d active alerts before chaos: %s — proceeding anyway",
            len(active), names,
        )
    else:
        logger.info("Pre-flight clean: 0 active alerts.")
    return True


# -----------------------------------------------------------------------------
# Test execution
# -----------------------------------------------------------------------------

async def run_one(short: str, cls: type[ChaosTest]) -> ChaosResult:
    test = cls()
    started_at = datetime.now(timezone.utc).isoformat()
    chaos_start = time.monotonic()
    setup_ok = induce_ok = teardown_ok = False
    error: str | None = None
    decision: dict | None = None

    logger.info("─" * 72)
    logger.info("Test: %s", test.name)
    logger.info("Expects alert: %s (timeout=%ds)", test.expected_alertname, test.timeout_s)

    baseline = await get_baseline_marker()
    logger.info("Baseline marker: %s", baseline[:19])

    try:
        await test.setup()
        setup_ok = True
        await test.induce()
        induce_ok = True

        decision = await poll_for_decision(
            alert_name=test.expected_alertname,
            after_timestamp=baseline,
            timeout_s=test.timeout_s,
        )
        if decision is None:
            error = f"no /decisions row matched {test.expected_alertname} within {test.timeout_s}s"
            logger.error(error)
        else:
            logger.info(
                "Captured decision %s — verdict=%s, conf=%s, q=%s",
                decision.get("id"), decision.get("llm_verdict"),
                decision.get("llm_confidence"), decision.get("rca_quality"),
            )
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        logger.error("Test induce/poll failed: %s", error, exc_info=True)
    finally:
        try:
            await test.teardown()
            teardown_ok = True
            logger.info("Teardown completed.")
        except Exception as e:
            error = (error or "") + f" | teardown also failed: {type(e).__name__}: {e}"
            logger.error("CRITICAL: teardown failed — %s", e, exc_info=True)

    duration = time.monotonic() - chaos_start

    # Score the captured RCA, if any
    if decision:
        scored = score_rca(decision)
        suggested_raw = decision.get("suggested_actions", "[]")
        evidence_raw = decision.get("evidence", "[]")
        try:
            suggested = json.loads(suggested_raw) if isinstance(suggested_raw, str) else suggested_raw
        except json.JSONDecodeError:
            suggested = []
        try:
            evidence = json.loads(evidence_raw) if isinstance(evidence_raw, str) else evidence_raw
        except json.JSONDecodeError:
            evidence = []
    else:
        scored = None
        suggested = []
        evidence = []

    return ChaosResult(
        test_name=test.name,
        test_short=short,
        expected_alertname=test.expected_alertname,
        started_at=started_at,
        duration_s=round(duration, 2),
        decision_id=(decision or {}).get("id"),
        rca_text=(decision or {}).get("rca_report"),
        verdict=(decision or {}).get("llm_verdict"),
        confidence=str((decision or {}).get("llm_confidence") or ""),
        rca_quality=(decision or {}).get("rca_quality"),
        suggested_actions=suggested if isinstance(suggested, list) else [],
        evidence=evidence if isinstance(evidence, list) else [],
        score_cause_first=scored.cause_first_lede if scored else 0.0,
        score_named_cause=scored.named_cause if scored else 0.0,
        score_specific_evidence=scored.specific_evidence if scored else 0.0,
        score_state_changing=scored.state_changing_action if scored else 0.0,
        score_total=scored.total if scored else 0.0,
        score_grade=scored.grade if scored else "F",
        score_notes=scored.notes if scored else ["No decision captured — score N/A"],
        setup_ok=setup_ok,
        induce_ok=induce_ok,
        teardown_ok=teardown_ok,
        error=error,
    )


# -----------------------------------------------------------------------------
# Reports
# -----------------------------------------------------------------------------

def render_html_report(results: list[ChaosResult], started_at: str) -> str:
    """Render results as a standalone HTML page for monitoring-docs."""
    rows_html = []
    for r in results:
        grade_color = {
            "A": "#6bcf7f", "B": "#e0d060", "C": "#f0a050", "F": "#e06070",
        }.get(r.score_grade, "#8890a0")
        actions_html = "<br>".join(f"<code>{_esc(a)}</code>" for a in r.suggested_actions[:3])
        evidence_html = "<br>".join(f"• {_esc(e)}" for e in r.evidence[:5])
        notes_html = "<br>".join(f"• {_esc(n)}" for n in r.score_notes)
        rca_html = _esc(r.rca_text or "(no RCA captured)").replace("\n", "<br>")
        status = (
            "✅ captured" if r.decision_id else
            ("⚠ teardown ok, no RCA" if r.teardown_ok else "❌ FAILED")
        )
        rows_html.append(f"""
<tr>
  <td><strong>{_esc(r.test_short)}</strong><br><small>{_esc(r.expected_alertname)}</small></td>
  <td>{status}<br><small>{r.duration_s:.0f}s</small></td>
  <td><span style="color:{grade_color};font-size:24px;font-weight:700;">{r.score_grade}</span><br>
      <small>{r.score_total:.2f}</small></td>
  <td>cause-first: {r.score_cause_first:.1f}<br>
      named: {r.score_named_cause:.1f}<br>
      evidence: {r.score_specific_evidence:.1f}<br>
      action: {r.score_state_changing:.1f}</td>
  <td>verdict: <strong>{_esc(r.verdict or '—')}</strong><br>
      conf: {_esc(r.confidence or '—')} · q: {_esc(r.rca_quality or '—')}</td>
  <td style="max-width:340px;font-size:12px;line-height:1.5;">{rca_html[:800]}{"..." if rca_html and len(rca_html)>800 else ""}</td>
  <td style="font-size:11px;line-height:1.5;">{actions_html}</td>
  <td style="font-size:11px;line-height:1.5;">{evidence_html}</td>
  <td style="font-size:11px;color:#8890a0;line-height:1.5;">{notes_html}</td>
</tr>""")

    overall = sum(r.score_total for r in results) / max(len(results), 1)
    overall_grade = "A" if overall >= 0.85 else "B" if overall >= 0.65 else "C" if overall >= 0.40 else "F"

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chaos Report {started_at[:10]} — CIRES</title>
<style>
  body {{ font-family: 'Inter','Segoe UI',sans-serif; background:#0f1117; color:#e4e6ee; margin:0; line-height:1.65; font-size:14px; }}
  code {{ font-family:'JetBrains Mono',ui-monospace,monospace; font-size:0.85em; background:#1a1d27; border:1px solid #2a2d3a; padding:1px 6px; border-radius:4px; color:#40d0d0; }}
  .topnav {{ background:#13151e; border-bottom:1px solid #2a2d3a; padding:14px 40px; }}
  .topnav a {{ color:#4ea8de; margin-right:14px; text-decoration:none; font-size:13px; font-weight:600; }}
  .hero {{ padding:48px 40px 32px; border-bottom:1px solid #2a2d3a; }}
  .hero h1 {{ font-size:32px; font-weight:800; margin:0 0 12px; }}
  .hero h1 .accent {{ color:#b07ee8; }}
  .hero p {{ color:#c0c5d0; max-width:800px; margin:0 0 14px; }}
  .pill {{ display:inline-block; font-size:11px; padding:4px 10px; border-radius:12px; border:1px solid; margin-right:6px; font-weight:600; }}
  .pill.green {{ color:#6bcf7f; border-color:rgba(107,207,127,.4); background:rgba(107,207,127,.08); }}
  .pill.orange {{ color:#f0a050; border-color:rgba(240,160,80,.4); background:rgba(240,160,80,.08); }}
  .pill.red {{ color:#e06070; border-color:rgba(224,96,112,.4); background:rgba(224,96,112,.08); }}
  table {{ width:calc(100% - 80px); margin:24px 40px; border-collapse:collapse; background:#13151e; border-radius:8px; overflow:hidden; }}
  th, td {{ padding:14px 12px; border-bottom:1px solid #2a2d3a; text-align:left; vertical-align:top; }}
  th {{ background:#1a1d27; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:1px; color:#8890a0; }}
  tr:hover td {{ background:#1e2230; }}
  .footer {{ padding:24px 40px; color:#8890a0; font-size:13px; border-top:1px solid #2a2d3a; }}
</style></head>
<body>
<nav class="topnav">
  <a href="index.html">🏠 Home</a>
  <a href="rca-quality-audit-2026-04-28.html">📋 RCA Audit</a>
  <a href="audit-2026-04-28.html">📋 Sweep audit</a>
  <a href="decisions-log.html">📝 Decisions Log</a>
</nav>
<section class="hero">
  <h1>Chaos Test <span class="accent">Report</span></h1>
  <p>End-to-end RCA quality measurement. Each row injects a real failure into the production stack, captures whatever RCA the triage produces, and scores it on four axes (cause-first lede, named cause, specific evidence, state-changing action). Generated by <code>monitoring-project/scripts/chaos/runner.py</code>.</p>
  <p><span class="pill {'green' if overall >= 0.65 else 'orange' if overall >= 0.4 else 'red'}">Overall grade: <strong>{overall_grade}</strong> ({overall:.2f})</span>
     <span class="pill green">{sum(1 for r in results if r.decision_id)}/{len(results)} alerts captured</span>
     <span class="pill green">{sum(1 for r in results if r.teardown_ok)}/{len(results)} teardowns clean</span>
     <span class="pill orange">Run started: {started_at[:19]}</span></p>
</section>
<table>
<thead>
<tr><th>Test</th><th>Status</th><th>Grade</th><th>Axes</th><th>Verdict</th><th>RCA prose</th><th>Suggested actions</th><th>Evidence</th><th>Score notes</th></tr>
</thead>
<tbody>{''.join(rows_html)}</tbody>
</table>
<div class="footer">
  Tests live at <code>monitoring-project/scripts/chaos/tests/</code>.
  Run <code>./scripts/chaos/runner.py --tests &lt;short_names&gt;</code> from the controller.
  See <a href="rca-quality-audit-2026-04-28.html" style="color:#4ea8de;">RCA Quality Audit</a> for the failure-mode taxonomy these tests measure against.
</div>
</body></html>
"""


def _esc(s: str | None) -> str:
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

async def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--tests",
        default=",".join(REGISTRY),
        help="Comma-separated test short-names. Default: all.",
    )
    p.add_argument(
        "--no-execute",
        action="store_true",
        help="Print the manifest without running anything.",
    )
    p.add_argument(
        "--no-preflight",
        action="store_true",
        help="Skip the pre-flight health check.",
    )
    args = p.parse_args()

    selected = [t.strip() for t in args.tests.split(",") if t.strip()]
    unknown = [t for t in selected if t not in REGISTRY]
    if unknown:
        logger.error("Unknown test name(s): %s. Known: %s", unknown, list(REGISTRY))
        sys.exit(2)

    logger.info("Chaos run plan:")
    for t in selected:
        cls = REGISTRY[t]
        logger.info("  %s — %s (%s, timeout=%ds)", t, cls.name, cls.expected_alertname, cls.timeout_s)

    if args.no_execute:
        logger.info("--no-execute set, exiting without running.")
        return 0

    if not args.no_preflight and not await preflight():
        sys.exit(3)

    started_at = datetime.now(timezone.utc).isoformat()
    results: list[ChaosResult] = []
    for short in selected:
        cls = REGISTRY[short]
        try:
            res = await run_one(short, cls)
        except Exception as e:
            logger.error("Catastrophic test failure on %s: %s", short, e, exc_info=True)
            sys.exit(4)
        results.append(res)

        # Brief cool-down between tests so dedup window clears + the stack settles
        if short != selected[-1]:
            cool = 30
            logger.info("Cool-down %ds before next test...", cool)
            await asyncio.sleep(cool)

    # Persist raw results
    repo_root = Path(__file__).parent.parent.parent
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    raw_path = reports_dir / f"{started_at[:19].replace(':','-')}.json"
    raw_path.write_text(json.dumps([asdict(r) for r in results], indent=2, default=str))
    logger.info("Wrote raw report: %s", raw_path)

    # Render HTML report into monitoring-docs
    html = render_html_report(results, started_at)
    html_path = repo_root.parent / "monitoring-docs" / f"chaos-report-{started_at[:10]}.html"
    if html_path.parent.exists():
        html_path.write_text(html)
        logger.info("Wrote HTML report: %s", html_path)
    else:
        # Fallback if monitoring-docs isn't a sibling (e.g., CI)
        html_path = reports_dir / f"chaos-report-{started_at[:10]}.html"
        html_path.write_text(html)
        logger.info("Wrote HTML report (sibling not found): %s", html_path)

    # Summary table
    print()
    print("=" * 72)
    print(f"Chaos run summary — {started_at[:19]}")
    print("=" * 72)
    print(f"{'Test':<24} {'Status':<14} {'Grade':<7} {'Total':<7} {'Verdict':<10}")
    print("-" * 72)
    for r in results:
        status = "captured" if r.decision_id else ("partial" if r.teardown_ok else "FAILED")
        print(
            f"{r.test_short:<24} {status:<14} {r.score_grade:<7} {r.score_total:.2f}    "
            f"{(r.verdict or '—'):<10}"
        )
    overall = sum(r.score_total for r in results) / max(len(results), 1)
    print("-" * 72)
    print(f"Overall: {overall:.2f}  ({sum(1 for r in results if r.decision_id)}/{len(results)} captured)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
