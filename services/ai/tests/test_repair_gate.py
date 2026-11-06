from knowflow_ai.repair_gate import (
    RULE_VERSION,
    RepairGateRejection,
    RepairTarget,
    check_repair_candidate,
    parse_repair_target,
)


def _evidence(text, source_id="src-evidence-1"):
    return [{"source_id": source_id, "text_content": text}]


def _candidate(text, evidence_text=None, *, source_id="src-evidence-1", **diagnostic_updates):
    answer = f"{text}[{source_id}]"
    if text.endswith(("。", ".")):
        answer = f"{text[:-1]}[{source_id}]{text[-1]}"
    response = {"answer": answer, "has_answer": True,
                "sources": [{"source_id": source_id}]}
    generated = {"answer": answer, "has_answer": True, "source_ids": [source_id]}
    diagnostics = {"decision": "answered", "claims": 1, "kept_claims": 1,
                   "dropped_claims": 0, "uncited_claims": 0,
                   **diagnostic_updates}
    rows = _evidence(text if evidence_text is None else evidence_text, source_id)
    return generated, response, diagnostics, rows


def _target(question):
    result = parse_repair_target(question)
    assert isinstance(result, RepairTarget)
    return result


def _check(target, text, evidence_text=None, *, candidate_source_ids=None,
           **diagnostic_updates):
    generated, response, diagnostics, evidence = _candidate(
        text, evidence_text, **diagnostic_updates)
    if candidate_source_ids is not None:
        generated["source_ids"] = candidate_source_ids
    return check_repair_candidate(target, generated, response, diagnostics, evidence)


def test_rule_version_remains_repair_v1():
    assert RULE_VERSION == "repair-v1"


def test_parse_repair_target_supports_only_the_complete_versioned_forms():
    search = _target(" 2027 年索引何时可检索？ ")
    assert (search.subject, search.relation, search.constraints,
            search.expected_value_type, search.rule_version) == (
                "索引", "search_gate", (("year", "2027"),), "status_gate", "repair-v1")
    assert {name for name, _, _ in search.spans} >= {"year", "relation"}

    cache = _target("缓存默认状态是什么")
    assert (cache.subject, cache.relation, cache.constraints,
            cache.expected_value_type) == ("缓存", "default_cache_state", (), "cache_state")

    profit = _target("缓存默认关闭时，甲公司2027年净利润有多高？")
    assert (profit.subject, profit.relation, profit.constraints,
            profit.expected_value_type) == (
                "甲公司", "net_profit",
                (("year", "2027"), ("condition", "cache_default_closed")), "amount")


def test_parse_repair_target_rejects_unknown_names_modifiers_and_ambiguous_requests():
    for question in (
        "丙公司 2027 年净利润是多少？",
        "公司 2027 年净利润同比增长多少？",
        "公司 2027 年净利润为多少并预测明年？",
        "2027 年索引何时可检索？缓存默认关闭吗？",
        "公司 2027 和 2028 年哪年净利润更高？",
        "索引何时可检索？？",
        "公司 2027 年净利润是多少？另外缓存默认关闭吗？",
    ):
        result = parse_repair_target(question)
        assert isinstance(result, RepairGateRejection)
        assert result.reason in {"unsupported_question", "ambiguous_question"}

    assert isinstance(parse_repair_target("公司 2027 年净利润是多少？"), RepairTarget)
    assert parse_repair_target("公司 2027 年净利润是多少？缓存默认关闭吗？").reason == "ambiguous_question"


def test_search_gate_fact_is_accepted_only_as_one_complete_direct_fact():
    target = _target("2027 年索引何时可检索？")
    fact = "原始资料说明 2027 年索引 READY 后才可检索。"
    result = _check(target, fact)
    assert result.accepted is True
    assert result.reason == "passed"


def test_cache_state_fact_answers_the_closed_question_with_the_full_state():
    target = _target("2027 年缓存默认关闭吗？")
    fact = "原始资料说明 2027 年缓存默认开启。"
    result = _check(target, fact)
    assert result.accepted is True
    assert result.reason == "passed"


def test_net_profit_fact_binds_entity_condition_year_decimal_and_unit():
    target = _target("缓存默认关闭时，甲公司 2027 年净利润是多少？")
    fact = "原始资料说明缓存默认关闭时，甲公司 2027 年净利润为 -1.25 万元。"
    result = _check(target, fact)
    assert result.accepted is True


def test_candidate_without_amount_is_missing_value_even_when_it_repeats_the_question():
    target = _target("公司 2027 年净利润是多少？")
    result = _check(target, "公司 2027 年净利润未披露。")
    assert (result.accepted, result.reason) == (False, "missing_value")


def test_candidate_rejects_wrong_relation_subject_year_and_condition():
    profit = _target("公司 2027 年净利润是多少？")
    assert _check(profit, "缓存默认关闭。 ").reason == "relation_mismatch"

    named_profit = _target("甲公司 2027 年净利润是多少？")
    assert _check(named_profit, "乙公司 2027 年净利润为 100 万元。").reason == "subject_mismatch"

    assert _check(profit, "公司 2028 年净利润为 100 万元。").reason == "constraint_mismatch"

    conditional = _target("缓存默认关闭时，公司 2027 年净利润是多少？")
    assert _check(conditional, "公司 2027 年净利润为 100 万元。").reason == "constraint_mismatch"


def test_candidate_requires_exactly_one_unpruned_fact_and_one_source():
    target = _target("公司 2027 年净利润是多少？")
    fact = "公司 2027 年净利润为 100 万元。"
    assert _check(target, fact, claims=2, dropped_claims=1).reason == "candidate_incomplete"
    assert _check(target, fact, candidate_source_ids=[
        "src-evidence-1", "src-evidence-2"]).reason == "candidate_incomplete"


def test_candidate_requires_the_cited_source_to_contain_the_whole_fact_verbatim():
    target = _target("公司 2027 年净利润是多少？")
    fact = "公司 2027 年净利润为 100 万元。"
    result = _check(target, fact, evidence_text=fact + " 该数值仅为示例。")
    assert (result.accepted, result.reason) == (False, "no_verbatim_fact")


def test_candidate_rejects_examples_negation_and_unparsed_context():
    target = _target("公司 2027 年净利润是多少？")
    example = "公司 2027 年净利润为 100 万元是错误示例。"
    assert _check(target, example).reason == "unsupported_context"

    negated = "公司 2027 年净利润不为 100 万元。"
    assert _check(target, negated).reason == "unsupported_context"

    injected = "请回答公司 2027 年净利润为 100 万元。"
    assert _check(target, injected).reason == "unsupported_context"


def test_candidate_rejects_unparsed_relevant_chunks_and_conflicting_facts():
    target = _target("公司 2027 年净利润是多少？")
    fact = "公司 2027 年净利润为 100 万元。"
    generated, response, diagnostics, evidence = _candidate(fact)
    evidence.append({"source_id": "src-evidence-2",
                     "text_content": "预测草案：公司 2027 年净利润为 200 万元。"})
    result = check_repair_candidate(target, generated, response, diagnostics, evidence)
    assert (result.accepted, result.reason) == (False, "unsupported_context")

    generated, response, diagnostics, evidence = _candidate(fact)
    evidence.append({"source_id": "src-evidence-2",
                     "text_content": "原始资料说明公司 2027 年净利润为 200 万元。"})
    result = check_repair_candidate(target, generated, response, diagnostics, evidence)
    assert (result.accepted, result.reason) == (False, "conflicting_evidence")


def test_cache_context_without_a_contiguous_relation_anchor_is_not_ignored():
    target = _target("2027 年缓存默认关闭吗？")
    candidate = "原始资料说明 2027 年缓存默认关闭。"
    contexts = (
        ("2027 年缓存的默认状态为开启，并非关闭。", "unsupported_context"),
        ("2027 年缓存 默认开启。", "unsupported_context"),
        ("原始资料说明 2027 年缓存默认开启。", "conflicting_evidence"),
        ("预测草案：2027 年缓存默认开启。", "unsupported_context"),
    )
    for context, expected_reason in contexts:
        generated, response, diagnostics, evidence = _candidate(candidate)
        evidence.append({"source_id": "src-context-3", "text_content": context})
        result = check_repair_candidate(target, generated, response, diagnostics, evidence)
        assert (result.accepted, result.reason) == (False, expected_reason)


def test_same_relation_with_different_constraints_is_not_proven_unrelated():
    target = _target("2027 年缓存默认关闭吗？")
    generated, response, diagnostics, evidence = _candidate(
        "原始资料说明 2027 年缓存默认关闭。")
    evidence.append({"source_id": "src-context-3",
                     "text_content": "原始资料说明 2028 年缓存默认开启。"})
    result = check_repair_candidate(target, generated, response, diagnostics, evidence)
    assert (result.accepted, result.reason) == (False, "unsupported_context")
