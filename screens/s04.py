"""S04 우선순위 보완 학습: 공부 순서와 오답노트, 시험 대비 요약 노트, 내려받기."""
import hashlib
import json

import streamlit as st

from core import explain, export, llm, note, pageimg
from core.diagnose import evidence_pages
from core.export import ACTION_HINT, FORMULA, explanation_html, note_card_html, review_html
from core.html import badge, bar, esc, status_badge
from core.priority import ACTIONS, split_review
from screens import common

VIEWS = ("🎯 공부 순서와 오답노트", "📒 시험 대비 요약 노트")
REVIEW_NOTE = "'진단 안 함'은 출제 가능성 점수가 20점 미만이거나 빠른 진단에서 빠져 문제를 내지 않은 개념이에요."


@st.cache_data(show_spinner=False, max_entries=300)
def page_image(run_id: str, n: int, _data: bytes):
    """강의자료 한 쪽 그림. PDF 바이트는 해시하지 않는다."""
    return pageimg.page_jpeg(_data, n)


def _answer_hash(cid: str) -> str:
    raw = json.dumps(common.given_of(cid), ensure_ascii=False, sort_keys=True)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]


def make_explanations(ids: list) -> None:
    """보완 설명을 동시에 만든다. 샘플에서 같은 답이면 서버에 저장된 설명을 다시 쓴다."""
    ss = st.session_state
    ss["stage_error"].pop("explain", None)
    cmap, questions = common.concept_map(), common.current_questions()
    prio_by = {p["concept_id"]: p for p in ss["priorities"]}
    # 스레드에 넘길 값은 스레드를 만들기 전에 꺼낸다
    material, meta, run_id = ss["material"], ss["meta_pages"], ss["run_id"]
    cache = common.result_cache() if ss["from_sample"] else None
    todo = {}
    for cid in ids:
        if cid in ss["explanations"] or cid not in prio_by:
            continue
        status, conf = prio_by[cid]["status"], common.confusion_of(cid)
        cache_key = ("e", run_id, cid, status, _answer_hash(cid), conf)
        if cache is not None:
            saved = cache.get(cache_key)
            if saved is not None:
                ss["explanations"][cid] = saved
                continue
        q = questions.get(cid)
        g = ss["grading"].get(cid) if q else None
        todo[cid] = (cache_key, status, q, g, common.given_of(cid), conf)
    ss["explain_failed"] = [c for c in ss["explain_failed"] if c not in ss["explanations"]]
    if not todo:
        return
    if material is None or common.ai_blocked("explain"):
        ss["explain_failed"] = sorted(set(ss["explain_failed"]) | set(todo))
        return
    jobs = {cid: (lambda usage, c=cmap[cid], t=t: explain.make_explanation(
        c, t[1], t[2], t[3], t[4], t[5], material, meta, usage)) for cid, t in todo.items()}
    with st.spinner("보완 설명을 만드는 중이에요. 보통 20~40초 걸려요."):
        results, errors = common.run_with_progress(jobs, "보완 설명 만드는 중", 8, "보완 설명")
    for cid, value in results.items():
        ss["explanations"][cid] = value
        if cache is not None:
            cache.put(todo[cid][0], value)
    ss["explain_failed"] = sorted((set(ss["explain_failed"]) | set(errors)) - set(results))
    if errors:
        common.set_stage_error("explain", next(iter(errors.values())))


def make_notes(only=None) -> None:
    """요약 노트: '자세히'·'보통'만 AI로 만들고 '짧게'는 개념 요약을 그대로 쓴다."""
    ss = st.session_state
    ss["stage_error"].pop("notes", None)
    cmap = common.concept_map()
    prio_by = {p["concept_id"]: p for p in ss["priorities"]}
    material, meta, run_id, utts = ss["material"], ss["meta_pages"], ss["run_id"], ss["utterances"]
    questions = common.current_questions()
    cache = common.result_cache() if ss["from_sample"] else None
    todo = {}
    for cid in note.lecture_order(ss["concepts"], meta):
        p = prio_by.get(cid)
        if p is None or (only is not None and cid not in only):
            continue
        detail = note.detail_of(p)
        if detail == "짧게":
            ss["notes"][cid] = note.short_note(cmap[cid])
            continue
        if cid in ss["notes"] and ss["notes"][cid]["detail"] == detail:
            continue
        cache_key = ("n", run_id, cid, detail, p["status"], _answer_hash(cid), common.confusion_of(cid))
        if cache is not None:
            saved = cache.get(cache_key)
            if saved is not None:
                ss["notes"][cid] = saved
                continue
        todo[cid] = (cache_key, p, ss["grading"].get(cid) if cid in questions else None)
    ss["notes_failed"] = [c for c in ss["notes_failed"] if c not in ss["notes"]]
    if not todo:
        ss["notes_made"] = True
        return
    if material is None or common.ai_blocked("notes"):
        ss["notes_failed"] = sorted(set(ss["notes_failed"]) | set(todo))
        ss["notes_made"] = True
        return
    jobs = {cid: (lambda usage, c=cmap[cid], t=t: note.make_note(c, t[1], t[2], utts, material, meta, usage))
            for cid, t in todo.items()}
    with st.spinner("요약 노트를 만드는 중이에요. 보통 20~40초 걸려요."):
        results, errors = common.run_with_progress(jobs, "요약 노트", 8, "요약 노트")
    for cid, value in results.items():
        ss["notes"][cid] = value
        if cache is not None:
            cache.put(todo[cid][0], value)
    ss["notes_failed"] = sorted((set(ss["notes_failed"]) | set(errors)) - set(results))
    # 다 끝난 뒤에만 '만들었음'으로 둔다. 만드는 도중 다른 버튼을 눌러 끊기면 다음에 다시 만든다.
    ss["notes_made"] = True
    if errors:
        common.set_stage_error("notes", next(iter(errors.values())))


def _downloads(where: str) -> None:
    ss = st.session_state
    state = common.snapshot()
    name_study, name_notes = export.file_names()
    left, right = st.columns(2)
    left.download_button("📥 공부 순서·오답노트 내려받기", export.study_html(state), file_name=name_study,
                         mime="text/html", key=f"w_dl_study_{where}", width="stretch")
    right.download_button("📒 요약 노트 내려받기", export.notes_html(state) if ss["notes_made"] else "",
                          file_name=name_notes, mime="text/html", key=f"w_dl_notes_{where}", width="stretch",
                          disabled=not ss["notes_made"],
                          help=None if ss["notes_made"] else "'시험 대비 요약 노트' 보기를 한 번 열면 켜져요.")


def _original_pages(cid: str, pages, where: str) -> None:
    """근거 페이지 중 메타 쪽을 뺀 앞 2쪽을 그림으로. PDF일 때만."""
    ss = st.session_state
    if not ss["material_bytes"]:
        return
    meta = set(ss["meta_pages"])
    body = [p for p in pages or [] if p not in meta][:2]
    if not body:
        return
    with st.expander("강의자료 원본 보기 · " + ", ".join(f"p.{p}" for p in body)):
        for p in body:
            img = page_image(ss["run_id"], p, ss["material_bytes"])
            if img:
                st.image(img, caption=f"p.{p}", width="stretch")


def _concept_card(p: dict, questions: dict) -> None:
    ss = st.session_state
    cid = p["concept_id"]
    q = questions.get(cid)
    g = ss["grading"].get(cid) if q else None
    expl, conf = ss["explanations"].get(cid), common.confusion_of(cid)
    with st.container(border=True):
        st.html(f"<h4 style='margin:0'>{p['rank']}. {esc(p['name'])}</h4><p style='margin:2px 0'>"
                f"{status_badge(p['status'])}{badge('출제 점수 ' + str(p['exam_pct']), 'blue')}"
                f"{badge('우선순위 ' + str(p['priority']))}</p>")
        if q and g:
            with st.expander(f"📝 내 문제와 답 다시 보기 · {g['status']} {g['score']}/10"):
                st.html(review_html(q, g, common.given_of(cid)))
        if expl or conf:
            st.html(explanation_html(expl, conf))
        if not expl:
            failed = cid in ss["explain_failed"]
            if failed:
                st.html('<p class="bn-red">설명을 만들지 못했어요. 아래 버튼으로 다시 만들 수 있어요.</p>')
            if ss["material"] is None:
                st.caption("자료를 다시 올리면 새 설명을 만들 수 있어요.")
            elif st.button("설명 다시 만들기" if failed else "설명 보기", key=f"w_ex_{cid}"):
                make_explanations([cid])
                st.rerun()
        pages = (expl or {}).get("check_pages") or evidence_pages(common.concept_map()[cid], [])
        _original_pages(cid, pages, "study")


def _study_view() -> None:
    ss = st.session_state
    prios, questions = ss["priorities"], common.current_questions()
    for action in ACTIONS:
        group = [p for p in prios if p["action"] == action]
        if not group:
            continue
        st.subheader(f"{action} · {len(group)}개")
        st.caption(ACTION_HINT[action])
        if action == "복습만":
            opened, folded = split_review(group, common.confusions())
            for p in opened:  # 헷갈린 점을 적은 개념은 접지 않는다
                _concept_card(p, questions)
            if folded:
                with st.expander(f"복습만 {len(folded)}개 펼쳐 보기"):
                    st.caption(REVIEW_NOTE)
                    for p in folded:
                        _concept_card(p, questions)
            continue
        if action == "다음":
            rest = [p["concept_id"] for p in group if p["concept_id"] not in ss["explanations"]]
            if rest and ss["material"] is not None:
                if st.button(f"'다음' 개념 설명 {len(rest)}개 한 번에 보기", key="w_ex_next", width="stretch"):
                    make_explanations(rest)
                    st.rerun()
        for p in group:
            _concept_card(p, questions)
    with st.expander("전체 표로 보기"):
        rows = "".join(
            f"<tr><td>{p['rank']}</td><td>{esc(p['name'])}</td><td>{bar(p['exam_pct'])} {p['exam_pct']}점</td>"
            f"<td>{status_badge(p['status'])}</td><td>{bar(p['priority'], 'red')} {p['priority']}</td>"
            f"<td>{esc(p['action'])}</td></tr>" for p in prios)
        st.html('<div class="bn-scroll"><table class="bn-table"><tr><th>순위</th><th>개념</th><th>출제 점수</th>'
                f"<th>이해 상태</th><th>우선순위</th><th>권장</th></tr>{rows}</table></div>"
                f'<p class="bn-small">{esc(FORMULA)}</p>')


def _notes_view() -> None:
    ss = st.session_state
    if not ss["notes_made"]:
        make_notes()
        st.rerun()
    common.show_stage_error("notes")
    cmap = common.concept_map()
    prio_by = {p["concept_id"]: p for p in ss["priorities"]}
    order = note.lecture_order(ss["concepts"], ss["meta_pages"])
    count = {d: sum(1 for cid in order if ss["notes"].get(cid, {}).get("detail") == d) for d in note.DETAILS}
    common.num_boxes([(d, count[d], "blue" if d == "자세히" else "plain") for d in note.DETAILS])
    st.caption("강의 순서대로 정리했어요. 중요한 개념일수록 자세히 썼어요.")
    for cid in order:
        made = ss["notes"].get(cid)
        if made is None:
            with st.container(border=True):
                st.html(f"<h4 style='margin:0'>{esc(cmap[cid]['name'])}</h4>"
                        '<p class="bn-red">요약 노트를 만들지 못했어요.</p>')
                if ss["material"] is not None and st.button("요약 노트 다시 만들기", key=f"w_note_{cid}"):
                    make_notes(only=[cid])
                    st.rerun()
            continue
        st.html(note_card_html(cmap[cid], made, prio_by.get(cid), ss["utterances"]))
        _original_pages(cid, made.get("source_pages") or evidence_pages(cmap[cid], []), "notes")


def render() -> None:
    ss = st.session_state
    common.header(4)
    prios = ss["priorities"]
    if not prios:
        st.info("아직 공부 순서가 없어요. ③에서 채점한 뒤 '공부 순서 보기'를 눌러 주세요.")
        return
    common.show_stage_error("explain")
    count = {a: sum(1 for p in prios if p["action"] == a) for a in ACTIONS}
    common.num_boxes([("지금 당장", count["지금 당장"], "bad"), ("다음", count["다음"], "warn"),
                      ("복습만", count["복습만"], "plain")])
    _downloads("top")
    if "w_view" not in st.session_state:
        st.session_state["w_view"] = ss["s04_view"] or VIEWS[0]
    view = st.segmented_control("보기 고르기", VIEWS, key="w_view", label_visibility="collapsed",
                                required=True, width="stretch") or VIEWS[0]
    ss["s04_view"] = view
    if view == VIEWS[1]:
        _notes_view()
    else:
        _study_view()
    st.divider()
    _downloads("bottom")
    if st.button("다른 자료로 다시", key="w_again", width="stretch"):
        common.reset_state()
        common.goto(1)
