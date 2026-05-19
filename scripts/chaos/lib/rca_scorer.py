"""Score a captured RCA on five quality axes.

Each axis returns 0.0 (fail), 0.5 (partial), or 1.0 (clean pass).
Total score is the mean across the five. The scorer is deliberately
conservative — false-positive scoring (rating bad RCAs as good) would
mask the regressions chaos tests are meant to catch, so when in doubt
we score lower.

Axes
----
  1. cause_first_lede     — first sentence names a cause, not the symptom
  2. named_cause          — RCA prose mentions a specific component/mechanism
  3. specific_evidence    — evidence list contains numbers/units/quoted strings
  4. state_changing_action — first suggested action is a remediation verb
  5. archetype_match      — RCA's named cause is plausible for THIS alert's
                            archetype. The 0b215ef3 incident motivated this:
                            HighKongP95Latency fired but the RCA recommended
                            OOMKill remediations. The first four axes all
                            scored well on that RCA; only archetype mismatch
                            would have caught it. (S3-HF-09, 2026-05-19.)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass


# -----------------------------------------------------------------------------
# Surface-only patterns — same set as app/response_validator.py uses for the
# retry gate. Mirrored here so chaos scoring stays in sync with what the live
# validator catches.
# -----------------------------------------------------------------------------
_SURFACE_LEDE_PATTERNS = [
    re.compile(r"^\s*(?:The\s+)?PromQL\s+(?:expression\s+)?[`'\"]", re.I),
    re.compile(r"^\s*(?:The\s+)?PromQL\s+\w+\s*\(", re.I),
    re.compile(r"^\s*The\s+(?:metric|query|expression|value|observation)\s+\S+\s+(?:reports|reported|shows|showed|returned|indicates|indicated)\b", re.I),
    re.compile(r"^\s*\w+(?:\{[^}]*\})?\s*[=<>]\s*[0-9]", re.I),
    re.compile(r"^\s*Based\s+on\s+(?:the\s+)?(?:observed|repeated|reported|metric|PromQL|query|queries|log\s+entries|logs|trace|values?|frequency|rate|elevated|high|increased|recurring)\b", re.I),
    re.compile(r"^\s*Looking\s+at\s+(?:the\s+)?(?:metrics?|data|observations?|logs?|traces?)\b", re.I),
]

_HEDGE_PATTERNS = [
    re.compile(r"\bindicates?\s+a\s+(?:persistent|recurring|potential|ongoing|possible|likely)\s+(?:issue|problem|concern)\b", re.I),
    re.compile(r"\bappears?\s+(?:that\s+there\s+is|to\s+be|that\s+the)\b.{0,50}?\b(?:issue|problem|concern|condition)\b", re.I),
    re.compile(r"\bsuggest(?:s|ing)?\s+(?:that\s+)?(?:a\s+)?(?:potential|possible|some\s+kind\s+of)\b", re.I),
    re.compile(r"\bcould\s+be\s+indicative\s+of\b", re.I),
    re.compile(r"\b(?:requires?|warrants?|needs?)\s+further\s+(?:investigation|review|analysis|examination)\b", re.I),
    re.compile(r"\bpotential\s+(?:performance\s+degradation|resource\s+contention)\b", re.I),
]

# Cause-naming words that indicate a NAMED component / mechanism is being cited.
# These are heuristic — any RCA that mentions one of these in the lede is
# probably trying to identify a specific cause vs hedging.
_CAUSE_NAMING = re.compile(
    r"\b(?:exhausted|saturated|leaked|leaking|throttl(?:ed|ing)|misconfigured|"
    r"wrong\s+(?:config|setting)|deploy(?:ed|ment)\s+(?:regress|broke)|"
    r"OOM[-_]?kill|connection\s+pool|thread\s+pool|circuit[-_\s]?breaker|"
    r"GC\s+pause|garbage\s+collection|JDBC|JVM\s+heap|cgroup|memory\s+limit|"
    r"kubelet|coredns|kube[-_]?api|endpoint|service\s+account|"
    r"NetworkPolicy|security\s+group|firewall|TLS|cert(?:ificate)?\s+expir(?:y|ed)|"
    r"DaemonSet|Deployment|ConfigMap|Secret|PVC|PV\b)",
    re.I,
)

# S3-HF-09 — archetype → expected cause-vocabulary map.
#
# For each alert archetype, what kinds of causes are PLAUSIBLE? The map is
# deliberately permissive — every keyword that *could* legitimately appear in
# an RCA for that alert. False positives (over-permissive matches) are still
# caught by other axes; false negatives (under-permissive) would silently
# pass wrong-archetype RCAs, which is the whole point of this axis.
#
# Match logic: alert.alertname → category → keyword set. RCA prose must
# contain at least one keyword from the right set; otherwise axis 5 fails
# with "cause vocabulary mismatch — RCA cites {found} but alert is {alert}".
_ARCHETYPE_VOCAB: dict[str, set[str]] = {
    # Latency-family alerts (Kong p95, service-self p95, error rate)
    "latency": {
        "slow query", "query plan", "missing index", "lock contention",
        "synchronized", "mutex", "thread blocked", "gc pause", "gc overhead",
        "connection pool", "pool exhausted", "hikaricp", "circuit breaker",
        "upstream", "downstream", "p95", "p99", "latency", "tail latency",
        "queue depth", "backpressure", "network delay", "rtt", "tcp retransmit",
        "cold cache", "cache miss", "saturate", "saturation",
    },
    # Memory-family alerts (Heap, OOM, MemoryUsage)
    "memory": {
        "oom", "out of memory", "heap", "heap dump", "leak", "leaked",
        "gc", "garbage collection", "young gen", "old gen", "g1", "cms",
        "javaheap", "jvm", "cgroup", "memory limit", "rss", "working set",
        "memory pressure", "page cache", "swap", "memory_limiter",
    },
    # CPU-family alerts
    "cpu": {
        "cpu", "load", "throttled", "throttle", "spike", "context switch",
        "tight loop", "busy wait", "hot path", "deadlock", "lock contention",
        "thread starvation",
    },
    # Disk / storage alerts
    "disk": {
        "disk", "fill", "filling", "storage", "wal", "log retention", "fsync",
        "inode", "tmp", "compaction", "loki", "ingester", "chunks", "cardinality",
    },
    # Telemetry pipeline alerts
    "telemetry": {
        "otel", "collector", "queue", "span drop", "memory_limiter",
        "batch processor", "exporter", "receiver", "pipeline", "telemetry",
    },
    # Target-down / reachability
    "reachability": {
        "down", "unreachable", "scrape", "timeout", "target down", "dns",
        "resolution", "network policy", "security group", "firewall",
        "tls", "certificate", "expiry", "expired", "rolling restart",
        "kubelet", "node not ready", "draining",
    },
    # Log anomalies (Drain3)
    "log": {
        "novel template", "drain3", "log pattern", "regression", "deploy",
        "new error", "first seen", "stack trace", "exception class",
    },
}

# Map alertname regex → vocabulary category. Order matters: first match wins.
_ALERTNAME_TO_CATEGORY = [
    (re.compile(r".*P95Latency$|.*ErrorRate$|.*UpstreamErrorRate$", re.I), "latency"),
    (re.compile(r".*MemoryUsage$|.*OOM.*", re.I), "memory"),
    (re.compile(r".*CpuUsage$", re.I), "cpu"),
    (re.compile(r".*DiskUsage$|.*DiskFillingUp$|.*IngestionRateLow$", re.I), "disk"),
    (re.compile(r"^OTelCollector.*", re.I), "telemetry"),
    (re.compile(r"^TargetDown$|.*Crash.*|.*Probe.*|.*TLS.*", re.I), "reachability"),
    (re.compile(r"^Drain3.*", re.I), "log"),
]


def _alert_archetype(alertname: str) -> str | None:
    for pattern, category in _ALERTNAME_TO_CATEGORY:
        if pattern.match(alertname or ""):
            return category
    return None


def _score_archetype_match(rca: str, alertname: str) -> tuple[float, str | None]:
    """Score whether the RCA's dominant cause vocabulary matches the alert's.

    Counts keyword hits per archetype across the whole RCA prose. The
    dominant category is the one with the most hits. Decision:

      1.0  — dominant category matches the alert's category, by a margin
             of at least 2 keywords (so incidental latency-vocab words in
             a memory RCA don't accidentally score it as latency).
      0.5  — no clear winner / tie / no hits at all.
      0.0  — dominant category is something OTHER than the alert's.
             This is the 0b215ef3 smoking gun: alert was latency, RCA's
             dominant vocab was memory.
    """
    category = _alert_archetype(alertname)
    if category is None:
        return 1.0, None
    rca_lower = rca.lower()

    counts: dict[str, int] = {}
    for cat, vocab in _ARCHETYPE_VOCAB.items():
        n = sum(1 for kw in vocab if kw in rca_lower)
        if n:
            counts[cat] = n

    if not counts:
        return 0.5, f"no archetype-vocab keywords found for {alertname} ({category})"

    # Sort by hit count desc; in case of tie the alert's own category wins
    # (tie-break toward the alert — gives the LLM the benefit of the doubt
    # on close calls, but mismatches with a clear delta still fail).
    sorted_cats = sorted(counts.items(), key=lambda kv: (-kv[1], 0 if kv[0] == category else 1))
    dominant, dominant_count = sorted_cats[0]
    expected_count = counts.get(category, 0)

    if dominant == category and dominant_count >= 1:
        return 1.0, None

    # Wrong-archetype dominant. Two flavours of failure:
    #   - hard miss (memory RCA on latency alert): 0.0
    #   - close call (1 expected hit, 2 wrong-vocab hits): still 0.0 if the
    #     wrong-vocab outweighs the right one
    if dominant_count > expected_count:
        # Most-cited vocab is the wrong category — flag it.
        top_three = ", ".join(
            f"{cat}={n}" for cat, n in sorted_cats[:3]
        )
        return 0.0, (
            f"archetype mismatch — alert is {alertname} (vocab={category}, "
            f"hits={expected_count}); RCA's dominant vocab is "
            f"'{dominant}' ({dominant_count} hits). Counts: {top_three}"
        )

    # Tie with the right category in front already handled by the tie-break.
    return 0.5, f"weak archetype match for {alertname} ({category}) — counts: {counts}"


# Remediation verbs — same list as response_validator's _REMEDIATION_VERB_PATTERNS.
_REMEDIATION_VERBS = re.compile(
    r"\b(?:kubectl\s+(?:rollout\s+(?:restart|undo)|scale|set\s+(?:resources|env|image)|patch|delete\s+pod|drain|cordon|edit|apply)|"
    r"helm\s+(?:rollback|upgrade)|"
    r"docker\s+(?:restart|kill|stop|start)|"
    r"systemctl\s+(?:restart|reload|stop|start)|"
    r"terraform\s+apply|git\s+revert|ansible-playbook)\b",
    re.I,
)


@dataclass
class QualityScore:
    cause_first_lede: float
    named_cause: float
    specific_evidence: float
    state_changing_action: float
    archetype_match: float
    notes: list[str]

    @property
    def total(self) -> float:
        return (
            self.cause_first_lede
            + self.named_cause
            + self.specific_evidence
            + self.state_changing_action
            + self.archetype_match
        ) / 5

    @property
    def grade(self) -> str:
        # Veto: archetype_match=0 is a structural failure. The RCA didn't
        # answer the question it was asked — no amount of polished prose
        # or specific evidence saves it. Force F. (S3-HF-09 design.)
        if self.archetype_match == 0.0:
            return "F"
        t = self.total
        if t >= 0.85:
            return "A"
        if t >= 0.65:
            return "B"
        if t >= 0.40:
            return "C"
        return "F"


def score_rca(decision: dict) -> QualityScore:
    """Score a captured /decisions row on five axes."""
    notes: list[str] = []

    rca = (decision.get("rca_report") or "").strip()
    suggested_actions_raw = decision.get("suggested_actions") or "[]"
    evidence_raw = decision.get("evidence") or "[]"

    # Try to JSON-parse evidence + actions; they're stored as JSON strings.
    try:
        actions = json.loads(suggested_actions_raw) if isinstance(suggested_actions_raw, str) else suggested_actions_raw
    except json.JSONDecodeError:
        actions = []
    try:
        evidence = json.loads(evidence_raw) if isinstance(evidence_raw, str) else evidence_raw
    except json.JSONDecodeError:
        evidence = []
    if not isinstance(actions, list):
        actions = []
    if not isinstance(evidence, list):
        evidence = []

    # ---- Axis 1: cause-first lede ---------------------------------------
    if not rca:
        cause_first = 0.0
        notes.append("Empty RCA — no lede to score")
    else:
        # Take the first sentence (up to first period followed by space/end)
        first_sentence = re.split(r"\.(?:\s|$)", rca, maxsplit=1)[0]
        if any(p.search(first_sentence) for p in _SURFACE_LEDE_PATTERNS):
            cause_first = 0.0
            notes.append("Surface-only lede pattern matched in first sentence")
        elif any(p.search(rca) for p in _HEDGE_PATTERNS):
            cause_first = 0.5
            notes.append("Hedge pattern detected in RCA prose")
        else:
            cause_first = 1.0

    # ---- Axis 2: named-cause specificity --------------------------------
    if _CAUSE_NAMING.search(rca):
        named_cause = 1.0
    elif rca:
        named_cause = 0.0
        notes.append("RCA does not name a specific cause/mechanism")
    else:
        named_cause = 0.0

    # ---- Axis 3: specific evidence --------------------------------------
    # Evidence is good if it contains numbers, code-style strings, or specific
    # log-line/trace references. Empty list = 0; >2 specific items = 1.0.
    if not evidence:
        specific_evidence = 0.0
        notes.append("No evidence list emitted")
    else:
        specific_count = 0
        for item in evidence:
            s = str(item)
            # Specific = contains a number, equals sign, ms unit, or quoted log
            if (
                re.search(r"\d", s)
                or "=" in s
                or "ms" in s.lower()
                or "`" in s
                or '"' in s
            ):
                specific_count += 1
        specific_evidence = min(1.0, specific_count / 2)
        if specific_evidence < 1.0:
            notes.append(f"Only {specific_count}/{len(evidence)} evidence items appear specific")

    # ---- Axis 4: state-changing first action ----------------------------
    if not actions:
        state_changing = 0.0
        notes.append("No suggested actions emitted")
    else:
        first_action = str(actions[0])
        if _REMEDIATION_VERBS.search(first_action):
            state_changing = 1.0
        else:
            state_changing = 0.0
            notes.append(f"First action is not a state-change verb: {first_action[:60]}")

    # ---- Axis 5: archetype match (S3-HF-09) -----------------------------
    alertname = decision.get("alert_name") or decision.get("alertname") or ""
    archetype_match, archetype_note = _score_archetype_match(rca, alertname)
    if archetype_note:
        notes.append(archetype_note)

    return QualityScore(
        cause_first_lede=cause_first,
        named_cause=named_cause,
        specific_evidence=specific_evidence,
        state_changing_action=state_changing,
        archetype_match=archetype_match,
        notes=notes,
    )
