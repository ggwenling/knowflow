"""Closed, deterministic request-to-evidence gate for citation repair.

This module deliberately understands only a small, versioned grammar. It does
not infer facts from evidence, call a model, or emit user-controlled text in a
decision. Any input outside the grammar is rejected.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from typing import Any

from .citation_verify import MAX_ANSWER_CODEPOINTS


RULE_VERSION = "repair-v1"
REPAIR_GATE_REASONS = frozenset({
    "not_checked", "unsupported_question", "ambiguous_question",
    "ineligible_reason", "no_claims", "candidate_incomplete",
    "no_verbatim_fact", "subject_mismatch", "relation_mismatch",
    "constraint_mismatch", "missing_value", "unsupported_context",
    "conflicting_evidence", "passed",
})

_MARKER = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9._:-]{0,127})\]", re.ASCII)
_FORMAT_WHITESPACE = re.compile(r"\s+")
_ENTITY_PATTERN = r"甲公司|乙公司|公司"
_YEAR_PATTERN = r"(?P<year>[0-9]{4})[ \t]*年[ \t]*"
_QUESTION_PATTERNS = (
    ("search_gate", re.compile(
        rf"(?:{_YEAR_PATTERN})?索引(?P<relation>何时可检索)[?？]?", re.ASCII)),
    ("default_cache_state", re.compile(
        rf"(?:{_YEAR_PATTERN})?缓存默认(?P<ask>关闭吗|状态是什么)[?？]?", re.ASCII)),
    ("net_profit", re.compile(
        rf"(?P<condition>缓存默认关闭时，)?"
        rf"(?P<subject>{_ENTITY_PATTERN})[ \t]*"
        rf"(?:{_YEAR_PATTERN})?净利润(?P<ask>是多少|有多高)[?？]?", re.ASCII)),
)

_FACT_PATTERNS = (
    ("search_gate", re.compile(
        rf"(?:原始资料说明[ \t]*)?(?:{_YEAR_PATTERN})?"
        r"索引[ \t]*READY[ \t]*后才可检索[。.]?", re.ASCII)),
    ("default_cache_state", re.compile(
        rf"(?:原始资料说明[ \t]*)?(?:{_YEAR_PATTERN})?"
        r"缓存默认(?P<state>关闭|开启)[。.]?", re.ASCII)),
    ("net_profit", re.compile(
        rf"(?:原始资料说明[ \t]*)?(?P<condition>缓存默认关闭时，)?"
        rf"(?P<subject>{_ENTITY_PATTERN})[ \t]*(?:{_YEAR_PATTERN})?"
        r"净利润为[ \t]*(?P<amount>-?[0-9]+(?:\.[0-9]+)?)[ \t]*"
        r"(?P<unit>亿元|万元|元)[。.]?", re.ASCII)),
)

_AMBIGUITY_HINTS = re.compile(
    r"分别|比较|对比|排名|哪年更|哪个更|哪些更|更高|更低|"
    r"以及|并且|还是|同时", re.ASCII)
_RELATION_ANCHORS = {
    "search_gate": ("可检索", "READY"),
    "default_cache_state": ("缓存默认",),
    "net_profit": ("净利润",),
}
_MISSING_VALUE_HINTS = re.compile(r"未披露|未知|暂无数据|没有数据|未提供|未说明")
_AMOUNT_VALUE = re.compile(r"净利润为[ \t]*-?[0-9]+(?:\.[0-9]+)?[ \t]*(?:亿元|万元|元)", re.ASCII)
_QUESTION_MARK = re.compile(r"[?？]")


@dataclass(frozen=True)
class RepairTarget:
    """A request parsed completely from the original question."""

    subject: str
    relation: str
    constraints: tuple[tuple[str, str], ...]
    expected_value_type: str
    rule_version: str = RULE_VERSION
    # Internal source spans prove that each extracted slot came from the
    # question itself. These are never copied into diagnostics or logs.
    spans: tuple[tuple[str, int, int], ...] = ()


@dataclass(frozen=True)
class RepairGateRejection:
    reason: str


@dataclass(frozen=True)
class RepairCandidateResult:
    accepted: bool
    reason: str


@dataclass(frozen=True)
class _RepairFact:
    subject: str
    relation: str
    constraints: tuple[tuple[str, str], ...]
    value_type: str
    value: str | Decimal | None
    unit: str | None = None


def _normalize(text: str) -> str:
    return _FORMAT_WHITESPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()


def _spans(match: re.Match[str], *names: str) -> tuple[tuple[str, int, int], ...]:
    return tuple((name, match.start(name), match.end(name))
                 for name in names
                 if name in match.re.groupindex and match.start(name) >= 0)


def _constraints(year: str | None, condition: str | None = None) -> tuple[tuple[str, str], ...]:
    values = []
    if year is not None:
        values.append(("year", year))
    if condition is not None:
        values.append(("condition", condition))
    return tuple(values)


def compound_question(question: str) -> bool:
    """True only when the request genuinely asks more than one question.

    Repeated or trailing question marks (``？？``) are punctuation rather than a
    second request, so they never make a question compound by themselves.
    """
    if not isinstance(question, str):
        return False
    segments = (segment.strip() for segment in _QUESTION_MARK.split(question))
    return len([segment for segment in segments if segment]) > 1


def _ambiguous_question(question: str) -> bool:
    """Detect conflicting requests, never punctuation alone."""
    if _AMBIGUITY_HINTS.search(question):
        return True
    years = re.findall(r"(?<![0-9])[0-9]{4}(?![0-9])", question, re.ASCII)
    if len(set(years)) > 1:
        return True
    anchors = sum(question.count(anchor) for anchor in ("何时可检索", "缓存默认", "净利润"))
    return anchors > 1


def parse_repair_target(question: str) -> RepairTarget | RepairGateRejection:
    """Parse one supported question in full, or return a finite rejection.

    Supported forms are intentionally limited to index readiness, cache
    default state, and net profit for the exact configured entity names.
    """
    if not isinstance(question, str):
        return RepairGateRejection("unsupported_question")
    normalized = _normalize(question)
    found: list[tuple[str, re.Match[str]]] = []
    for relation, pattern in _QUESTION_PATTERNS:
        match = pattern.fullmatch(normalized)
        if match is not None:
            found.append((relation, match))
    if len(found) > 1:
        return RepairGateRejection("ambiguous_question")
    if not found:
        return RepairGateRejection(
            "ambiguous_question" if _ambiguous_question(normalized) else "unsupported_question")

    relation, match = found[0]
    year = match.groupdict().get("year")
    condition_value = ("cache_default_closed"
                       if match.groupdict().get("condition") is not None else None)
    if relation == "search_gate":
        subject, value_type = "索引", "status_gate"
        spans = _spans(match, "year", "relation")
    elif relation == "default_cache_state":
        subject, value_type = "缓存", "cache_state"
        spans = _spans(match, "year", "ask")
    else:
        subject, value_type = match.group("subject"), "amount"
        spans = _spans(match, "subject", "year", "condition", "ask")
    return RepairTarget(subject=subject, relation=relation,
                        constraints=_constraints(year, condition_value),
                        expected_value_type=value_type, spans=spans)


def _parse_fact(text: str) -> _RepairFact | None:
    normalized = _normalize(text)
    for relation, pattern in _FACT_PATTERNS:
        match = pattern.fullmatch(normalized)
        if match is None:
            continue
        groups = match.groupdict()
        year = groups.get("year")
        condition = ("cache_default_closed"
                     if groups.get("condition") is not None else None)
        constraints = _constraints(year, condition)
        if relation == "search_gate":
            return _RepairFact("索引", relation, constraints, "status_gate", "ready_after")
        if relation == "default_cache_state":
            state = "closed" if groups["state"] == "关闭" else "open"
            return _RepairFact("缓存", relation, constraints, "cache_state", state)
        try:
            amount = Decimal(groups["amount"])
        except InvalidOperation:
            return None
        return _RepairFact(groups["subject"], relation, constraints, "amount",
                           amount, groups["unit"])
    return None


def _relation_anchor_present(target: RepairTarget, text: str) -> bool:
    return any(anchor in text for anchor in _RELATION_ANCHORS[target.relation])


def _missing_requested_value(target: RepairTarget, text: str) -> bool:
    if target.relation == "net_profit":
        if "相关年份" in text:
            return False
        if re.search(r"净利润不(?:为|是|等于)", text):
            return False
        return (target.subject in text and "净利润" in text
                and (_MISSING_VALUE_HINTS.search(text) is not None
                     or _AMOUNT_VALUE.search(text) is None))
    if target.relation == "default_cache_state":
        return "缓存默认" in text and not re.search(r"缓存默认(?:关闭|开启)", text)
    return "索引" in text and "可检索" in text and "READY" not in text


def _candidate_incomplete(generated: dict[str, Any], response: dict[str, Any],
                          diagnostics: dict[str, Any]) -> tuple[str | None, str | None]:
    """Check A1 completeness and return (source_id, unmarked fact text)."""
    if (not isinstance(generated, dict)
            or generated.get("has_answer") is not True
            or not isinstance(generated.get("answer"), str)
            or len(generated["answer"]) > MAX_ANSWER_CODEPOINTS
            or not isinstance(generated.get("source_ids"), list)
            or len(generated["source_ids"]) != 1):
        return None, None
    answer = generated["answer"]
    markers = list(_MARKER.finditer(answer))
    source_id = generated["source_ids"][0]
    if (not isinstance(source_id, str) or len(markers) != 1
            or markers[0].group(1) != source_id
            or diagnostics.get("decision") != "answered"
            or diagnostics.get("claims") != 1
            or diagnostics.get("kept_claims") != 1
            or diagnostics.get("dropped_claims") != 0
            or diagnostics.get("uncited_claims") != 0
            or not isinstance(response, dict)
            or response.get("has_answer") is not True
            or not isinstance(response.get("answer"), str)
            or len(response["answer"]) > MAX_ANSWER_CODEPOINTS
            or not isinstance(response.get("sources"), list)
            or len(response["sources"]) != 1
            or not isinstance(response["sources"][0], dict)
            or response["sources"][0].get("source_id") != source_id):
        return None, None
    fact_text = _normalize(_MARKER.sub("", answer))
    if not fact_text or _normalize(response["answer"]) != _normalize(answer):
        return None, None
    return source_id, fact_text


def _relevant_evidence_context(target: RepairTarget, evidence: list[dict[str, Any]],
                               cited_source_id: str, cited_fact: _RepairFact) -> str | None:
    """Return an A6 rejection reason if context is incomplete or conflicts."""
    for item in evidence:
        if not isinstance(item, dict) or item.get("source_id") == cited_source_id:
            continue
        text = item.get("text_content")
        if not isinstance(text, str):
            continue
        normalized = _normalize(text)
        fact = _parse_fact(normalized)
        if fact is not None:
            if fact.subject == target.subject and fact.relation == target.relation:
                if fact.constraints != target.constraints:
                    # A parsed fact about the same relation is not proven
                    # irrelevant merely because its constraints differ.
                    return "unsupported_context"
                if (fact.value_type != cited_fact.value_type
                        or fact.value != cited_fact.value
                        or fact.unit != cited_fact.unit):
                    return "conflicting_evidence"
            continue
        # Do not split long chunks or discard headings, conditions, negation,
        # quoted examples, or embedded instructions to recover a local clause.
        # An unparsed source naming the requested subject is not demonstrably
        # unrelated; a relation-anchor substring is not required as proof.
        if target.subject in normalized:
            return "unsupported_context"
    return None


def check_repair_candidate(target: RepairTarget, generated: dict[str, Any],
                           response: dict[str, Any], diagnostics: dict[str, Any],
                           evidence: list[dict[str, Any]]) -> RepairCandidateResult:
    """Apply A1–A6 to one already verifier-approved repair candidate."""
    source_id, fact_text = _candidate_incomplete(generated, response, diagnostics)
    if source_id is None or fact_text is None:
        return RepairCandidateResult(False, "candidate_incomplete")

    evidence_by_id = {item.get("source_id"): item.get("text_content")
                      for item in evidence if isinstance(item, dict)}
    source_text = evidence_by_id.get(source_id)
    if not isinstance(source_text, str) or _normalize(source_text) != fact_text:
        return RepairCandidateResult(False, "no_verbatim_fact")

    fact = _parse_fact(fact_text)
    if fact is None:
        if not _relation_anchor_present(target, fact_text):
            return RepairCandidateResult(False, "relation_mismatch")
        if _missing_requested_value(target, fact_text):
            return RepairCandidateResult(False, "missing_value")
        return RepairCandidateResult(False, "unsupported_context")

    if fact.relation != target.relation:
        return RepairCandidateResult(False, "relation_mismatch")
    if fact.subject != target.subject:
        return RepairCandidateResult(False, "subject_mismatch")
    if fact.constraints != target.constraints:
        return RepairCandidateResult(False, "constraint_mismatch")
    if fact.value_type != target.expected_value_type or fact.value is None:
        return RepairCandidateResult(False, "missing_value")

    context_reason = _relevant_evidence_context(target, evidence, source_id, fact)
    if context_reason is not None:
        return RepairCandidateResult(False, context_reason)
    return RepairCandidateResult(True, "passed")
