# CLAUDE.md — my-trading-agent 개발 정책

> **모든 노트북 / 모든 AI 모델(Claude, GPT-4o 등)에서 공통 적용**
> VS Code Copilot이 이 파일을 자동으로 읽어 지시에 따릅니다.

---

## 1. 수정 원칙 (Surgical Changes)

- **요청한 부분만 수정한다.** 인접 코드, 주석, 포맷을 건드리지 않는다.
- **import 문은 반드시 파일 최상단**(모듈 레벨)에만 추가한다.
  - 함수 내부 import는 순환참조 회피 목적일 때만 허용.
  - **절대로 함수 블록 사이에 module-level import를 삽입하지 않는다.**
- 변경 전 반드시 해당 파일의 현재 내용을 확인한다.
- 관련 없는 dead code, 스타일, 리팩토링은 언급만 하고 건드리지 않는다.

---

## 2. Python 파일 작성 규칙

### 2-1. import 순서 (파일 최상단, 이 순서 준수)
```python
# 1. 표준 라이브러리
import os, sys, json, asyncio, math
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 2. 서드파티
from dotenv import load_dotenv
import requests

# 3. 내부 유틸/엔진 (BASE_DIR sys.path 설정 후)
from utils.logger import setup_custom_logger
from utils.datetime_utils import get_kst_now, get_kst_now_str
from engine.data_fetcher import DataFetcher
from config.settings import ...
```

### 2-2. 자주 실수하는 패턴 — 절대 금지
```python
# ❌ 잘못된 예: 함수 블록 사이에 module import 삽입
def some_func():
    from engine.account_abroad import AccountManagerAbroad
from utils.datetime_utils import get_kst_now  # ← 절대 금지 (들여쓰기 없이 끼어든 import)
    result = AccountManagerAbroad().get_account_summary()

# ✅ 올바른 예
from utils.datetime_utils import get_kst_now  # 파일 최상단

def some_func():
    from engine.account_abroad import AccountManagerAbroad  # 순환참조 회피용만 허용
    result = AccountManagerAbroad().get_account_summary()
```


### 2-4. 로거
```python
logger = setup_custom_logger("ModuleName", log_prefix="log_filename")
# print() 사용 금지 (디버그 임시 제외)
```

### 2-5. 코드 스타일
- 들여쓰기: **4 spaces** (탭 금지)
- 줄 길이: 120자 이하 권장
- 문자열: `f-string` 우선, `%` 포맷 금지
- `None` 체크: `if x is None` (not `if not x`)
- 타입 힌트 권장: 함수 인자/반환값에 명시

---

## 3. 설정값 소스 통일

| 설정 항목 | 소스 | 접근 방법 |
|---|---|---|
| 거래 파라미터 | `config/trading.json` | 런타임에 매번 직접 읽기 (모듈 상수 금지) |
| API 키, 토큰 | `.env` | `os.getenv("KEY")` |
| 종목 규칙 | `config/3_RAB_KR.json` | `load_rules_auto_buy()` 통해서만 접근 |
| KIS 설정 | `config/settings.py` | `from config.settings import ...` |
| KST 현재 시각 | `utils/datetime_utils.py` | `get_kst_now()`, `get_kst_now_str()` |

## 6. 수정 전 체크리스트

1. **파일 현재 내용 확인** — 이전 세션의 수정이 이미 반영됐을 수 있음
2. **에러 라인 번호 확인** — 에러 로그의 라인 번호로 정확한 위치 파악
3. **구문 검사** — 수정 후 `python3 -m py_compile <파일>` 통과 여부
4. **연관 파일 체크** — 함수 시그니처 변경 시 모든 호출부 함께 수정
5. **trading.json 키 추가 시** — 이 문서 섹션 3의 키 목록도 함께 업데이트

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
