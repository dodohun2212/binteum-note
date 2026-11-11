"""화면 공용: 세션 초기화, 키 읽기, 사용량·비용 보호 연결, 머리말, 카드 조각."""
import time

import streamlit as st

import config
from core import guard, llm
from core import score as score_mod
from core.diagnose import MCQ, diag_targets, question_kind
from core.html import badge, bar, esc, numrow

STEPS = {1: "① 자료 올리기", 2: "② 출제 포인트", 3: "③ 취약점 진단", 4: "④ 공부 순서", 5: "⑤ 안내·설정"}
TITLES = {
    1: ("빈틈노트", "코리아텍 학생이 시험 전, 강의자료와 교수님 수업 녹음으로 무엇부터 공부할지 정하는 앱"),
    2: ("출제 포인트 레이더", "자료와 녹음의 신호를 모아 시험에 나올 가능성이 높은 개념부터 보여 줘요."),
    3: ("내 취약점 진단", "짧은 문제로 내가 실제로 아는지 확인해요. 찍어서 맞힌 것은 '헷갈림'이에요."),
    4: ("우선순위 보완 학습", "출제 점수 × 모르는 정도로 정한 공부 순서와 오답노트, 요약 노트예요."),
    5: ("안내·설정", "사용 방법과 주의할 점, 지금 설정과 사용량이에요."),
}

# 세션 키는 모두 여기에 기본값과 함께 둔다. (기본값을 만드는 함수, 새 분석 때 지울지)
DEFAULTS = {
    "step": (lambda: 1, True),
    "material": (lambda: None, True),
    "material_bytes": (lambda: None, True),
    "transcript": (lambda: None, True),
    "transcript_source": (lambda: None, True),
    "concepts": (list, True),
    "meta_pages": (list, True),
    "utterances": (list, True),
    "scores": (list, True),
    "notices": (list, True),
    "q_mode": (lambda: "섞어서", True),
    "quick_diag": (lambda: None, True),
    "diag_ids": (list, True),
    "questions": (dict, True),          # {(개념 id, 고른 형식): 문제}
    "q_failed": (dict, True),           # {(개념 id, 고른 형식): (문구, 코드)}
    "answers": (dict, True),
    "dont_know": (dict, True),
    "mcq_choice": (dict, True),
    "guessed": (dict, True),
    "confusion": (dict, True),
    "show_missing": (lambda: False, True),
    "grading": (dict, True),
    "grade_failed": (list, True),
    "grade_error": (lambda: None, True),
    "stage_error": (dict, True),        # {단계: (문구, 코드, 자세한 오류)}
    "priorities": (list, True),
    "explanations": (dict, True),
    "explain_failed": (list, True),
    "notes": (dict, True),
    "notes_failed": (list, True),
    "notes_made": (lambda: False, True),
    "s04_view": (lambda: None, True),
    "run_id": (lambda: None, True),
    "from_sample": (lambda: False, True),
    "from_saved": (lambda: False, True),
    "usage": (llm.Usage, True),
    "timings": (dict, True),
    "errors": (list, True),
    "analyses_used": (lambda: 0, False),   # "다른 자료로 다시"로도 지우지 않는다
}
# 입력칸 위젯 키의 접두어. 새 분석 때 이 접두어로 시작하는 키를 지운다.
WIDGET_PREFIXES = ("ans_", "dk_", "mcq_", "guess_", "conf_", "w_")

MCQ_DONT_KNOW = "모르겠어요"


def init_state() -> None:
    for key, (make, _) in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = make()


def reset_state() -> None:
    """새 분석·"다른 자료로 다시": 분석 횟수만 남기고 전부 지운다."""
    for key, (make, clear) in DEFAULTS.items():
        if clear:
            st.session_state[key] = make()
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith(WIDGET_PREFIXES):
            del st.session_state[key]


def load_keys() -> None:
    """키는 st.secrets → 환경변수 순으로만 읽는다."""
    found = {}
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        try:
            found[name] = st.secrets.get(name)
        except Exception:
            found[name] = None
    llm.configure(found["ANTHROPIC_API_KEY"], found["OPENAI_API_KEY"])


@st.cache_resource
def analysis_counter() -> guard.DailyCounter:
    return guard.DailyCounter(config.MAX_ANALYSES_PER_DAY)


@st.cache_resource
def ai_call_counter() -> guard.DailyCounter:
    return guard.DailyCounter(config.MAX_AI_CALLS_PER_DAY)


@st.cache_resource
def result_cache() -> guard.ResultCache:
    return guard.ResultCache(max_items=200)


def take_analysis():
    """분석 1번을 쓴다. 못 쓰면 (문구, 코드)를 돌려준다."""
    ss = st.session_state
    if guard.session_left(ss["analyses_used"], config.MAX_ANALYSES_PER_SESSION) == 0:
        return (f"이 화면에서는 분석을 {config.MAX_ANALYSES_PER_SESSION}번까지 할 수 있어요. "
                "지금 결과는 ②~④에서 계속 볼 수 있어요.", "E-16")
    if ai_call_counter().full or not analysis_counter().try_take():
        return llm.LimitError.message, "E-17"
    ss["analyses_used"] += 1
    return None


def give_back_analysis(session: bool, daily: bool) -> None:
    if session and st.session_state["analyses_used"] > 0:
        st.session_state["analyses_used"] -= 1
    if daily:
        analysis_counter().give_back()


def add_usage(usage, stage: str = "", seconds: float = 0.0) -> None:
    """사용량을 세션에 더하고, 서버 전체 하루 AI 호출 수에도 더한다. 단계별 시간은 덮어쓰지 않고 더한다."""
    ss = st.session_state
    if usage is not None:
        ss["usage"].merge(usage)
        ai_call_counter().add(usage.calls)
    if stage:
        ss["timings"][stage] = ss["timings"].get(stage, 0.0) + seconds


def ai_blocked(stage: str) -> bool:
    """하루 AI 호출 상한에 닿았으면 새 AI 작업을 시작하지 않고 그 단계에 E-17을 남긴다."""
    if ai_call_counter().full:
        st.session_state["stage_error"][stage] = (llm.LimitError.message, "E-17", "")
        return True
    return False


def set_stage_error(stage: str, exc) -> None:
    message, code = llm.error_text(exc)
    st.session_state["stage_error"][stage] = (message, code, f"{type(exc).__name__}: {exc}")


def show_stage_error(stage: str) -> None:
    err = st.session_state["stage_error"].get(stage)
    if not err:
        return
    message, code, detail = err
    st.error(f"{message} ({code})" if code else message)
    if detail:
        with st.expander("자세한 오류"):
            st.code(detail)


def run_with_progress(jobs: dict, label: str, workers: int, stage: str) -> tuple:
    """여러 호출을 동시에 부르며 진행 막대 'k / n'을 늘린다. (결과, 실패)를 돌려준다."""
    if not jobs:
        return {}, {}
    started = time.time()
    progress = st.progress(0.0, text=f"{label} 0 / {len(jobs)}")

    def on_done(done, total):
        progress.progress(done / total, text=f"{label} {done} / {total}")

    results, errors, usage = llm.run_many(jobs, workers=workers, on_done=on_done)
    progress.empty()
    add_usage(usage, stage, time.time() - started)
    return results, errors


def goto(step: int) -> None:
    st.session_state["step"] = step
    st.rerun()


def can_open(step: int) -> bool:
    ss = st.session_state
    if step in (1, 5):
        return True
    if step == 2:
        return bool(ss["scores"])
    if step == 3:
        return bool(ss["scores"]) and bool(current_questions())
    return bool(ss["priorities"])


def header(step: int) -> None:
    """맨 위 단계 표시 줄, 제목, 한 줄 설명."""
    crumbs = []
    for n in (1, 2, 3, 4):
        cls = "bn-step bn-step-on" if n == step else "bn-step"
        crumbs.append(f'<span class="{cls}">{STEPS[n]}</span>')
    title, sub = TITLES[step]
    st.html(f'<div class="bn-steps">{" › ".join(crumbs)}</div>'
            f'<h1 class="bn-title">{esc(title)}</h1><p class="bn-sub">{esc(sub)}</p>')


def num_boxes(items) -> None:
    st.html(numrow(items))


# ---------- 진단 대상·문제 꺼내기 ----------

def score_rows() -> list:
    return st.session_state["scores"]


def all_targets() -> list:
    return diag_targets(score_rows())


def quick_on() -> bool:
    return bool(st.session_state["quick_diag"]) and len(all_targets()) > config.QUICK_DIAG_TOP


def target_ids() -> list:
    return diag_targets(score_rows(), top=config.QUICK_DIAG_TOP if quick_on() else None)


def wanted_kind(cid: str) -> str:
    pct = next(r["pct"] for r in score_rows() if r["concept_id"] == cid)
    return question_kind(pct, st.session_state["q_mode"])


def current_questions() -> dict:
    """지금 진단 대상과 고른 형식에 맞는 문제 {개념 id: 문제} (순위 순서)."""
    ss = st.session_state
    out = {}
    for cid in ss["diag_ids"]:
        q = ss["questions"].get((cid, wanted_kind(cid)))
        if q:
            out[cid] = q
    return out


def given_of(cid: str) -> dict:
    ss = st.session_state
    return {"answer": ss["answers"].get(cid, ""), "dont_know": bool(ss["dont_know"].get(cid)),
            "choice": ss["mcq_choice"].get(cid), "guessed": bool(ss["guessed"].get(cid))}


def confusion_of(cid: str) -> str:
    """헷갈린 점은 객관식에서 보기를 고르고 '확신 없이 골랐어요'를 체크했을 때만 쓴다."""
    ss = st.session_state
    choice = ss["mcq_choice"].get(cid)
    if ss["guessed"].get(cid) and isinstance(choice, int) and choice >= 0:
        return str(ss["confusion"].get(cid) or "").strip()
    return ""


def confusions() -> dict:
    return {cid: confusion_of(cid) for cid in current_questions() if confusion_of(cid)}


def concept_map() -> dict:
    return {c["id"]: c for c in st.session_state["concepts"]}


def snapshot() -> dict:
    """내려받기·저장에 넘기는 세션 묶음."""
    ss = st.session_state
    qs = current_questions()
    return {
        "material_name": ss["material"]["name"] if ss["material"] else None,
        "has_transcript": bool(ss["transcript"]),
        "concepts": ss["concepts"], "meta_pages": ss["meta_pages"], "utterances": ss["utterances"],
        "scores": ss["scores"], "priorities": ss["priorities"], "questions": qs,
        "given": {cid: given_of(cid) for cid in qs}, "confusion": confusions(),
        "grading": {cid: g for cid, g in ss["grading"].items() if cid in qs},
        "explanations": ss["explanations"], "notes": ss["notes"],
    }


def score_row_html(row: dict, dim: bool = False) -> str:
    """② 순위 목록 한 줄: 순위, 이름, 막대와 점수, 근거 배지."""
    chips = "".join(badge(t, "neg" if neg else "plain") for t, neg in score_mod.badges(row))
    return (f'<div class="bn-row{" bn-dim" if dim else ""}"><span class="bn-row-rank">{row["rank"]}</span>'
            f'<span class="bn-row-name">{esc(row["name"])}</span>'
            f'<span class="bn-row-bar">{bar(row["pct"], "gray" if dim else "blue")}</span>'
            f'<span class="bn-row-pct">{row["pct"]}점</span>'
            f'<span class="bn-row-badges">{chips}</span></div>')


def kind_badges(q: dict, pct: int) -> str:
    return badge(q["kind"], "blue" if q["kind"] == MCQ else "plain") + badge(f"출제 점수 {pct}", "blue")
