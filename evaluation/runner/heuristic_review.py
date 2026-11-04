"""Heuristic support and citation review shared by offline review scripts."""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable


MARKER = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9._:-]{0,127})\]", re.ASCII)
SENTENCE_BOUNDARIES = "。！？.!?；;\n"
CLAUSE_BOUNDARIES = "，、；;"
_PART_BOUNDARIES = re.compile(r"[，。；、！？.!?;:\s]+")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_NEGATION = re.compile(
    r"(无需|不得|不能|不可|不应|不会|不是|没有|无|未|非|勿|别|禁止|不可以|不用)")
_CN_NUM = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "百": 100, "千": 1000,
    "万": 10000,
}
_CN_NUM_RE = re.compile(r"[零〇一二两三四五六七八九十百千万]+")
_CLAUSE_SPLIT = re.compile(
    r"[，,、；;。！？!?\n]+|(?<!\d)\.(?!\d)|但是|然而|不过|但|而")
_NORMALIZE_PUNCTUATION = frozenset(
    "，。；、！？!?.,:：;\"'“”‘’（）()【】[]{}<>《》〈〉「」『』"
    "—–-…·_／/\\|~`　"
)


def _sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
    left = max((text.rfind(mark, 0, start) for mark in SENTENCE_BOUNDARIES),
               default=-1) + 1
    following = [text.find(mark, end) for mark in SENTENCE_BOUNDARIES]
    following = [position for position in following if position >= 0]
    right = min(following) + 1 if following else len(text)
    return left, right


def _marker_attach_start(answer: str, marker_start: int) -> int:
    cursor = marker_start
    while cursor > 0 and answer[cursor - 1] in "。.!？?\n ":
        cursor -= 1
    while True:
        found = None
        for match in MARKER.finditer(answer):
            if match.end() <= cursor and answer[match.end():cursor].strip() == "":
                found = match
        if found is None:
            break
        cursor = found.start()
        while cursor > 0 and answer[cursor - 1] in "。.!？?\n ":
            cursor -= 1
    return cursor


def sentence_around(answer: str, marker_index: int) -> str:
    markers = list(MARKER.finditer(answer))
    if type(marker_index) is not int or not 0 <= marker_index < len(markers):
        return answer
    marker = markers[marker_index]
    attach = _marker_attach_start(answer, marker.start())
    left, right = _sentence_span(answer, attach, marker.end())
    return answer[left:right].strip()


def clause_around(answer: str, marker_index: int) -> str:
    markers = list(MARKER.finditer(answer))
    if type(marker_index) is not int or not 0 <= marker_index < len(markers):
        return answer
    marker = markers[marker_index]
    attach = _marker_attach_start(answer, marker.start())
    sentence_left, sentence_right = _sentence_span(
        answer, attach, marker.end())
    left = max((answer.rfind(mark, sentence_left, attach)
                for mark in CLAUSE_BOUNDARIES), default=-1)
    left = sentence_left if left < 0 else left + 1
    right_candidates = [answer.find(mark, marker.end(), sentence_right)
                        for mark in CLAUSE_BOUNDARIES]
    right_candidates = [position for position in right_candidates if position >= 0]
    right = min(right_candidates) if right_candidates else sentence_right
    return answer[left:right].strip()


def attributed_clause(answer: str, marker_index: int) -> str:
    markers = list(MARKER.finditer(answer))
    if type(marker_index) is not int or not 0 <= marker_index < len(markers):
        return ""
    marker = markers[marker_index]
    attach = _marker_attach_start(answer, marker.start())
    left, _right = _sentence_span(answer, attach, marker.end())
    cluster = [item for item in markers
               if _marker_attach_start(answer, item.start()) == attach]
    if not cluster:
        return ""
    first = min(item.start() for item in cluster)
    lead = answer[left:_marker_attach_start(answer, first)]
    clauses = [part.strip() for part in re.split(r"[，、；;]", lead) if part.strip()]
    if not clauses:
        return lead.strip()
    index = cluster.index(marker)
    if len(clauses) == len(cluster):
        return clauses[index]
    if len(clauses) > len(cluster):
        return clauses[len(clauses) - len(cluster) + index]
    return lead.strip()


def citation_claims(answer: str, marker_index: int,
                    claim: str | None = None) -> tuple[str, str]:
    markers = list(MARKER.finditer(answer))
    if type(marker_index) is not int or not 0 <= marker_index < len(markers):
        cleaned_claim = MARKER.sub("", claim or "").strip()
        return answer, cleaned_claim
    local_claim = clause_around(answer, marker_index)
    if isinstance(claim, str) and MARKER.sub("", claim).strip():
        local_claim = claim
    claim_body = MARKER.sub("", local_claim).strip(
        " \t\r\n，、。；;！？.!?")
    return local_claim, claim_body


def contentful_parts(text: str) -> list[str]:
    cleaned = MARKER.sub("", text)
    return [part for part in _PART_BOUNDARIES.split(cleaned) if len(part) >= 2]


def _evidence_texts(evidence: str | Iterable[str]) -> list[str]:
    if isinstance(evidence, str):
        return [evidence]
    return [text for text in evidence if isinstance(text, str)]


def _normalize(text: str) -> str:
    text = MARKER.sub("", text).casefold()

    def replace_chinese_number(match: re.Match[str]) -> str:
        parsed = _parse_cn_number(match.group(0))
        return str(parsed) if parsed is not None else match.group(0)

    text = _CN_NUM_RE.sub(replace_chinese_number, text)
    return "".join(char for char in text
                   if not char.isspace() and char not in _NORMALIZE_PUNCTUATION)


def _parse_cn_number(token: str) -> int | None:
    if not token or any(char not in _CN_NUM for char in token):
        return None
    digit_chars = {"零", "〇", "一", "二", "两", "三", "四", "五",
                   "六", "七", "八", "九"}
    if all(char in digit_chars for char in token):
        return int("".join(str(_CN_NUM[char]) for char in token))
    total = section = current = 0
    for char in token:
        value = _CN_NUM[char]
        if value >= 10:
            if current == 0:
                current = 1
            if value == 10000:
                section += current
                total += section * value
                section = 0
            else:
                section += current * value
            current = 0
        else:
            current = value
    return total + section + current


def _extract_numbers(text: str) -> set[str]:
    cleaned = MARKER.sub("", text)
    values: set[str] = set()
    for match in _NUMBER.finditer(cleaned):
        values.add(match.group(0))
    for match in _CN_NUM_RE.finditer(cleaned):
        parsed = _parse_cn_number(match.group(0))
        if parsed is not None:
            values.add(str(parsed))
    return values


def _matching_text(text: str) -> str:
    """Text used to align claims and evidence, ignoring number/polarity changes."""
    cleaned = MARKER.sub("", text)
    cleaned = _NEGATION.sub("", cleaned)
    cleaned = _NUMBER.sub("", cleaned)
    cleaned = _CN_NUM_RE.sub("", cleaned)
    return _normalize(cleaned)


def _overlap_without_numbers_or_polarity(claim: str, evidence: str) -> float:
    claim_text = _matching_text(claim)
    evidence_text = _matching_text(evidence)
    if not claim_text:
        return 0.0
    if len(claim_text) == 1:
        return 1.0 if claim_text in evidence_text else 0.0
    claim_bigrams = Counter(claim_text[index:index + 2]
                            for index in range(len(claim_text) - 1))
    evidence_bigrams = Counter(evidence_text[index:index + 2]
                               for index in range(len(evidence_text) - 1))
    matched = sum(min(count, evidence_bigrams[bigram])
                  for bigram, count in claim_bigrams.items())
    return matched / sum(claim_bigrams.values())


def _clauses(text: str) -> list[str]:
    return [part.strip() for part in _CLAUSE_SPLIT.split(text) if part.strip()]


def _best_matching_evidence_clauses(
        claim: str, evidence: str | Iterable[str]) -> list[str]:
    clauses = [clause for source in _evidence_texts(evidence)
               for clause in _clauses(source)]
    if not clauses:
        return []
    scores = [(_overlap_without_numbers_or_polarity(claim, clause), clause)
              for clause in clauses]
    best_score = max(score for score, _clause in scores)
    if best_score < 0.55:
        return []
    # Equally good matches can be repeated evidence; lower-overlap clauses
    # must not lend their numbers or polarity to the best topical match.
    return [clause for score, clause in scores if score == best_score]


def _numbers_compatible(sentence: str, evidence: str | Iterable[str]) -> bool:
    for claim_clause in _clauses(sentence):
        claim_numbers = _extract_numbers(claim_clause)
        if not claim_numbers:
            continue
        matches = _best_matching_evidence_clauses(claim_clause, evidence)
        if not matches:
            return False
        evidence_numbers = set().union(*(_extract_numbers(match)
                                         for match in matches))
        if not claim_numbers.issubset(evidence_numbers):
            return False
    return True


def _negation_tokens(text: str) -> set[str]:
    return set(_NEGATION.findall(MARKER.sub("", text)))


def _negation_compatible(sentence: str, evidence: str | Iterable[str]) -> bool:
    for claim_clause in _clauses(sentence):
        matches = _best_matching_evidence_clauses(claim_clause, evidence)
        claim_is_negative = bool(_negation_tokens(claim_clause))
        if any(claim_is_negative != bool(_negation_tokens(match))
               for match in matches):
            return False
    return True


def _conflicts(sentence: str, evidence: str | Iterable[str]) -> bool:
    return (not _numbers_compatible(sentence, evidence)
            or not _negation_compatible(sentence, evidence))


def _strict_grounded(sentence: str, evidence: str | Iterable[str]) -> bool:
    parts = contentful_parts(sentence)
    if not parts:
        return False
    evidence_texts = _evidence_texts(evidence)
    hits = sum(1 for part in parts
               if any(part in source for source in evidence_texts))
    return hits >= max(1, (len(parts) + 1) // 2)


def _bigram_coverage(sentence: str, evidence: str | Iterable[str]) -> float:
    normalized = _normalize(sentence)
    if len(normalized) < 2:
        return 0.0
    claim_bigrams = Counter(normalized[index:index + 2]
                            for index in range(len(normalized) - 1))
    evidence_bigrams = Counter()
    for source in _evidence_texts(evidence):
        normalized_source = _normalize(source)
        evidence_bigrams.update(normalized_source[index:index + 2]
                                for index in range(len(normalized_source) - 1))
    matched = sum(min(count, evidence_bigrams[bigram])
                  for bigram, count in claim_bigrams.items())
    return matched / sum(claim_bigrams.values())


def _soft_grounded(sentence: str, evidence: str | Iterable[str]) -> bool:
    normalized = _normalize(sentence)
    if len(normalized) < 4:
        return False
    coverage = _bigram_coverage(sentence, evidence)
    if coverage < 0.55:
        return False
    evidence_texts = [_normalize(source) for source in _evidence_texts(evidence)]
    key_parts = [part for part in contentful_parts(sentence)
                 if len(_normalize(part)) >= 2]
    if not key_parts:
        return any(normalized in source for source in evidence_texts)
    return any(
        bigram in source
        for part in key_parts
        for normalized_part in [_normalize(part)]
        for bigram in (normalized_part[index:index + 2]
                       for index in range(len(normalized_part) - 1))
        for source in evidence_texts
    )


def grounded(sentence: str, evidence: str | Iterable[str]) -> bool:
    """Grounding with conflict checks on every accepting path."""
    if not MARKER.sub("", sentence or "").strip():
        return False
    if _conflicts(sentence, evidence):
        return False
    return (_strict_grounded(sentence, evidence)
            or _soft_grounded(sentence, evidence))


def citation_supported(answer: str, marker_index: int, claim: str,
                       evidence: str | Iterable[str]) -> bool:
    local_clause, claim_body_local = citation_claims(answer, marker_index, claim)
    full_claim = MARKER.sub("", claim or "").strip(" \t\r\n，、。；;！？.!?")
    attr = attributed_clause(answer, marker_index)
    marker_count = len(list(MARKER.finditer(answer)))
    if marker_count <= 1:
        complete_claims = [full_claim, claim_body_local, local_clause,
                           sentence_around(answer, marker_index)]
        seen_claims: set[str] = set()
        for complete_claim in complete_claims:
            body = MARKER.sub("", complete_claim or "").strip()
            if body and body not in seen_claims:
                seen_claims.add(body)
                if _conflicts(body, evidence):
                    return False
    candidates: list[str] = []
    if attr:
        # Parallel citations: only the attributed clause is safe. Never OR a
        # collector compound claim that mixes sibling facts.
        candidates.append(attr)
    else:
        candidates.extend([claim_body_local, local_clause])
        if full_claim:
            candidates.append(full_claim)
        if marker_count <= 1:
            candidates.append(sentence_around(answer, marker_index))
            if not full_claim and not claim_body_local:
                candidates.append(MARKER.sub("", answer))
    for candidate in candidates:
        body = MARKER.sub("", candidate or "").strip()
        if body and grounded(candidate, evidence):
            return True
    return False


def reference_hit_stats(reference_answer: str, answer: str) -> tuple[int, int]:
    ref_parts = contentful_parts(reference_answer)
    normalized_answer = _normalize(answer)
    hits = sum(1 for part in ref_parts
               if _normalize(part) and _normalize(part) in normalized_answer)
    return hits, len(ref_parts)


def support_judgement(answer: str, citation_judgements: Iterable[bool],
                      reference_answer: str,
                      cited_evidence: str | Iterable[str]) -> str:
    """Whole-answer support from evidence/reference; cite booleans ignored."""
    judgements = list(citation_judgements)
    if len(judgements) == 0:
        return "unsupported"

    answer_body = MARKER.sub("", answer)
    sources = list(_evidence_texts(cited_evidence))
    ref = (reference_answer or "").strip()
    check_sources = sources + ([ref] if ref else [])
    parts = contentful_parts(answer_body)
    if not parts:
        return "unsupported"
    # Reject injected clauses that conflict or have near-zero overlap.
    for part in parts:
        if not grounded(part, check_sources):
            return "unsupported"
    if grounded(answer_body, cited_evidence):
        return "supported"
    ref_hit, ref_total = reference_hit_stats(ref, answer)
    if ref_total > 0 and ref_hit >= max(1, (ref_total + 1) // 2):
        return "supported"
    return "unsupported"
