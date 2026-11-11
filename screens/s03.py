"""S03 내 취약점 진단: 문제 카드, 답 입력, 채점, 결과."""
import streamlit as st

import config
from core import diagnose, figure, llm, priority
from core.diagnose import MCQ, is_answered
from core.export import review_html
from core.html import badge, esc, mark, status_badge
from screens import common, s02, s04

ANSWER_HINT = "아는 만큼 2~3문장으로 적어 주세요."
GRADE_HINT = "모든 문제에 답해야 채점해요. 모르면 '모르겠어요'를 고르면 돼요."
MISSING_NOTE = "아직 답하지 않았어요. 모르면 '모르겠어요'를 골라 주세요."
CONFUSION_PLACEHOLDER = "②와 ③ 중에 고민했어요. 두 방법이 어떻게 다른지 모르겠어요."
MCQ_OPTIONS = [0, 1, 2, 3, -1]


def _live(cid: str, q: dict) -> dict:
    """입력칸 위젯의 지금 값(아직 안 그려졌으면 세션 딕셔너리)."""
    ss = st.session_state
    given = common.given_of(cid)
    if q["kind"] == MCQ:
        given["choice"] = ss.get("mcq_" + cid, given["choice"])
        given["guessed"] = bool(ss.get("guess_" + cid, given["guessed"]))
    else:
        given["answer"] = ss.get("ans_" + cid, given["answer"])
        given["dont_know"] = bool(ss.get("dk_" + cid, given["dont_know"]))
    return given


def _answered(cid: str, q: dict) -> bool:
    given = _live(cid, q)
    return is_answered(q, given["answer"], given["dont_know"], given["choice"])


def fill_examples(questions: dict) -> None:
    """샘플 체험용 예시 답을 입력칸 세션 키와 세션 딕셔너리에 넣는다(입력칸이 그려지기 전에)."""
    ss = st.session_state
    for cid, given in diagnose.example_answers(questions).items():
        ss["answers"][cid], ss["dont_know"][cid] = given["answer"], given["dont_know"]
        ss["mcq_choice"][cid], ss["guessed"][cid] = given["choice"], given["guessed"]
        ss["confusion"][cid] = given["confusion"]
        if questions[cid]["kind"] == MCQ:
            ss["mcq_" + cid], ss["guess_" + cid], ss["conf_" + cid] = given["choice"], given["guessed"], given["confusion"]
        else:
            ss["ans_" + cid], ss["dk_" + cid] = given["answer"], given["dont_know"]


def grade(questions: dict, only=None) -> None:
    """한 번에 채점. 객관식·'모르겠어요'는 코드가, 답이 있는 서술형만 AI가 채점한다."""
    ss = st.session_state
    ss["stage_error"].pop("grading", None)
    cmap = common.concept_map()
    material, meta = ss["material"], ss["meta_pages"]
    jobs = {}
    for cid in only or list(questions):
        q, given = questions[cid], common.given_of(cid)
        done = diagnose.grade_without_ai(q, given["answer"], given["dont_know"], given["choice"], given["guessed"])
        if done is not None:
            ss["grading"][cid] = done
        else:
            jobs[cid] = (lambda usage, c=cmap[cid], q=q, a=given["answer"]:
                         diagnose.grade_essay(c, q, a, material, meta, usage))
    ss["grade_failed"], ss["grade_error"] = [], None
    if jobs:
        if material is None or common.ai_blocked("grading"):
            ss["grade_failed"] = list(jobs)
            return
        with st.spinner("서술형 답을 채점하는 중이에요. 보통 10~20초 걸려요."):
            results, errors = common.run_with_progress(jobs, "채점하는 중", 6, "채점")
        ss["grading"].update(results)
        ss["grade_failed"] = list(errors)
        if errors:
            exc = next(iter(errors.values()))
            ss["grade_error"] = llm.error_text(exc) + (f"{type(exc).__name__}: {exc}",)


def open_study() -> None:
    """우선순위를 계산하고 자동 보완 설명을 다 만든 뒤 ④로 넘어간다."""
    ss = st.session_state
    questions = common.current_questions()
    grading = {cid: g for cid, g in ss["grading"].items() if cid in questions}
    ss["priorities"] = priority.compute_priorities(ss["scores"], grading)
    s04.make_explanations(priority.auto_explain_ids(ss["priorities"], common.confusions()))
    common.goto(4)


def _input_card(n: int, cid: str, q: dict, pct: int) -> None:
    ss = st.session_state
    with st.container(border=True):
        st.html(f"<h4 style='margin:0'>Q{n}. {esc(common.concept_map()[cid]['name'])}</h4>"
                f"<p style='margin:2px 0'>{common.kind_badges(q, pct)}</p>"
                f'<div class="bn-q">{esc(q["question"])}</div>{figure.to_html(q.get("figure"))}')
        if q["kind"] == MCQ:
            key = "mcq_" + cid
            if key not in ss and ss["mcq_choice"].get(cid) is not None:
                ss[key] = ss["mcq_choice"][cid]
            choice = st.radio("보기", MCQ_OPTIONS, index=None, key=key, label_visibility="collapsed",
                              format_func=lambda i, q=q: common.MCQ_DONT_KNOW if i == -1 else f"{mark(i)} {q['choices'][i]}")
            ss["mcq_choice"][cid] = choice
            if isinstance(choice, int) and choice >= 0:
                gkey = "guess_" + cid
                if gkey not in ss:
                    ss[gkey] = bool(ss["guessed"].get(cid))
                guessed = st.checkbox("확신 없이 골랐어요 (찍었어요)", key=gkey)
                ss["guessed"][cid] = guessed
                if guessed:
                    ckey = "conf_" + cid
                    if ckey not in ss:
                        ss[ckey] = ss["confusion"].get(cid, "")
                    ss["confusion"][cid] = st.text_area(
                        "어떤 점이 헷갈렸나요? (선택)", key=ckey, max_chars=config.CONFUSION_MAX_CHARS,
                        height=80, placeholder=CONFUSION_PLACEHOLDER,
                        help="적으면 ④ 보완 설명이 이 질문에 바로 답해요. 비워 둬도 채점해요.")
            else:
                ss["guessed"][cid] = False
        else:
            akey, dkey = "ans_" + cid, "dk_" + cid
            if akey not in ss:
                ss[akey] = ss["answers"].get(cid, "")
            if dkey not in ss:
                ss[dkey] = bool(ss["dont_know"].get(cid))
            ss["answers"][cid] = st.text_area("내 답", key=akey, height=110, placeholder=ANSWER_HINT)
            ss["dont_know"][cid] = st.checkbox("모르겠어요", key=dkey)
        if ss["show_missing"] and not _answered(cid, q):
            st.html(f'<p class="bn-red">{MISSING_NOTE}</p>')
        if cid in ss["grade_failed"]:
            st.html('<p class="bn-red">이 문제는 채점하지 못했어요. 답은 그대로 있어요. 아래에서 다시 채점할 수 있어요.</p>')


def _result_card(n: int, cid: str, q: dict, pct: int) -> None:
    ss = st.session_state
    g = ss["grading"][cid]
    conf = common.confusion_of(cid)
    extra = f'<div class="bn-box bn-box-reply"><div class="bn-box-t">💬 내가 헷갈린 점</div><p>{esc(conf)}</p></div>' if conf else ""
    st.html(f'<div class="bn-card"><h4>Q{n}. {esc(common.concept_map()[cid]["name"])}</h4>'
            f"<p>{status_badge(g['status'])}{badge(str(g['score']) + '/10')}{common.kind_badges(q, pct)}</p>"
            f"{review_html(q, g, common.given_of(cid))}{extra}</div>")


def render() -> None:
    ss = st.session_state
    common.header(3)
    questions = common.current_questions()
    pct_by = {r["concept_id"]: r["pct"] for r in ss["scores"]}
    common.show_stage_error("questions")
    common.show_stage_error("grading")
    common.show_stage_error("explain")

    failed_q = [cid for cid in ss["diag_ids"] if cid not in questions]
    if failed_q:
        cmap = common.concept_map()
        names = ", ".join(cmap[cid]["name"] for cid in failed_q)
        err = ss["q_failed"].get((failed_q[0], common.wanted_kind(failed_q[0])))
        reason = f" {err[0]} ({err[1]})" if err else ""
        st.warning(f"문제를 만들지 못한 개념 {len(failed_q)}개는 진단에서 뺐어요: {names}.{reason}")
        if st.button("못 만든 문제 다시 만들기", key="w_retry_q", disabled=ss["material"] is None):
            s02.make_questions(ss["diag_ids"])
            st.rerun()
    if not questions:
        st.info("아직 진단 문제가 없어요. ②에서 '개념 진단하기'를 눌러 주세요.")
        if st.button("② 출제 포인트로", key="w_back2"):
            common.goto(2)
        return

    graded = [cid for cid in questions if cid in ss["grading"]]
    all_graded = len(graded) == len(questions)
    if all_graded:
        count = {s: sum(1 for cid in questions if ss["grading"][cid]["status"] == s) for s in ("앎", "헷갈림", "모름")}
        common.num_boxes([("앎", count["앎"], "ok"), ("헷갈림", count["헷갈림"], "warn"), ("모름", count["모름"], "bad")])
    n_mcq = sum(1 for q in questions.values() if q["kind"] == MCQ)
    answered = sum(1 for cid, q in questions.items() if cid in ss["grading"] or _answered(cid, q))
    st.progress(answered / len(questions),
                text=f"답한 문제 {answered} / {len(questions)} · 객관식 {n_mcq} · 서술형 {len(questions) - n_mcq}")

    if ss["from_sample"] and not graded and answered < len(questions):
        st.caption("샘플로 둘러보는 중이라면 '예시 답 채우기'로 바로 채점까지 가 볼 수 있어요.")
        if st.button("예시 답 채우기 (샘플 체험용)", key="w_fill", width="stretch"):
            fill_examples(questions)
            ss["show_missing"] = False
            st.rerun()

    if ss["grade_failed"]:
        err = ss["grade_error"] or ss["stage_error"].get("grading") or llm.error_text(llm.BadJSONError())
        st.error(f"서술형 {len(ss['grade_failed'])}문제를 채점하지 못했어요. {err[0]} ({err[1]})")
        if len(err) > 2 and err[2]:
            with st.expander("자세한 오류"):
                st.code(err[2])

    for n, (cid, q) in enumerate(questions.items(), 1):
        if cid in ss["grading"]:
            _result_card(n, cid, q, pct_by[cid])
        else:
            _input_card(n, cid, q, pct_by[cid])

    if not all_graded:
        missing = [f"Q{n}" for n, (cid, q) in enumerate(questions.items(), 1)
                   if cid not in ss["grading"] and not _answered(cid, q)]
        retry = bool(ss["grade_failed"])
        st.caption(GRADE_HINT)
        if st.button("채점 못한 문제 다시 채점" if retry else "채점하기", type="primary", width="stretch", key="w_grade"):
            if missing:
                ss["show_missing"] = True  # 카드가 버튼보다 먼저 그려지므로 한 번 다시 그린다
                st.rerun()
            ss["show_missing"] = False
            grade(questions, only=[cid for cid in questions if cid not in ss["grading"]])
            st.rerun()
        if ss["show_missing"] and missing:
            st.html(f'<p class="bn-red">아직 답하지 않은 문제: {", ".join(missing)} (E-11)</p>')
        if retry and graded:
            if st.button("채점 못한 문제는 빼고 공부 순서 보기", width="stretch", key="w_skip"):
                open_study()
    else:
        if st.button("공부 순서 보기", type="primary", width="stretch", key="w_study"):
            open_study()
        st.caption("누르면 틀리거나 헷갈린 개념의 보완 설명을 만든 뒤 ④로 넘어가요. 보통 20~40초 걸려요.")
