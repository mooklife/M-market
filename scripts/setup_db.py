"""DB 초기화 스크립트 — 최초 1회 실행"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.database import init_db
from crawler.runner import sync_markets_from_json

if __name__ == "__main__":
    init_db()
    sync_markets_from_json()
    print("DB 초기화 및 마켓 동기화 완료")
