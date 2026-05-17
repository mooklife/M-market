# PROJECT.md — M-Market 가격 비교 시스템

> **모든 개발 세션에서 이 문서를 참조한다. 구조·스키마·인터페이스 변경 시 반드시 이 문서도 함께 업데이트한다.**

---

## 1. 시스템 개요

한국 온라인 마켓(마켓컬리·쿠팡·이마트몰·롯데마트몰·오아시스)의 야채 가격을 자동 수집해
웹에서 마켓별 가격을 한눈에 비교하고, 90일 가격 추세를 차트로 제공하는 Python+FastAPI 웹 애플리케이션.

---

## 2. 기술 스택

| 역할 | 기술 |
|---|---|
| Backend | Python 3.14 + FastAPI |
| 템플릿 | Jinja2 (서버사이드 렌더링) |
| DB | SQLite (`data/market.db`) — 추후 PostgreSQL 전환 가능 |
| 크롤러 | Playwright (헤드리스, JS 렌더링 대응, 로그인 지원) |
| 차트 | Chart.js (CDN, 빌드 단계 없음) |
| 스케줄러 | crontab 또는 `scripts/crawl.py` 수동 실행 |

---

## 3. 디렉토리 구조

```
M-market/
├── CLAUDE.md
├── PROJECT.md
├── README.md
├── requirements.txt
├── .env                   ← 로컬 전용 (gitignore)
├── .env.example
├── data/
│   └── market.db          ← SQLite DB 파일 (gitignore)
├── config/
│   ├── settings.py        ← BASE_DIR, DB_PATH, 공통 상수
│   └── markets.json       ← 등록 마켓 목록
├── crawler/
│   ├── __init__.py
│   ├── base.py            ← BaseCrawler 추상 클래스
│   ├── kurly.py           ← 마켓컬리
│   ├── coupang.py         ← 쿠팡
│   ├── emart.py           ← 이마트몰
│   ├── lotte.py           ← 롯데마트몰
│   ├── oasis.py           ← 오아시스마켓
│   └── runner.py          ← 크롤링 오케스트레이터
├── db/
│   ├── __init__.py
│   ├── database.py        ← SQLite 연결 / 테이블 초기화
│   ├── models.py          ← 테이블명·컬럼명 상수
│   └── repository.py      ← CRUD
├── web/
│   ├── app.py             ← FastAPI 앱 엔트리포인트
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── api.py         ← REST API (/api/*)
│   │   └── pages.py       ← HTML 페이지 라우트
│   └── templates/
│       ├── base.html
│       ├── index.html     ← 메인: 품목별 마켓 현재가 비교
│       ├── detail.html    ← 상세: 90일 가격 추세 차트
│       └── admin.html     ← 관리: 마켓 설정 / 수동 크롤링
├── utils/
│   ├── logger.py          ← setup_custom_logger
│   └── datetime_utils.py  ← get_kst_now(), get_kst_now_str()
├── scripts/
│   ├── setup_db.py        ← DB 초기화 (최초 1회)
│   └── crawl.py           ← 크롤링 수동 실행 진입점
└── logs/                  ← 로그 파일 디렉토리 (gitignore)
```

---

## 4. DB 스키마

### 4-1. categories (카테고리)

```sql
CREATE TABLE categories (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    key            TEXT UNIQUE NOT NULL,   -- 'vegetable' | 'fruit' | 'grocery'
    name           TEXT NOT NULL,          -- '야채' | '과일' | '식료품'
    search_keyword TEXT NOT NULL DEFAULT ''
);
```

### 4-2. search_items (추적 품목 — 핵심)

카테고리 하위 실제 추적 대상 품목. 크롤러는 이 목록 기준으로 마켓별 검색을 실행한다.

```sql
CREATE TABLE search_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    name        TEXT NOT NULL,       -- '양파', '당근', '무', '가지', '콩나물' …
    is_active   INTEGER DEFAULT 1,
    sort_order  INTEGER DEFAULT 0,
    FOREIGN KEY (category_id) REFERENCES categories(id),
    UNIQUE (category_id, name)
);
```

**초기 데이터**: `config/items.json` 에서 시드. 관리자 화면에서 추가/삭제/활성화 가능.

### 4-3. markets (마켓)

```sql
CREATE TABLE markets (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,        -- '마켓컬리'
    url            TEXT NOT NULL,        -- 'https://www.kurly.com'
    crawler_key    TEXT UNIQUE NOT NULL, -- 'kurly'
    is_active      INTEGER DEFAULT 1,
    login_required INTEGER DEFAULT 0,
    created_at     TEXT NOT NULL
);
```

### 4-4. products (상품)

```sql
CREATE TABLE products (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id      INTEGER NOT NULL,
    category_id    INTEGER NOT NULL,
    search_item_id INTEGER,              -- 어떤 품목 검색으로 수집됐는지
    name           TEXT NOT NULL,
    unit           TEXT,                 -- '1단', '1kg', '500g'
    product_url    TEXT,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (market_id)      REFERENCES markets(id),
    FOREIGN KEY (category_id)    REFERENCES categories(id),
    FOREIGN KEY (search_item_id) REFERENCES search_items(id),
    UNIQUE (market_id, search_item_id, name, unit)
);
```

### 4-5. price_history (가격 이력 — 핵심)

```sql
CREATE TABLE price_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id     INTEGER NOT NULL,
    collected_at   TEXT NOT NULL,    -- KST ISO8601 (날짜만 비교 가능)
    original_price INTEGER,          -- 정가 (원), NULL 허용
    discount_rate  REAL DEFAULT 0.0, -- 0.0 ~ 1.0
    sale_price     INTEGER NOT NULL, -- 실판매가
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE INDEX idx_price_history_product_date
    ON price_history (product_id, collected_at DESC);
```

**90일 보존 정책**: `crawl.py` 실행 시마다 `collected_at < NOW() - 90일` 레코드 자동 삭제.  
1년치 데이터 분석이 필요해질 경우 보존 기간을 `config/settings.py`의 `RETENTION_DAYS`로 조정.

---

## 5. 크롤러 인터페이스

### 5-1. BaseCrawler (crawler/base.py)

```python
class BaseCrawler:
    market_key: str                # crawler_key와 동일
    category_url: dict[str, str]   # {'vegetable': 'https://...'}

    async def crawl(self, category_key: str) -> list[dict]:
        """크롤링 실행 후 상품 목록 반환"""

    async def _fetch_products(self, url: str) -> list[dict]:
        """하위 클래스에서 구현 — Playwright로 페이지 파싱"""
```

### 5-2. 반환 데이터 형식 (통일)

```python
{
    "name": "대파",           # str  — 상품명
    "unit": "1단",            # str  — 단위/용량 (없으면 None)
    "product_url": "https://...", # str  — 상품 직접 링크
    "original_price": 2990,   # int  — 정가 (할인 전), 없으면 None
    "discount_rate": 0.10,    # float — 0.0~1.0 (없으면 0.0)
    "sale_price": 2691        # int  — 실제 판매가 (필수)
}
```

### 5-3. 로그인 처리

- `login_required=1` 마켓: `.env`의 `{CRAWLER_KEY}_ID` / `{CRAWLER_KEY}_PW` 참조
- 예: 쿠팡 → `COUPANG_ID`, `COUPANG_PW`
- Playwright 세션은 크롤러 인스턴스 수명 동안 유지

---

## 6. API 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| GET | `/` | 메인 페이지 (HTML) |
| GET | `/product/{id}` | 상품 상세 페이지 (HTML) |
| GET | `/admin` | 관리 페이지 (HTML) |
| GET | `/api/categories` | 카테고리 목록 |
| GET | `/api/products?category=vegetable` | 품목 목록 (마켓별 최신가 포함) |
| GET | `/api/prices/{product_id}?days=90` | 가격 이력 (차트용) |
| GET | `/api/markets` | 마켓 목록 |
| POST | `/api/crawl` | 수동 크롤링 트리거 |

---

## 7. 설정값 소스 (이 프로젝트)

| 항목 | 소스 | 접근 방법 |
|---|---|---|
| DB 경로 | `config/settings.py` | `from config.settings import DB_PATH` |
| 보존 기간 | `config/settings.py` | `RETENTION_DAYS = 90` |
| 마켓 목록 | `config/markets.json` | `runner.py`가 읽어 크롤러 선택 |
| API 키/로그인 | `.env` | `os.getenv("KURLY_ID")` 등 |
| 카테고리 URL | 각 크롤러 클래스 내 `category_url` dict | 하드코딩 (마켓 구조 변경 시 수정) |

---

## 8. 확장 로드맵

| 단계 | 내용 |
|---|---|
| Phase 1 (현재) | 야채 크롤링 + 90일 추세 웹 표시 |
| Phase 2 | 과일·식료품 카테고리 추가 (categories 레코드 + 크롤러 URL 추가) |
| Phase 3 | 1년치 데이터 → 계절별 가격 분석 차트 |
| Phase 4 | 모바일 웹앱 (PWA) |
| Phase 5 | PostgreSQL 전환 (대용량 시) |
