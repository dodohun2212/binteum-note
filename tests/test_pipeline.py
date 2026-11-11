"""가짜 AI로 전체 흐름을 한 번 돈다 (T-17)."""
import pytest

from core import diagnose, explain, export, llm, note, priority

MODE = "섞어서"


@pytest.fixture(scope="module")
def flow(analysis, material):
    """분석 결과 → 문제 → 예시 답 → 채점 → 우선순위 → 설명 → 요약 노트 → 파일 두 개."""
    concepts = {c["id"]: c for c in analysis["concepts"]}
    meta = analysis["meta_pages"]
    scores = analysis["scores"]["scores"]
    pct = {r["concept_id"]: r["pct"] for r in scores}
    targets = diagnose.diag_targets(scores)
    names = [concepts[cid]["name"] for cid in targets]

    kinds = {cid: diagnose.question_kind(pct[cid], MODE) for cid in targets}
    questions = {cid: diagnose.make_question(concepts[cid], kinds[cid], material, meta, names)
                 for cid in targets}

    given = diagnose.example_answers(questions)
    confusion = {cid: a["confusion"] for cid, a in given.items() if a.get("confusion")}
    grading = {}
    for cid, q in questions.items():
        a = given[cid]
        g = diagnose.grade_without_ai(q, a["answer"], a["dont_know"], a["choice"], a["guessed"])
        if g is None:
            g = diagnose.grade_essay(concepts[cid], q, a["answer"], material, meta)
        grading[cid] = g

    prios = priority.compute_priorities(scores, grading)
    prio_by = {p["concept_id"]: p for p in prios}
    explain_ids = priority.auto_explain_ids(prios, confusion)
    explanations = {
        cid: explain.make_explanation(concepts[cid], prio_by[cid]["status"], questions.get(cid), grading.get(cid),
                                      given.get(cid), confusion.get(cid, ""), material, meta)
        for cid in explain_ids
    }
    notes = {cid: note.make_note(c, prio_by[cid], grading.get(cid), analysis["utterances"], material, meta)
             for cid, c in concepts.items()}

    state = {
        "material_name": material["name"], "has_transcript": True,
        "concepts": analysis["concepts"], "meta_pages": meta, "utterances": analysis["utterances"],
        "scores": scores, "priorities": prios, "questions": questions, "given": given,
        "confusion": confusion, "grading": grading, "explanations": explanations, "notes": notes,
    }
    return {"state": state, "targets": targets, "kinds": kinds, "pct": pct, "names": names,
            "explain_ids": explain_ids, "study": export.study_html(state), "notes": export.notes_html(state)}


def test_targets_are_20_or_more(flow, analysis):
    pct = flow["pct"]
    assert len(flow["targets"]) >= 1
    assert all(pct[cid] >= 20 for cid in flow["targets"])
    left_out = [r["concept_id"] for r in analysis["scores"]["scores"] if r["concept_id"] not in flow["targets"]]
    assert all(pct[cid] < 20 for cid in left_out)


def test_question_kinds_follow_mixed_rule(flow):
    questions = flow["state"]["questions"]
    assert list(questions) == flow["targets"]
    for cid, q in questions.items():
        expected = "서술형" if flow["pct"][cid] >= 50 else "객관식"
        assert q["kind"] == expected, cid
    kinds = {q["kind"] for q in questions.values()}
    assert kinds == {"서술형", "객관식"}


def test_all_answered_and_graded(flow):
    state = flow["state"]
    for cid, q in state["questions"].items():
        a = state["given"][cid]
        assert diagnose.is_answered(q, a["answer"], a["dont_know"], a["choice"]) is True
    assert set(state["grading"]) == set(flow["targets"])
    statuses = {g["status"] for g in state["grading"].values()}
    assert statuses == {"앎", "헷갈림", "모름"}


def test_explanations_cover_every_wrong_concept(flow):
    state = flow["state"]
    wrong = [cid for cid, g in state["grading"].items() if g["status"] in ("모름", "헷갈림")]
    assert len(wrong) >= 2
    for cid in wrong:
        assert cid in state["explanations"]
        assert state["explanations"][cid]["explanation"].strip() != ""
    # 헷갈린 점을 적은 개념은 그에 대한 답이 생긴다
    assert len(state["confusion"]) >= 1
    for cid in state["confusion"]:
        assert state["explanations"][cid]["confusion_reply"]


def test_notes_for_every_concept(flow, analysis):
    notes = flow["state"]["notes"]
    assert set(notes) == {c["id"] for c in analysis["concepts"]}
    details = {n["detail"] for n in notes.values()}
    assert "자세히" in details
    assert "짧게" in details
    for n in notes.values():
        assert n["from_ai"] is (n["detail"] != "짧게")


def test_two_files(flow, analysis):
    study, notes = flow["study"], flow["notes"]
    for doc in (study, notes):
        assert doc.startswith("<!doctype html>")
        assert "image/jpeg" not in doc
    assert "시험 대비 요약 노트" in notes
    assert "시험 대비 요약 노트" not in study
    assert "공부 순서·오답노트" in study
    assert len(analysis["concepts"]) == 13
    assert notes.count('class="bn-card"') == 13
    for status in ("앎", "헷갈림", "모름"):
        assert f">{status}</span>" in study


def test_study_file_has_one_card_per_graded_concept(flow):
    assert flow["study"].count('class="bn-card"') == len(flow["targets"])


def test_run_many_makes_same_number_of_questions(flow, analysis, material):
    concepts = {c["id"]: c for c in analysis["concepts"]}
    meta = analysis["meta_pages"]

    def job(cid):
        return lambda usage: diagnose.make_question(concepts[cid], flow["kinds"][cid], material, meta,
                                                    flow["names"], usage=usage)

    results, errors, usage = llm.run_many({cid: job(cid) for cid in flow["targets"]}, workers=6)
    assert errors == {}
    assert len(results) == len(flow["targets"])
    assert list(results) == flow["targets"]
    assert usage.calls == len(flow["targets"])
    for cid, q in results.items():
        assert q["kind"] == flow["kinds"][cid]
        assert q["question"] == flow["state"]["questions"][cid]["question"]
