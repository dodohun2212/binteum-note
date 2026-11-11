"""화면(screens)과 내려받기(export)가 함께 쓰는 HTML 도우미.

이스케이프, 문단, 배지, 상태 색, 주의 문구, 한국 날짜를 한 곳에 둔다.
"""
import html as _html
import re
from datetime import datetime, timedelta, timezone

NOTICE = "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다."
NOTICE_END = "이 결과는 자료와 녹음의 신호를 규칙대로 더한 것으로, 실제 출제를 보장하지 않습니다."
SCORE_NOTE = (
    "출제 가능성 점수는 자료와 녹음의 신호를 정해진 규칙(가중치 v0)으로 더해, "
    "가장 높은 개념을 100점으로 맞춘 비교용 점수예요. 확률이 아니며 실제 출제를 보장하지 않습니다."
)
NO_EXPLAIN_HINT = "보완 설명은 앱 ④에서 '설명 보기'로 만들 수 있어요."
NOT_FOUND_LABEL = "올린 자료에서 찾지 못함"
NOT_FOUND_TIP = "교재 다른 장이나 수업 노트를 확인하세요."

KST = timezone(timedelta(hours=9))
MARKS = "①②③④"
STATUS_KIND = {"앎": "ok", "헷갈림": "warn", "모름": "bad", "진단 안 함": "mute"}


def kst_today(now=None):
    """한국 날짜. 배포 서버는 UTC라 그대로 쓰면 오전 9시 전에 전날이 된다."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(KST).date()


def esc(s) -> str:
    """본문 글 이스케이프. 작은따옴표는 그대로 둔다."""
    return _html.escape("" if s is None else str(s), quote=False)


def mark(i: int) -> str:
    """보기 번호 ①~④."""
    return MARKS[i] if 0 <= i < 4 else "?"


def eul(i: int) -> str:
    """①을·②를·③을·④를"""
    return mark(i) + ("을" if i in (0, 2) else "를")


def ieyo(i: int) -> str:
    """①이에요·②예요·③이에요·④예요"""
    return mark(i) + ("이에요" if i in (0, 2) else "예요")


def badge(text, kind: str = "plain") -> str:
    return f'<span class="bn-badge bn-{kind}">{esc(text)}</span>'


STATUS_SHOWN = {"진단 안 함": "아직 확인 안 함"}   # 화면 표시만 바꾼다(문제를 내지 않은 개념)


def status_badge(status: str) -> str:
    return badge(STATUS_SHOWN.get(status, status), STATUS_KIND.get(status, "mute"))


_CITE = re.compile(r"\((p\.[^()]{0,40})\)")


def rich(text) -> str:
    """이스케이프한 뒤 (p.n)은 페이지 배지로, (녹음)은 녹음 배지로 바꾼다."""
    out = esc(text)

    def chip(m):
        nums = re.findall(r"\d+", m.group(1))
        if not nums:
            return m.group(0)
        return "".join(f'<span class="bn-chip">p.{n}</span>' for n in nums)

    out = _CITE.sub(chip, out)
    return out.replace("(녹음)", '<span class="bn-chip bn-rec">녹음</span>')


def paragraphs(text) -> str:
    """빈 줄로 나눈 문단을 <p>로."""
    parts = [p.strip() for p in re.split(r"\n\s*\n", str(text or "")) if p.strip()]
    return "".join(f"<p>{rich(p).replace(chr(10), '<br>')}</p>" for p in parts)


def page_chips(pages) -> str:
    return "".join(f'<span class="bn-chip">p.{int(n)}</span>' for n in pages or [])


def bar(pct, kind: str = "blue") -> str:
    pct = max(0, min(100, int(pct or 0)))
    return f'<span class="bn-bar"><span class="bn-bar-in bn-bar-{kind}" style="width:{pct}%"></span></span>'


def numrow(items) -> str:
    """숫자 칸을 한 줄(flex, 줄바꿈 없음)로. items = [(이름, 값, 종류)]."""
    cells = []
    for it in items:
        label, value = it[0], it[1]
        kind = it[2] if len(it) > 2 else "plain"
        cells.append(
            f'<div class="bn-num bn-num-{kind}"><div class="bn-num-v">{esc(value)}</div>'
            f'<div class="bn-num-l">{esc(label)}</div></div>'
        )
    return f'<div class="bn-numrow">{"".join(cells)}</div>'


def box(inner_html: str, kind: str = "info", title: str = "") -> str:
    head = f'<div class="bn-box-t">{esc(title)}</div>' if title else ""
    return f'<div class="bn-box bn-box-{kind}">{head}{inner_html}</div>'


# 화면과 내려받는 파일이 같이 쓰는 모양. 밝은 바탕 기준의 고정 색.
BASE_CSS = """
.bn-badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.8rem;line-height:1.5;
  margin:2px 4px 2px 0;border:1px solid #d1d5db;background:#f3f4f6;color:#374151;white-space:nowrap}
.bn-ok{background:#dcfce7;border-color:#86efac;color:#166534}
.bn-warn{background:#fef9c3;border-color:#fde047;color:#854d0e}
.bn-bad{background:#fee2e2;border-color:#fca5a5;color:#991b1b}
.bn-mute{background:#f3f4f6;border-color:#d1d5db;color:#6b7280}
.bn-blue{background:#dbeafe;border-color:#93c5fd;color:#1e40af}
.bn-neg{background:#f3f4f6;border-color:#e5e7eb;color:#9ca3af;text-decoration:line-through}
.bn-chip{display:inline-block;padding:0 7px;border-radius:6px;font-size:.78rem;margin:0 2px;
  background:#dbeafe;color:#1e40af;border:1px solid #bfdbfe;white-space:nowrap;vertical-align:1px}
.bn-rec{background:#ede9fe;color:#5b21b6;border-color:#ddd6fe}
.bn-bar{display:inline-block;width:100%;height:9px;border-radius:6px;background:#e5e7eb;overflow:hidden;vertical-align:middle}
.bn-bar-in{display:block;height:100%;border-radius:6px}
.bn-bar-blue{background:#2563eb}.bn-bar-red{background:#dc2626}.bn-bar-gray{background:#9ca3af}
.bn-numrow{display:flex;flex-wrap:nowrap;gap:8px;margin:10px 0 14px}
.bn-num{flex:1 1 0;min-width:0;border:1px solid #e5e7eb;border-radius:12px;padding:10px 6px;text-align:center;background:#fff}
.bn-num-v{font-size:1.55rem;font-weight:700;color:#111827;line-height:1.2}
.bn-num-l{font-size:.82rem;color:#6b7280;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bn-num-ok .bn-num-v{color:#15803d}.bn-num-warn .bn-num-v{color:#a16207}.bn-num-bad .bn-num-v{color:#b91c1c}
.bn-num-blue .bn-num-v{color:#1d4ed8}
.bn-card{border:1px solid #e5e7eb;border-radius:14px;padding:14px 16px;margin:10px 0;background:#fff;color:#111827}
.bn-card h4{margin:0 0 6px;font-size:1.08rem}
.bn-card p{margin:.45em 0}
.bn-q{font-size:1.06rem;font-weight:600;margin:8px 0;white-space:pre-wrap}
.bn-box{border-left:4px solid #93c5fd;background:#eff6ff;border-radius:8px;padding:9px 13px;margin:9px 0;color:#111827}
.bn-box p{margin:.35em 0}
.bn-box-t{font-weight:700;margin-bottom:3px}
.bn-box-gap{border-color:#f87171;background:#fef2f2}
.bn-box-reply{border-color:#3b82f6;background:#eff6ff}
.bn-box-nf{border-color:#facc15;background:#fefce8}
.bn-box-ans{border-color:#9ca3af;background:#f9fafb}
.bn-box-ok{border-color:#4ade80;background:#f0fdf4}
.bn-row{display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid #f1f5f9;flex-wrap:wrap}
.bn-row-rank{width:1.8em;font-weight:700;color:#6b7280;flex:0 0 auto}
.bn-row-name{flex:1 1 7em;min-width:0;font-weight:600}
.bn-row-bar{flex:1 1 3em;min-width:3em}
.bn-row-pct{flex:0 0 auto;font-weight:700;color:#1d4ed8;min-width:3.2em;text-align:right}
.bn-row-badges{flex:1 1 100%;padding-left:1.8em}
.bn-dim{opacity:.55}
.bn-choice{padding:5px 10px;border-radius:8px;margin:3px 0;border:1px solid #e5e7eb}
.bn-choice-ok{background:#dcfce7;border-color:#86efac}
.bn-choice-bad{background:#fee2e2;border-color:#fca5a5}
.bn-fig{margin:8px 0;overflow-x:auto}
.bn-fig img{max-width:100%;height:auto}
.bn-fig table{border-collapse:collapse;background:#fff;color:#111827}
.bn-fig td,.bn-fig th{border:1px solid #9ca3af;padding:4px 10px;text-align:center;font-size:.95rem}
.bn-fig th{background:#eff6ff}
.bn-fig .bn-idx td{border:none;color:#6b7280;font-size:.78rem;padding:1px 10px}
.bn-fig-cap{font-size:.85rem;color:#6b7280;margin-bottom:3px}
.bn-scroll{overflow-x:auto}
.bn-table{border-collapse:collapse;width:100%;font-size:.92rem}
.bn-table th,.bn-table td{border-bottom:1px solid #e5e7eb;padding:6px 8px;text-align:left;vertical-align:middle}
.bn-table th{background:#f9fafb;white-space:nowrap}
.bn-small{font-size:.86rem;color:#6b7280}
.bn-red{color:#b91c1c;font-weight:600}
"""
