import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from config.settings import BASE_DIR, DB_PATH
from db.models import DDL_CREATE_TABLES, SEED_CATEGORIES
from utils.logger import setup_custom_logger

logger = setup_custom_logger("Database", log_prefix="db")


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """기존 DB에 누락된 컬럼/테이블을 추가하는 마이그레이션 (멱등)"""
    # categories.search_keyword
    cols = {row[1] for row in conn.execute("PRAGMA table_info(categories)").fetchall()}
    if "search_keyword" not in cols:
        conn.execute("ALTER TABLE categories ADD COLUMN search_keyword TEXT NOT NULL DEFAULT ''")
        logger.info("categories.search_keyword 컬럼 추가")

    # products.search_item_id
    prod_cols = {row[1] for row in conn.execute("PRAGMA table_info(products)").fetchall()}
    if "search_item_id" not in prod_cols:
        conn.execute("ALTER TABLE products ADD COLUMN search_item_id INTEGER REFERENCES search_items(id)")
        logger.info("products.search_item_id 컬럼 추가")


def _seed_search_items(conn: sqlite3.Connection) -> None:
    """config/items.json 에서 search_items 시드 데이터 삽입 (멱등)"""
    items_path = BASE_DIR / "config" / "items.json"
    if not items_path.exists():
        return
    with open(items_path, encoding="utf-8") as f:
        items_map: dict[str, list[str]] = json.load(f)

    for cat_key, names in items_map.items():
        row = conn.execute("SELECT id FROM categories WHERE key = ?", (cat_key,)).fetchone()
        if row is None:
            continue
        cat_id = row[0]
        for order, name in enumerate(names):
            conn.execute(
                """INSERT INTO search_items (category_id, name, is_active, sort_order)
                   VALUES (?, ?, 1, ?)
                   ON CONFLICT(category_id, name) DO NOTHING""",
                (cat_id, name, order),
            )


def init_db() -> None:
    """테이블 생성 및 시드 데이터 삽입 (멱등)"""
    with get_db() as conn:
        conn.executescript(DDL_CREATE_TABLES)
        _migrate(conn)
        for key, name, keyword in SEED_CATEGORIES:
            conn.execute(
                """INSERT INTO categories (key, name, search_keyword) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                       name=excluded.name, search_keyword=excluded.search_keyword""",
                (key, name, keyword),
            )
        _seed_search_items(conn)
    logger.info(f"DB 초기화 완료: {DB_PATH}")
