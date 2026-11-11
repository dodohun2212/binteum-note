"""빈틈노트: 페이지 설정, CSS, 예전 모듈 버리기, 사이드바, 화면 고르기만 한다."""
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent


def _file_times() -> dict:
    """코드 모듈과 프롬프트 파일의 수정 시각."""
    modules = [ROOT / "config.py"] + sorted((ROOT / "core").glob("*.py")) + sorted((ROOT / "screens").glob("*.py"))
    prompts = sorted((ROOT / "prompts").glob("*.md"))
    return {"modules": {p.name + "@" + p.parent.name: p.stat().st_mtime for p in modules},
            "prompts": {p.name: p.stat().st_mtime for p in prompts}}


def _drop_stale_modules() -> None:
    """재배포 뒤 예전 core·screens·config 모듈과 서버 공용 캐시를 버린다.

    Streamlit Cloud는 새 코드를 받아도 app.py만 다시 실행하고 이미 불러온 모듈은 예전 것을 쓴다.
    프롬프트 파일만 바뀌어도(또는 지난 기록이 없어도) 새로 읽게 한다.
    """
    from core.guard import needs_reload

    now = _file_times()
    previous = getattr(sys, "_bintm_file_times", None)
    if needs_reload(previous, now):
        for name in list(sys.modules):
            if name == "config" or name.split(".")[0] in ("core", "screens"):
                del sys.modules[name]
        st.cache_resource.clear()
    sys._bintm_file_times = now


st.set_page_config(page_title="빈틈노트", page_icon="📝", layout="centered")
_drop_stale_modules()

import config  # noqa: E402
from core import llm  # noqa: E402
from core.html import BASE_CSS  # noqa: E402
from screens import common, s01, s02, s03, s04, s05  # noqa: E402

APP_CSS = """
.block-container{max-width:860px;padding-top:4.5rem;padding-left:1rem;padding-right:1rem;padding-bottom:5rem}
.stMarkdown p,.stMarkdown li{font-size:17px;line-height:1.75}
.bn-steps{font-size:.85rem;color:#6b7280;margin-bottom:2px;line-height:1.6}
.bn-step-on{color:#1d4ed8;font-weight:700}
.bn-title{font-size:1.9rem;margin:.05em 0;line-height:1.25;padding:0}
.bn-sub{font-size:1.04rem;color:#374151;margin:0 0 .3em;line-height:1.55}
.bn-diff{margin:.2em 0 .6em 0;padding:0 0 0 1.2em}
.bn-diff li{margin:.35em 0;line-height:1.6}
textarea,.stRadio label p,.stCheckbox label p,.stTextArea label p{font-size:16px !important}
.stRadio label{padding:3px 0}
/* 기다리는 안내는 화면 아래 가운데에 고정해, 아래로 내려 둔 사람도 보게 한다 */
[data-testid="stSpinner"]{position: fixed;bottom:18px;left:50%;transform:translateX(-50%);z-index:9999;
  background:#1e293b;padding:10px 18px;border-radius:999px;box-shadow:0 4px 14px rgba(0,0,0,.25);
  max-width:92vw;width:max-content}
[data-testid="stSpinner"] *{color:#ffffff !important}
@media (max-width:480px){
  .block-container{padding-left:.8rem;padding-right:.8rem}
  .bn-title{font-size:1.55rem}.bn-sub{font-size:.98rem}
  .bn-num-v{font-size:1.3rem}.bn-num-l{font-size:.74rem}
  .bn-card{padding:12px 12px}
}
"""

st.html(f"<style>{BASE_CSS}{APP_CSS}</style>")
common.init_state()
common.load_keys()
ss = st.session_state

# 새로고침 등으로 결과가 사라졌으면 ①로 돌아간다
if ss["step"] in (2, 3, 4) and not ss["scores"]:
    ss["step"] = 1
    ss["errors"].append("새로고침하면 결과가 사라져요. 결과는 ④에서 내보내기로 저장할 수 있어요.")

with st.sidebar:
    st.markdown("### 빈틈노트")
    for n, label in common.STEPS.items():
        if st.button(label, key=f"w_nav_{n}", width="stretch", disabled=not common.can_open(n),
                     type="primary" if ss["step"] == n else "secondary"):
            common.goto(n)
    st.divider()
    if st.button("처음부터", key="w_nav_reset", width="stretch"):
        common.reset_state()
        st.rerun()
    st.caption(f"모델: {config.LLM_MODEL}")
    if llm.is_fake():
        st.caption("가짜 AI 모드")

SCREENS = {1: s01.render, 2: s02.render, 3: s03.render, 4: s04.render, 5: s05.render}
SCREENS[ss["step"]]()
