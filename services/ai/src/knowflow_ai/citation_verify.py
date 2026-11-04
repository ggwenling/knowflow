"""Small deterministic grounding checks for generated citation claims.

This is intentionally a conservative string heuristic, not a general natural
language entailment checker. It uses only the source text cited by each claim.
"""
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass


_MARKER = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9._:-]{0,127})\]", re.ASCII)
_BOUNDARIES = frozenset("。！？.!?；;\n")
_URL = re.compile(r"https?://[^\s<>\[\]{}]+", re.IGNORECASE)
_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@"
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*(?![A-Za-z0-9-])",
    re.ASCII,
)
_URL_TRAILING_PUNCTUATION = ".,!?;:。！？；，、)]}"
_NUMBER = re.compile(r"(?<![A-Za-z0-9_])\d+(?:\.\d+)?%?(?![A-Za-z0-9_])", re.ASCII)
_NEGATION = re.compile(
    r"并非|不是|没有|不曾|不再|不能|不可|不得|不应|禁止|否认|否定|未能|未曾|"
    r"尚未|还未|从未|无法|不(?!但|仅|只|光|妨)|没|未|无(?!论|限|穷|数)|非(?!常|凡)|"
    r"\b(?:not|no|never|without|cannot|can't|isn't|aren't|wasn't|weren't|"
    r"doesn't|don't|didn't|won't|shouldn't|mustn't|neither|nor)\b",
    re.IGNORECASE,
)


def _normalized(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def _protected_periods(text):
    """Return periods inside URLs or email addresses, excluding URL punctuation."""
    spans = []
    for match in _URL.finditer(text):
        end = match.end()
        while end > match.start() and text[end - 1] in _URL_TRAILING_PUNCTUATION:
            end -= 1
        spans.append((match.start(), end))
    spans.extend((match.start(), match.end()) for match in _EMAIL.finditer(text))
    return {position for start, end in spans
            for position in range(start, end) if text[position] == "."}


def _is_boundary(answer, position, in_marker, protected_periods):
    char = answer[position]
    if char not in _BOUNDARIES:
        return False
    if in_marker:
        return False
    if char == "." and position in protected_periods:
        return False
    # A decimal point belongs to the number, not the surrounding sentence.
    if (char == "." and position > 0 and position + 1 < len(answer)
            and answer[position - 1].isdigit() and answer[position + 1].isdigit()):
        return False
    return True


def _claim_units(answer):
    """Return (unmarked claim text, markers) for sentence/semicolon/newline units."""
    return [(unit.claim, list(unit.markers)) for unit in _claim_segments(answer)
            if unit.claim or unit.markers]


@dataclass(frozen=True)
class _ClaimSegment:
    start: int
    end: int
    boundary: str | None
    claim: str
    markers: tuple


def _claim_segments(answer):
    """Split an answer while retaining the source spans needed for pruning."""
    markers = list(_MARKER.finditer(answer))
    spans = [(marker.start(), marker.end()) for marker in markers]
    protected_periods = _protected_periods(answer)
    units = []
    start = 0
    marker_index = 0
    span_index = 0

    for position in range(len(answer) + 1):
        at_end = position == len(answer)
        in_marker = False
        if not at_end:
            while span_index < len(spans) and spans[span_index][1] <= position:
                span_index += 1
            in_marker = (span_index < len(spans)
                         and spans[span_index][0] <= position < spans[span_index][1])
            if not _is_boundary(answer, position, in_marker, protected_periods):
                continue
        end = position
        unit_markers = []
        while marker_index < len(markers) and markers[marker_index].start() < end:
            if markers[marker_index].start() >= start:
                unit_markers.append(markers[marker_index])
            marker_index += 1
        raw = answer[start:end]
        claim = _MARKER.sub("", raw).strip()
        boundary = None if at_end else answer[position]
        units.append(_ClaimSegment(start, end, boundary, claim, tuple(unit_markers)))
        start = position + 1

    return units


def _evidence_units(evidence):
    """Keep negation and numeric checks local to likely supporting text."""
    markers = list(_MARKER.finditer(evidence))
    spans = [(marker.start(), marker.end()) for marker in markers]
    protected_periods = _protected_periods(evidence)
    units = []
    start = 0
    span_index = 0
    for position in range(len(evidence)):
        while span_index < len(spans) and spans[span_index][1] <= position:
            span_index += 1
        in_marker = (span_index < len(spans)
                     and spans[span_index][0] <= position < spans[span_index][1])
        if _is_boundary(evidence, position, in_marker, protected_periods):
            unit = _normalized(evidence[start:position])
            if unit:
                units.append(unit)
            start = position + 1
    final = _normalized(evidence[start:])
    if final:
        units.append(final)
    return units


def _bigrams(text):
    return Counter(zip(text, text[1:]))


def _numeric_conflict(claim, evidence):
    claim_numbers = set(_NUMBER.findall(claim))
    return bool(claim_numbers - set(_NUMBER.findall(evidence)))


def _negation_conflict(claim, evidence):
    return bool(_NEGATION.search(claim)) != bool(_NEGATION.search(evidence))


def _bigram_coverage(claim_bigrams, evidence):
    claim_size = sum(claim_bigrams.values())
    if not claim_size:
        return 0
    evidence_bigrams = _bigrams(evidence)
    matched = sum(min(count, evidence_bigrams[bigram])
                  for bigram, count in claim_bigrams.items())
    return matched / claim_size


def _grounded(claim, evidence):
    claim = _normalized(claim)
    if not claim:
        return False
    claim_bigrams = _bigrams(claim)
    normalized_evidence = _normalized(evidence)
    if _numeric_conflict(claim, normalized_evidence):
        return False

    # Match against the complete retrieved chunk first. Splitting the chunk
    # can lose overlap when a paraphrase draws on adjacent sentences.
    comparison_texts = [normalized_evidence, *_evidence_units(evidence)]
    for comparison_text in comparison_texts:
        coverage = _bigram_coverage(claim_bigrams, comparison_text)
        if coverage >= 0.55 and _negation_conflict(claim, comparison_text):
            continue
        if claim in comparison_text:
            return True
        if coverage >= 0.55:
            return True
    return False


def prune_ungrounded_claims(answer, evidence_by_id):
    """Remove unsupported claim units and return the citations that remain.

    Marker-only units attach to the preceding claim, matching the collector's
    backward attachment rule. A stack is pruned marker by marker using strict
    full-claim substring coverage; a single marker keeps the existing
    non-empty-source policy.
    """
    segments = _claim_segments(answer)
    claims = []
    previous_claim = None
    for segment in segments:
        if segment.claim:
            claim = {"text": segment.claim, "markers": list(segment.markers),
                     "segments": [segment]}
            claims.append(claim)
            previous_claim = claim
        elif segment.markers and previous_claim is not None:
            previous_claim["markers"].extend(segment.markers)
            previous_claim["segments"].append(segment)

    kept_claims = []
    for claim in claims:
        markers = claim["markers"]
        normalized_claim = _normalized(claim["text"])
        if not markers or not normalized_claim:
            continue
        if len(markers) > 1:
            supported = []
            for marker in markers:
                evidence = evidence_by_id.get(marker.group(1))
                if (isinstance(evidence, str)
                        and normalized_claim in _normalized(evidence)):
                    supported.append(marker)
        else:
            marker = markers[0]
            evidence = evidence_by_id.get(marker.group(1))
            supported = ([marker] if isinstance(evidence, str)
                         and _normalized(evidence) else [])
        if supported:
            kept_claims.append((claim, supported))

    answer_parts = []
    for claim, supported in kept_claims:
        supported_spans = {(marker.start(), marker.end()) for marker in supported}
        chunks = []
        for segment in claim["segments"]:
            cursor = segment.start
            piece = []
            for marker in segment.markers:
                if (marker.start(), marker.end()) not in supported_spans:
                    piece.append(answer[cursor:marker.start()])
                    cursor = marker.end()
                else:
                    piece.append(answer[cursor:marker.end()])
                    cursor = marker.end()
            piece.append(answer[cursor:segment.end])
            if segment.boundary:
                piece.append(segment.boundary)
            chunks.append("".join(piece))
        readable = _normalized("".join(chunks))
        readable = re.sub(r"\s+([。！？.!?；;，,、])", r"\1", readable)
        if readable:
            answer_parts.append(readable)

    pruned_answer = " ".join(answer_parts).strip().rstrip(" ;；,，、").rstrip()
    # Derive IDs from actual retained markers in answer order, including the
    # unusual marker-only suffix form handled by _claim_segments.
    kept_source_ids = []
    seen_source_ids = set()
    for marker in _MARKER.finditer(pruned_answer):
        source_id = marker.group(1)
        if source_id not in seen_source_ids:
            seen_source_ids.add(source_id)
            kept_source_ids.append(source_id)
    return {"pruned_answer": pruned_answer,
            "kept_source_ids": kept_source_ids,
            "ok": bool(kept_source_ids)}


def citations_are_grounded(answer, evidence_by_id):
    """Compatibility boolean wrapper around the structured pruning result."""
    return prune_ungrounded_claims(answer, evidence_by_id)["ok"]
