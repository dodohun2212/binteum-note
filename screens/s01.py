"""S01 자료 올리기: 첫 화면, 샘플 체험, 내 자료 분석."""
import time

import streamlit as st

import config
from core import concepts as concepts_mod
from core import extract, guard, llm, sample, stt
from core import score as score_mod
from core import utterances as utter_mod
from core.html import NOTICE, badge, esc
from screens import common

SAMPLE_BUTTON = "🧪 샘플로 1분 체험"
SAMPLE_NOTE = "가상 자료구조 8장 슬라이드와 수업 대본으로 파일 없이 끝까지 써 볼 수 있어요"
DIFFS = (
    "교수님이 수업에서 \"이건 시험에 나와요\", \"꼭 알아 두세요\"라고 한 말을 녹음에서 찾아 출제 점수의 근거로 보여 줘요",
    "진단 문제로 내가 실제로 아는지 확인해요. 확신 없이 골라 맞힌 것도 '헷갈림'으로 가려요",
    "출제 점수 × 모르는 정도로 공부 순서를 정하고, 강의자료 쪽 번호를 인용한 오답노트와 요약 노트를 줘요",
)
RECEIVE = (
    ("진단 결과", "개념마다 앎 · 헷갈림 · 모름과 틀린 이유 한 줄"),
    ("공부 순서", "지금 당장 · 다음 · 복습만으로 묶은 순서"),
    ("오답노트", "내 문제와 답, 채점, 자료 쪽 번호를 인용한 보완 설명"),
    ("요약 노트", "강의 순서대로 모든 개념, 중요한 개념일수록 자세히"),
)
REAL_CHECK = ("대회 전에 만든 이전 버전으로 실제 자료구조 수업 한 과목의 강의자료(1~7장)를 확인해 보니, "
              "교수님이 시험 전에 예고한 개념 17개 중 15개를 자료만으로 진단 대상에 골랐어요"
              "(교수님 예고와 비교한 값이고, 실제 시험지와 비교한 것은 아니에요).")
SEND_NOTE = ("올린 자료와 녹음은 분석을 위해 AI 제공사(Anthropic, OpenAI) 서버로 전송됩니다. "
             "올린 파일은 서버 디스크에 저장하지 않아요. 결과는 이 화면(세션)이 끝나면 사라지고, "
             "같은 파일의 분석 결과와 쪽 그림은 서버 메모리에 잠시 두었다가 서버가 다시 켜지면 사라져요.")


@st.cache_data(show_spinner=False, max_entries=50)
def cached_concepts(run_id: str, _material: dict, _usage) -> dict:
    """같은 파일이면 호출 1 결과를 다시 쓴다. 캐시에서 꺼내면 _usage는 그대로다."""
    return concepts_mod.extract_concepts(_material, _usage)


@st.cache_data(show_spinner=False, max_entries=50)
def cached_utterances(run_id: str, transcript: str, concept_key: str, _concepts: list, _usage) -> list:
    """호출 2 캐시 키에는 대본과 함께 개념 목록도 넣는다."""
    return utter_mod.find_utterances(transcript, _concepts, _usage)


def _finish(material, data, transcript, source, result_concepts, meta, utts, scores, run_id,
            from_sample, notices) -> None:
    ss = st.session_state
    ss.update(material=material, material_bytes=data if material["kind"] == "pdf" else None,
              transcript=transcript, transcript_source=source, concepts=result_concepts,
              meta_pages=meta, utterances=utts, scores=scores, run_id=run_id,
              from_sample=from_sample, from_saved=from_sample, notices=notices)


def start_sample() -> None:
    """샘플은 호출 1·2를 부르지 않고 저장해 둔 실제 AI 결과로 바로 ②에 간다."""
    blocked = common.take_analysis()
    if blocked:
        st.error(f"{blocked[0]} ({blocked[1]})")
        return
    common.reset_state()
    data, transcript = sample.load_sample()
    material = extract.extract(sample.SAMPLE_PDF.name, data)
    saved = sample.saved_analysis(material, transcript)
    _finish(material, data, transcript, "paste", saved["concepts"], saved["meta_pages"],
            saved["utterances"], saved["scores"]["scores"], extract.make_run_id(data, transcript),
            True, [])
    # 저장된 결과만 쓴 분석(AI 호출 0번)은 하루 횟수에서 빼지 않는다
    common.give_back_analysis(*guard.refund_needed(False, 0))
    common.goto(2)


def analyze(file, audio, pasted: str) -> None:
    """내 자료 분석: 추출 → 대본 → 개념(호출 1) → 강조(호출 2) → 점수."""
    blocked = common.take_analysis()
    if blocked:
        st.error(f"{blocked[0]} ({blocked[1]})")
        return
    usage, started, notices = llm.Usage(), time.time(), []
    try:
        with st.status("분석하는 중이에요. 보통 1분쯤 걸려요.", expanded=True) as status:
            st.write("텍스트 추출 중")
            data = file.getvalue()
            material = extract.extract(file.name, data)
            if material["total_pages"] > config.MAX_PAGES:
                notices.append(f"앞 {config.MAX_PAGES}쪽만 분석해요. 한 장씩 올리면 더 정확해요 (E-13)")
            audio_bytes = None
            if audio is not None and not pasted.strip():
                try:
                    extract.check_audio(audio.name, audio.size)
                    audio_bytes = audio.getvalue()
                    st.write("녹음 받아쓰는 중")
                except extract.ExtractError as e:
                    notices.append(f"{e.message} (E-04)")
            # 대본은 받자마자 가린다
            transcript, source, stt_notice = stt.resolve_transcript(
                pasted, audio_bytes, audio.name if audio is not None else "")
            if stt_notice:
                notices.append(f"{stt_notice} (E-05)")
            run_id = extract.make_run_id(data, transcript or "")
            st.write("개념 찾는 중")
            result = cached_concepts(run_id, material, usage)
            utts = []
            if transcript:
                st.write("교수님 강조 찾는 중")
                utts = cached_utterances(run_id, transcript, utter_mod.concept_key(result["concepts"]),
                                         result["concepts"], usage)
                if not utts:
                    notices.append("녹음에서 강조한 말을 찾지 못했어요. 자료만으로 점수를 계산했어요 (E-10)")
            st.write("점수 계산 중")
            meta = score_mod.find_meta_pages(material["pages"], result)
            scores = score_mod.compute_scores(result["concepts"], utts, meta)["scores"]
            status.update(label="분석을 마쳤어요.", state="complete")
    except Exception as e:  # 실패하면 ①에 머문다
        common.add_usage(usage, "분석", time.time() - started)
        common.give_back_analysis(*guard.refund_needed(True, usage.calls))
        message, code = llm.error_text(e)
        st.error(f"{message} ({code})" if code else message)
        if not isinstance(e, (extract.ExtractError, concepts_mod.NoConceptsError)):
            with st.expander("자세한 오류"):
                st.code(f"{type(e).__name__}: {e}")
        return
    analyses_used = st.session_state["analyses_used"]
    common.reset_state()
    st.session_state["analyses_used"] = analyses_used
    _finish(material, data, transcript, source, result["concepts"], meta, utts, scores, run_id, False, notices)
    common.add_usage(usage, "분석", time.time() - started)
    common.give_back_analysis(*guard.refund_needed(False, usage.calls))
    common.goto(2)


def _preview_html() -> str:
    rows = ""
    for i, (name, pct, badges) in enumerate(sample.preview_top3(), 1):
        chips = "".join(badge(t, "neg" if neg else "plain") for t, neg in badges)
        rows += (f'<div class="bn-row"><span class="bn-row-rank">{i}</span>'
                 f'<span class="bn-row-name">{esc(name)}</span><span class="bn-row-pct">{pct}점</span>'
                 f'<span class="bn-row-badges">{chips}</span></div>')
    gets = "".join(f"<li><b>{esc(a)}</b> · {esc(b)}</li>" for a, b in RECEIVE)
    return (f'<div class="bn-card"><h4>결과 미리보기</h4>'
            f'<p class="bn-small">샘플 자료의 출제 가능성 점수 상위 3개예요. 이 자료 안에서 개념끼리 비교한 점수이고 확률이 아니에요.</p>{rows}'
            f'<p class="bn-small" style="margin-top:10px">진단을 마치면 받는 것</p><ul class="bn-diff">{gets}</ul></div>')


def render() -> None:
    ss = st.session_state
    common.header(1)
    for message in ss["errors"]:
        st.warning(message)
    ss["errors"] = []
    has_key = llm.has_key()
    if llm.is_fake():
        st.warning("가짜 AI 모드예요. 문제·채점·설명은 정해진 모양의 예시 답이에요.")
    if st.button(SAMPLE_BUTTON, type="primary", width="stretch", disabled=not has_key, key="w_sample"):
        start_sample()
    st.caption(SAMPLE_NOTE)
    if not has_key:
        st.error("AI 키가 설정되지 않았어요. README의 설정 방법을 보세요 (E-06)")
    left = guard.session_left(ss["analyses_used"], config.MAX_ANALYSES_PER_SESSION)
    if 0 <= left <= 2:
        st.caption(f"이 화면에서 분석은 {left}번 더 할 수 있어요.")

    diffs = "".join(f"<li>{esc(d)}</li>" for d in DIFFS)
    st.html(f'<div class="bn-card"><h4>ChatGPT·에브리타임과 다른 점</h4><ul class="bn-diff">{diffs}</ul></div>'
            + _preview_html()
            + f'<div class="bn-box bn-box-ok"><div class="bn-box-t">실제 수업으로 확인</div><p>{esc(REAL_CHECK)}</p></div>'
            + f'<div class="bn-box bn-box-nf"><p>{esc(NOTICE)}</p></div>')

    st.subheader("내 자료로 하기")
    file = st.file_uploader(f"강의자료 (PDF, PPTX · 최대 {config.MAX_MATERIAL_MB}MB)", type=["pdf", "pptx"],
                            key="w_material")
    if file is not None:
        st.caption(f"{file.name} · {file.size / 1024 / 1024:.1f}MB")
    tab_audio, tab_paste = st.tabs(["녹음 파일", "대본 붙여넣기"])
    with tab_audio:
        stt_ok = stt.available()
        audio = st.file_uploader(f"녹음 파일 (m4a, mp3, wav · 최대 {config.MAX_AUDIO_MB}MB)",
                                 type=["m4a", "mp3", "wav"], max_upload_size=config.MAX_AUDIO_MB,
                                 disabled=not stt_ok, key="w_audio")
        if not stt_ok:
            st.caption("지금은 녹음 받아쓰기를 쓸 수 없어요. 대본 붙여넣기를 써 주세요.")
        st.caption("교수님 허락을 받은 녹음만, 개인 학습 목적으로만 올려 주세요.")
    with tab_paste:
        pasted = st.text_area("받아쓴 대본", height=160, key="w_paste",
                              placeholder="녹음을 받아쓴 글을 붙여넣어 주세요. 비워 두면 자료만으로 계산해요.")
    st.caption("녹음과 대본이 없어도 분석할 수 있어요(녹음 신호만 빠져요). 둘 다 있으면 붙여넣은 대본을 써요.")
    if st.button("분석 시작", type="primary", width="stretch", key="w_analyze",
                 disabled=file is None or not has_key):
        analyze(file, audio, pasted or "")
    st.caption(SEND_NOTE)
