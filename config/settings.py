import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR / ".env")

DB_PATH = BASE_DIR / "data" / "market.db"
LOG_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"

RETENTION_DAYS = 90  # 가격 이력 보존 기간 (일) — 변경 시 PROJECT.md 섹션 4-4도 업데이트
