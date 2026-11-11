"""S02 출제 포인트 레이더: 순위 목록, 점수 내역, 문제 형식, 진단 시작."""
import streamlit as st

import config
from core import diagnose, llm
from core.diagnose import MODES, quick_default
from core.html import SCORE_NOTE, esc, page_chips
from core.score import TYPE_LABEL
from screens import common

SAMPLE_SAVED_NOTE = "샘플은 미리 저장해 둔 분석 결과를 써요. 내 자료는 매번 새로 분석해요."
NO_AUDIO_NOTE = "녹음 없이 자료만으로 계산했어요. 녹음을 넣으면 순위가 더 정확해져요."


def make_questions(ids: list) -> None:
    """대상 개념마다 문제 1개씩(동시 호출). 샘플 자료는 서버에 저장된 문제를 다시 쓴다."""
    ss = st.session_state
    ss["stage_error"].pop("questions", None)
    ss["diag_ids"] = list(ids)
    cmap = common.concept_map()
    names = [cmap[cid]["name"] for cid in ids]
    # 스레드에 넘길 값은 스레드를 만들기 전에 꺼낸다
    material, meta, run_id = ss["material"], ss["meta_pages"], ss["run_id"]
    cache = common.result_cache() if ss["from_sample"] else None
    todo = {}
    for cid in ids:
        key = (cid, common.wanted_kind(cid))
        if key in ss["questions"]:
            continue
        cache_key = ("q", run_id, cid, key[1], tuple(n for n in names if n != cmap[cid]["name"]))
        if cache is not None:
            saved = cache.get(cache_key)
            if saved is not None:  # 저장된 문제를 꺼냈으면 AI를 부르지 않는다
                ss["questions"][key] = saved
                ss["q_failed"].pop(key, None)
                continue
        todo[key] = (cmap[cid], cache_key)
    if not todo or material is None or common.ai_blocked("questions"):
        return
    jobs = {key: (lambda usage, c=c, kind=key[1]: diagnose.make_question(c, kind, material, meta, names, usage))
            for key, (c, _) in todo.items()}
    with st.spinner("문제를 만드는 중이에요. 보통 20~40초 걸려요."):
        results, errors = common.run_with_progress(jobs, "문제 만드는 중", 6, "문제 만들기")
    for key, q in results.items():
        ss["questions"][key] = q
        ss["q_failed"].pop(key, None)
        if cache is not None:
            cache.put(todo[key][1], q)
    for key, exc in errors.items():
        message, code = llm.error_text(exc)
        ss["q_failed"][key] = (message, code, f"{type(exc).__name__}: {exc}")
    if errors and not common.current_questions():
        common.set_stage_error("questions", next(iter(errors.values())))


def _detail_html(row: dict, concept: dict, utts: list) -> str:
    parts = [f"<h4>{row['rank']}. {esc(row['name'])} · {row['pct']}점</h4>",
             f"<p>{esc(concept.get('summary', ''))}</p>",
             f"<p class='bn-small'>등장 페이지 {page_chips(concept.get('pages'))}</p>"]
    if concept.get("objective_quote"):
        parts.append(f"<p class='bn-small'>학습목표: “{esc(concept['objective_quote'])}”</p>")
    lines = "".join(f"<li>{esc(r['label'])} <b>{r['points']:+.1f}</b></li>" for r in row["reasons"])
    parts.append(f"<p class='bn-small'>신호별 점수 (원점수 {row['raw']:.1f})</p><ul>{lines}</ul>")
    mine = [u for u in utts if u.get("concept_id") == row["concept_id"]]
    if mine:
        quotes = "".join(f"<li>“{esc(u['quote'])}” <span class='bn-badge'>{TYPE_LABEL.get(u['type'], u['type'])}"
                         f" · 강도 {u['strength']}</span></li>" for u in mine)
        parts.append(f"<p class='bn-small'>교수님이 한 말</p><ul>{quotes}</ul>")
    return f'<div class="bn-card">{"".join(parts)}</div>'


def render() -> None:
    ss = st.session_state
    common.header(2)
    for notice in ss["notices"]:
        st.warning(notice)
    if ss["from_saved"]:
        st.info(SAMPLE_SAVED_NOTE)
    rows, utts = ss["scores"], ss["utterances"]
    targets = common.all_targets()
    graded = bool(ss["grading"])

    # 빠른 진단 기본값: 직접 올린 자료이고 대상이 8개보다 많을 때만 켜짐
    if ss["quick_diag"] is None:
        ss["quick_diag"] = quick_default(ss["from_sample"], len(targets))
    quick_now = st.session_state.get("w_quick", ss["quick_diag"]) and len(targets) > config.QUICK_DIAG_TOP
    n_diag = min(len(targets), config.QUICK_DIAG_TOP) if quick_now else len(targets)
    strong = len({u["quote"] for u in utts if u.get("concept_id")})
    common.num_boxes([("찾은 개념", len(rows), "plain"), ("교수님 강조", strong, "blue"),
                      ("진단할 개념", n_diag, "bad")])
    if not ss["transcript"]:
        st.info(NO_AUDIO_NOTE)

    high = [r for r in rows if r["pct"] >= config.DIAG_MIN_PCT]
    low = [r for r in rows if r["pct"] < config.DIAG_MIN_PCT]
    markup = "".join(common.score_row_html(r) for r in high)
    if low:
        markup += (f"<p class='bn-small' style='margin:10px 0 2px'>아래 {len(low)}개는 출제 가능성 점수가 "
                   f"{config.DIAG_MIN_PCT}점 미만이라 진단하지 않고 '복습만'으로 둬요.</p>")
        markup += "".join(common.score_row_html(r, dim=True) for r in low)
    st.html(f'<div class="bn-card">{markup}</div><p class="bn-small">{esc(SCORE_NOTE)}</p>')

    with st.expander("점수 내역과 교수님이 한 말 자세히 보기"):
        cmap = common.concept_map()
        st.html("".join(_detail_html(r, cmap[r["concept_id"]], utts) for r in rows))
        outside = [u for u in utts if not u.get("concept_id")]
        if outside:
            lines = "".join(f"<li>{esc(u.get('concept_name', ''))}: “{esc(u['quote'])}”</li>" for u in outside)
            st.html(f"<p class='bn-small'>개념 목록 밖 언급</p><ul>{lines}</ul>")

    st.subheader("진단 준비")
    if "w_qmode" not in st.session_state:
        st.session_state["w_qmode"] = ss["q_mode"]
    mode = st.radio("문제 형식", MODES, key="w_qmode", horizontal=True, disabled=graded,
                    captions=[f"{config.ESSAY_MIN_PCT}점 이상 서술형 · 나머지 객관식", "보기 4개에서 고르기", "2~3문장으로 쓰기"])
    ss["q_mode"] = mode
    if len(targets) > config.QUICK_DIAG_TOP:
        if "w_quick" not in st.session_state:
            st.session_state["w_quick"] = bool(ss["quick_diag"])
        rest = len(targets) - config.QUICK_DIAG_TOP
        quick = st.toggle(f"빠른 진단: 출제 가능성 상위 {config.QUICK_DIAG_TOP}개만 풀기", key="w_quick", disabled=graded,
                          help=f"{len(targets)}문제 대신 {config.QUICK_DIAG_TOP}문제만 풀어요. 나머지 {rest}개는 "
                               "'진단 안 함'(이해도 중간)으로 공부 순서를 계산해요.")
        ss["quick_diag"] = quick
    else:
        ss["quick_diag"] = False
    if graded:
        st.caption("이미 채점한 뒤라 문제 형식과 빠른 진단은 바꿀 수 없어요.")

    ids = common.target_ids()
    common.show_stage_error("questions")
    if not ids:
        st.info(f"출제 가능성 점수가 {config.DIAG_MIN_PCT}점 이상인 개념이 없어 진단할 문제가 없어요.")
        return
    locked = ss["material"] is None
    if st.button(f"{len(ids)}개 개념 진단하기", type="primary", width="stretch", key="w_diag", disabled=locked):
        make_questions(ids)
        if common.current_questions():
            common.goto(3)
        st.rerun()
    st.caption("누르면 개념마다 문제를 하나씩 만들어요. 다 만들면 ③으로 넘어가요.")
