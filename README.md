# M-Market 가격 비교 시스템

한국 온라인 마켓(마켓컬리·쿠팡·이마트몰·롯데마트몰·오아시스)의 야채 가격을 자동 수집해
웹에서 마켓별 가격을 한눈에 비교하고, 90일 가격 추세를 차트로 제공합니다.

> 설계 상세: [PROJECT.md](PROJECT.md)

---

## 설치

### 1. 가상환경 및 패키지 설치

```bash
cd M-market
python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt

# Playwright 브라우저 설치 (최초 1회)
playwright install chromium
```

### 2. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일을 열어 로그인이 필요한 마켓의 ID/PW 입력
```

### 3. DB 초기화

```bash
python scripts/setup_db.py
```

---

## 실행

### 웹 서버 시작

```bash
uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload
```

브라우저에서 `http://localhost:8000` 접속.

### 크롤링 수동 실행

```bash
# 야채 전체 마켓
python scripts/crawl.py

# 카테고리 지정
python scripts/crawl.py --category vegetable

# 특정 마켓만
python scripts/crawl.py --market kurly,coupang

# 과일, 특정 마켓
python scripts/crawl.py --category fruit --market kurly
```

---

## crontab 설정 예시

```bash
crontab -e
```

```cron
# 매일 오전 7시 야채 크롤링
0 7 * * * /path/to/M-market/.venv/bin/python /path/to/M-market/scripts/crawl.py >> /path/to/M-market/logs/cron.log 2>&1

# 매일 오전 6시, 오후 6시 크롤링 (하루 2회)
0 6,18 * * * /path/to/M-market/.venv/bin/python /path/to/M-market/scripts/crawl.py
```

---

## 마켓 추가 방법

1. `config/markets.json` 에 새 마켓 항목 추가:
```json
{
    "name": "홈플러스몰",
    "url": "https://mfront.homeplus.co.kr",
    "crawler_key": "homeplus",
    "is_active": true,
    "login_required": false
}
```

2. `crawler/homeplus.py` 파일 생성 (`BaseCrawler` 상속, `_fetch_products` 구현)

3. DB 동기화:
```bash
python scripts/setup_db.py
```

---

## 웹 화면 구성

| 경로 | 내용 |
|---|---|
| `/` | 야채/과일/식료품 품목별 마켓 현재가 비교 |
| `/product/{품목명}` | 90일 마켓별 가격 추세 차트 |
| `/admin` | 마켓 활성화/비활성화, 수동 크롤링 트리거 |

---

## 프로젝트 구조 요약

```
M-market/
├── config/          설정 파일 (markets.json, settings.py)
├── crawler/         마켓별 크롤러 (Playwright 기반)
├── db/              SQLite DB 레이어
├── web/             FastAPI 웹 서버 + 템플릿
├── utils/           로거, KST 시각 유틸
├── scripts/         setup_db.py, crawl.py
└── data/            market.db (gitignore)
```
