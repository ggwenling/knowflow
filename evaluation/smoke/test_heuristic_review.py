from evaluation.collector.prediction import _claim
from evaluation.runner.heuristic_review import (
    MARKER,
    _bigram_coverage,
    attributed_clause,
    citation_supported,
    grounded,
    support_judgement,
)


def test_parallel_citations_attribute_leading_clauses_in_order():
    answer = "仓库每日清晨开门，访客必须提前预约。[src-a][src-b]"
    assert attributed_clause(answer, 0) == "仓库每日清晨开门"
    assert attributed_clause(answer, 1) == "访客必须提前预约"
    evidence_a = "仓库每日清晨开门。"
    evidence_b = "访客必须提前预约。"
    claim = "[src-a][src-b]"
    assert citation_supported(answer, 0, claim, evidence_a)
    assert citation_supported(answer, 1, claim, evidence_b)
    assert not citation_supported(answer, 0, claim, evidence_b)


def test_parallel_citations_before_period_do_not_use_compound_claim():
    answer = "仓库每日清晨开门，访客必须提前预约[src-a][src-b]。"
    marker = list(MARKER.finditer(answer))[0]
    claim = _claim(answer, marker.start(), marker.end())
    assert "仓库每日清晨开门" in claim and "访客必须提前预约" in claim
    assert attributed_clause(answer, 0) == "仓库每日清晨开门"
    assert not citation_supported(answer, 0, claim, "访客必须提前预约。")
    assert citation_supported(answer, 0, claim, "仓库每日清晨开门。")


def test_bigram_fallback_accepts_a_supported_paraphrase():
    claim = "申请人需提交有效身份证明原件"
    evidence = "申请人应当提供有效的身份证明原件。"
    assert _bigram_coverage(claim, evidence) >= 0.55
    assert grounded(claim, evidence)


def test_conflict_checks_cover_strict_and_soft_paths():
    assert not grounded("申请人年龄必须达到18周岁", "申请人年龄必须达到180周岁。")
    assert not grounded("申请人必须提交有效身份证明原件",
                        "申请人无需提交有效身份证明原件。")
    assert not grounded("电子档案可以直接删除", "电子档案不可以直接删除。")
    assert not grounded("档案保管期限为五年", "档案保管期限为十年。")
    assert not grounded("档案保管期限为80年，电子文件应当备份",
                        "档案保管期限为18年，电子文件应当备份。")
    assert not citation_supported(
        "申请人年龄必须达到18周岁[s]", 0,
        "申请人年龄必须达到18周岁[s]",
        "申请人年龄必须达到180周岁。")


def test_numbers_stay_with_their_best_matching_evidence_clause():
    claim = "纸质档案保管期为80年"
    evidence = "纸质档案保管期为18年。电子档案保管期为80年。"
    assert not grounded(claim, evidence)
    assert not citation_supported(f"{claim}[a]", 0, f"{claim}[a]", evidence)
    assert not grounded("档案保管期限为18年", "档案保管期限为18.5年。")
    assert grounded("档案保管期限为十八年", "档案保管期限为18年。")


def test_negation_is_checked_on_the_matching_clause():
    assert not grounded("电子档案不得直接删除",
                        "电子档案可以直接删除但不得备份。")
    assert grounded("申请人必须提交有效身份证明原件",
                    "申请人必须提交有效身份证明原件。无需提交复印件。")


def test_single_citation_checks_full_compound_claim_for_conflicts():
    answer = "档案保管期限为80年，电子文件应当备份[a]"
    evidence = "档案保管期限为18年，电子文件应当备份。"
    assert not citation_supported(answer, 0, answer, evidence)
    assert not citation_supported(answer, 0, "[a]", evidence)


def test_support_uses_union_evidence_even_when_all_local_cites_fail():
    answer = "档案保管期为五年。"
    cited = ["档案保管期为五年。"]
    assert support_judgement(answer, [False, False], "档案保管期为五年。", cited) == "supported"


def test_support_rejects_conflicting_or_short_extra_claims():
    reference = "档案保管期为五年。"
    assert support_judgement(
        "档案保管期为五年。[a]电子档案保管期为80年。",
        [True], reference,
        ["档案保管期为五年。电子档案保管期为18年。"],
    ) == "unsupported"
    assert support_judgement(
        "档案保管期为五年。[a]电子档案保管期为80年。",
        [False], reference,
        ["电子档案保管期为18年。"],
    ) == "unsupported"
    assert support_judgement(
        "档案保管期为五年。[a]月球是玻璃。",
        [True], reference, ["档案保管期为五年。"],
    ) == "unsupported"
    assert support_judgement(
        "档案保管期为五年。[a]档案保管地点位于月球。",
        [True], reference, ["档案保管期为五年。"],
    ) == "unsupported"
    assert support_judgement(
        "档案保管期为五年。[a]可出售。",
        [True], reference, ["档案保管期为五年。"],
    ) == "unsupported"
    assert support_judgement(
        "档案保管期为五年。[a]免费。",
        [True], reference, ["档案保管期为五年。"],
    ) == "unsupported"
    assert support_judgement(
        "电子档案保管期为80年。", [False],
        "纸质档案保管期为80年。", ["电子档案保管期为18年。"],
    ) == "unsupported"


def test_support_requires_evidence_for_each_parallel_sentence():
    answer = "档案保管期为五年。档案保管地点位于一号库。"
    evidence = ["档案保管期为五年。", "档案保管地点位于一号库。"]
    assert support_judgement(answer, [False, False], answer, evidence) == "supported"
