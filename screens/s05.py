"""S05 안내·설정: 사용 방법, 주의, 현재 설정, 이번 세션 사용량."""
import streamlit as st

import config
from core import stt
from core.html import NOTICE, esc
from core.score import WEIGHTS_VERSION
from screens import common

HOW_TO = (
    "① 강의자료(PDF·PPTX)와 녹음 또는 대본을 올리고 '분석 시작'을 눌러요. 파일이 없으면 '샘플로 1분 체험'을 눌러요.",
    "② 출제 가능성 점수 순위와 근거(학습목표, 본문 쪽수, 예제, 연습문제, 교수님 말)를 봐요.",
    "③ 진단 문제에 답하고 채점해요. 모르면 '모르겠어요', 찍었으면 '확신 없이 골랐어요'를 골라요.",
    "④ 공부 순서와 오답노트, 요약 노트를 보고 HTML 파일로 내려받아요.",
)
CAUTIONS = (
    NOTICE,
    "녹음은 교수님 허락을 받은 것만, 개인 학습 목적으로만 올려 주세요.",
    "올린 자료와 녹음은 분석을 위해 AI 제공사(Anthropic, OpenAI) 서버로 전송됩니다.",
    "올린 파일은 서버 디스크에 저장하지 않아요. 결과는 이 화면(세션)이 끝나면 사라지고, 같은 파일의 분석 결과와 "
    "쪽 그림은 서버 메모리에 잠시 두었다가 서버가 다시 켜지면 사라져요. 새로고침 전에 ④에서 내려받아 두세요.",
)


def _table(rows) -> str:
    body = "".join(f"<tr><th>{esc(a)}</th><td>{esc(b)}</td></tr>" for a, b in rows)
    return f'<div class="bn-scroll"><table class="bn-table">{body}</table></div>'


def render() -> None:
    ss = st.session_state
    common.header(5)
    st.subheader("사용 방법")
    st.html('<ul class="bn-diff">' + "".join(f"<li>{esc(t)}</li>" for t in HOW_TO) + "</ul>")
    st.subheader("주의할 점")
    st.html('<ul class="bn-diff">' + "".join(f"<li>{esc(t)}</li>" for t in CAUTIONS) + "</ul>")

    st.subheader("현재 설정")
    st.html(_table([
        ("언어 모델", config.LLM_MODEL),
        ("음성 인식", "사용 가능" if stt.available() else "사용 안 함 (대본 붙여넣기만)"),
        ("진단 기준", f"출제 가능성 점수 {config.DIAG_MIN_PCT}점 이상 전부 (빠른 진단은 상위 {config.QUICK_DIAG_TOP}개)"),
        ("문제 형식", f"{ss['q_mode']} ({config.ESSAY_MIN_PCT}점 이상 서술형 · 나머지 객관식이 기본)"),
        ("가중치 버전", WEIGHTS_VERSION),
        ("사용 제한", f"이 화면 분석 {config.MAX_ANALYSES_PER_SESSION}번 · 서버 전체 하루 분석 "
                  f"{config.MAX_ANALYSES_PER_DAY}번 · 하루 AI 호출 {config.MAX_AI_CALLS_PER_DAY}번"),
    ]))

    st.subheader("이번 세션 사용량")
    usage = ss["usage"]
    rows = [("AI 호출 수", f"{usage.calls}번"),
            ("입력 토큰", f"{usage.input_tokens:,}"), ("출력 토큰", f"{usage.output_tokens:,}"),
            ("이 화면에서 한 분석", f"{ss['analyses_used']}번"),
            ("서버 전체 오늘 분석", f"{common.analysis_counter().count}번"),
            ("서버 전체 오늘 AI 호출", f"{common.ai_call_counter().count}번")]
    rows += [(f"걸린 시간 · {stage}", f"{seconds:.1f}초") for stage, seconds in ss["timings"].items()]
    if ss["timings"]:
        rows.append(("걸린 시간 · 합계", f"{sum(ss['timings'].values()):.1f}초"))
    st.html(_table(rows))
    st.caption("AI 호출 수는 호출마다 세요. 저장된 결과를 다시 쓸 때는 더하지 않아요.")

    st.subheader("정보")
    st.html(_table([("팀", config.TEAM_NAME), ("대회", config.CONTEST_NAME)]))
    st.markdown(f"GitHub 저장소: [{config.REPO_URL}]({config.REPO_URL})")
