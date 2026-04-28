"""Score a captured RCA on four quality axes.

Each axis returns 0.0 (fail), 0.5 (partial), or 1.0 (clean pass).
Total score is the mean across the four. The scorer is deliberately
conservative — false-positive scoring (rating bad RCAs as good) would
mask the regressions chaos tests are meant to catch, so when in doubt
we score lower.
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
    notes: list[str]

    @property
    def total(self) -> float:
        return (
            self.cause_first_lede
            + self.named_cause
            + self.specific_evidence
            + self.state_changing_action
        ) / 4

    @property
    def grade(self) -> str:
        t = self.total
        if t >= 0.85:
            return "A"
        if t >= 0.65:
            return "B"
        if t >= 0.40:
            return "C"
        return "F"


def score_rca(decision: dict) -> QualityScore:
    """Score a captured /decisions row on four axes."""
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

    return QualityScore(
        cause_first_lede=cause_first,
        named_cause=named_cause,
        specific_evidence=specific_evidence,
        state_changing_action=state_changing,
        notes=notes,
    )
