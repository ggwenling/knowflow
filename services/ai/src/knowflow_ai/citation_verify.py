"""Small deterministic grounding checks for generated citation claims.

This is intentionally a conservative string heuristic, not a general natural
language entailment checker. It uses only the source text cited by each claim.
"""
import re
import unicodedata
from collections import Counter


_MARKER = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9._:-]{0,127})\]", re.ASCII)
_BOUNDARIES = frozenset("。！？.!?；;\n")
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


def _is_boundary(answer, position, in_marker):
    char = answer[position]
    if char not in _BOUNDARIES:
        return False
    if in_marker:
        return False
    # A decimal point belongs to the number, not the surrounding sentence.
    if (char == "." and position > 0 and position + 1 < len(answer)
            and answer[position - 1].isdigit() and answer[position + 1].isdigit()):
        return False
    return True


def _claim_units(answer):
    """Return (unmarked claim text, markers) for sentence/semicolon/newline units."""
    markers = list(_MARKER.finditer(answer))
    spans = [(marker.start(), marker.end()) for marker in markers]
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
            if not _is_boundary(answer, position, in_marker):
                continue
        end = position
        unit_markers = []
        while marker_index < len(markers) and markers[marker_index].start() < end:
            if markers[marker_index].start() >= start:
                unit_markers.append(markers[marker_index])
            marker_index += 1
        raw = answer[start:end]
        claim = _MARKER.sub("", raw).strip()
        if claim or unit_markers:
            units.append((claim, unit_markers))
        start = position + 1

    return units


def _evidence_units(evidence):
    """Keep negation and numeric checks local to likely supporting text."""
    markers = list(_MARKER.finditer(evidence))
    spans = [(marker.start(), marker.end()) for marker in markers]
    units = []
    start = 0
    span_index = 0
    for position in range(len(evidence)):
        while span_index < len(spans) and spans[span_index][1] <= position:
            span_index += 1
        in_marker = (span_index < len(spans)
                     and spans[span_index][0] <= position < spans[span_index][1])
        if _is_boundary(evidence, position, in_marker):
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


def citations_are_grounded(answer, evidence_by_id):
    """Check every complete cited claim against each source attached to it.

    Every non-empty claim unit must have at least one citation. For a unit with
    parallel markers, every cited source is independently checked against the
    full claim unit.
    """
    units = _claim_units(answer)
    if not units:
        return False
    for claim, markers in units:
        if not claim or not markers:
            return False
        for marker in markers:
            evidence = evidence_by_id.get(marker.group(1))
            if not isinstance(evidence, str) or not _grounded(claim, evidence):
                return False
    return True
