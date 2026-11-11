LLM_MODEL = "claude-sonnet-5-5"   # 이 한 줄만 바꾸면 모델 교체
STT_MODEL = "whisper-1"           # None이면 음성 인식 끄기(대본 붙여넣기만)
DIAG_MIN_PCT = 20                 # 출제 가능성 점수(0~100, 가장 높은 개념 = 100)가 이 값 이상인 개념은 전부 진단
ESSAY_MIN_PCT = 50                # "섞어서": 이 값 이상 서술형, 미만 객관식
MAX_PAGES = 120                   # 분석할 최대 쪽수
MAX_EVIDENCE_PAGES = 8            # 호출 3, 4, 5에 넣는 근거 쪽 상한
MAX_MATERIAL_MB = 30              # 강의자료 파일 크기 상한
MAX_AUDIO_MB = 25                 # 녹음 파일 크기 상한 (녹음 업로더별 상한으로도 건다)
AUTO_EXPLAIN_TOP = 3              # S04에서 자동으로 설명을 만드는 우선순위 상위 개수 (그 밖에 '지금 당장' 전부와 진단 모름·헷갈림 전부)
AI_MAX_TOKENS = 4000              # 호출 3-A/3-B/3-C/4의 답 길이 상한
NOTE_MAX_TOKENS = 5000            # 호출 5(요약 노트)의 답 길이 상한
CONFUSION_MAX_CHARS = 300         # 헷갈린 점 입력칸 글자 수 상한
MAX_ANALYSES_PER_SESSION = 5      # 세션당 분석 횟수. 0이면 제한 없음
MAX_ANALYSES_PER_DAY = 150        # 서버 전체 하루 분석 횟수. 0이면 제한 없음
QUICK_DIAG_TOP = 5                # "빠른 진단"을 켜면 출제 가능성 상위 몇 개만
QUICK_DIAG_AUTO_OVER = 8          # 직접 올린 자료의 진단 대상이 이보다 많으면 빠른 진단 기본 켜짐 (샘플은 꺼짐)
MAX_AI_CALLS_PER_DAY = 3000       # 서버 전체 하루 AI 호출 수. 0이면 제한 없음

# 화면 안내에 쓰는 값 (사람이 알려 준 값만 적는다)
TEAM_NAME = "빈틈노트"
CONTEST_NAME = "KOREATECH AI 실습형 이벤트 · Build for Students"
REPO_URL = "https://github.com/dodohun2212/binteum-note"
