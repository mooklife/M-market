import json
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Optional

from config.settings import RETENTION_DAYS
from db.database import get_db
from utils.datetime_utils import get_kst_now, get_kst_now_str
from utils.logger import setup_custom_logger

logger = setup_custom_logger("Repository", log_prefix="db")


# ── 마켓 ──────────────────────────────────────────────────────────────────────

def get_markets(active_only: bool = True) -> list[dict]:
    query = "SELECT * FROM markets"
    if active_only:
        query += " WHERE is_active = 1"
    with get_db() as conn:
        rows = conn.execute(query).fetchall()
    return [dict(r) for r in rows]


def upsert_market(name: str, url: str, crawler_key: str,
                  is_active: bool = True, login_required: bool = False) -> int:
    now = get_kst_now_str()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO markets (name, url, crawler_key, is_active, login_required, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(crawler_key) DO UPDATE SET
                   name=excluded.name, url=excluded.url,
                   is_active=excluded.is_active, login_required=excluded.login_required""",
            (name, url, crawler_key, int(is_active), int(login_required), now),
        )
        row = conn.execute("SELECT id FROM markets WHERE crawler_key = ?", (crawler_key,)).fetchone()
    return row["id"]


def set_market_active(crawler_key: str, is_active: bool) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE markets SET is_active = ? WHERE crawler_key = ?",
            (int(is_active), crawler_key),
        )


# ── 카테고리 ──────────────────────────────────────────────────────────────────

def get_categories() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM categories").fetchall()
    return [dict(r) for r in rows]


def get_category_id(key: str) -> Optional[int]:
    with get_db() as conn:
        row = conn.execute("SELECT id FROM categories WHERE key = ?", (key,)).fetchone()
    return row["id"] if row else None


def get_category(key: str) -> Optional[dict]:
    """id, key, name, search_keyword 반환"""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM categories WHERE key = ?", (key,)).fetchone()
    return dict(row) if row else None


def update_category_keyword(key: str, search_keyword: str) -> None:
    """카테고리 검색어 변경"""
    with get_db() as conn:
        conn.execute(
            "UPDATE categories SET search_keyword = ? WHERE key = ?",
            (search_keyword, key),
        )


# ── 추적 품목 ─────────────────────────────────────────────────────────────────

def get_search_items(category_key: str, active_only: bool = True) -> list[dict]:
    """카테고리별 추적 품목 목록 (예: 양파, 당근, ...)"""
    query = """SELECT si.id, si.name, si.is_active, si.sort_order, c.key AS category_key
               FROM search_items si
               JOIN categories c ON si.category_id = c.id
               WHERE c.key = ?"""
    if active_only:
        query += " AND si.is_active = 1"
    query += " ORDER BY si.sort_order, si.name"
    with get_db() as conn:
        rows = conn.execute(query, (category_key,)).fetchall()
    return [dict(r) for r in rows]


def add_search_item(category_key: str, name: str) -> int:
    cat = get_category(category_key)
    if cat is None:
        raise ValueError(f"카테고리 '{category_key}' 없음")
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO search_items (category_id, name) VALUES (?, ?)",
            (cat["id"], name.strip()),
        )
        row = conn.execute(
            "SELECT id FROM search_items WHERE category_id=? AND name=?",
            (cat["id"], name.strip()),
        ).fetchone()
    return row["id"]


def toggle_search_item(item_id: int, is_active: bool) -> None:
    with get_db() as conn:
        conn.execute("UPDATE search_items SET is_active=? WHERE id=?", (int(is_active), item_id))


def delete_search_item(item_id: int) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM search_items WHERE id=?", (item_id,))


# ── 대표 상품 ─────────────────────────────────────────────────────────────────

def upsert_standard_product(search_item_id: int, category_id: int,
                             product_type: str, product_state: str) -> int:
    """(search_item_id, product_type, product_state) 조합으로 대표 상품을 생성/조회."""
    display_name = f"{product_state} {product_type}" if product_state != "일반" else product_type
    with get_db() as conn:
        conn.execute(
            """INSERT INTO standard_products
                   (category_id, search_item_id, product_type, product_state, display_name)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(search_item_id, product_type, product_state) DO UPDATE SET
                   display_name=excluded.display_name""",
            (category_id, search_item_id, product_type, product_state, display_name),
        )
        row = conn.execute(
            """SELECT id FROM standard_products
               WHERE search_item_id=? AND product_type=? AND product_state=?""",
            (search_item_id, product_type, product_state),
        ).fetchone()
    return row["id"]


# ── 상품 ──────────────────────────────────────────────────────────────────────

def upsert_product(market_id: int, category_id: int, search_item_id: int,
                   name: str, unit: Optional[str], product_url: Optional[str],
                   weight_g: Optional[int] = None, unit_price: Optional[float] = None,
                   product_type: Optional[str] = None, product_state: Optional[str] = None,
                   standard_id: Optional[int] = None, image_url: Optional[str] = None) -> int:
    now = get_kst_now_str()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO products
                   (market_id, category_id, search_item_id, name, unit, product_url, created_at,
                    weight_g, unit_price, product_type, product_state, standard_id, image_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(market_id, search_item_id, name, unit) DO UPDATE SET
                   product_url=excluded.product_url,
                   search_item_id=excluded.search_item_id,
                   weight_g=excluded.weight_g,
                   unit_price=excluded.unit_price,
                   product_type=excluded.product_type,
                   product_state=excluded.product_state,
                   standard_id=excluded.standard_id,
                   image_url=excluded.image_url""",
            (market_id, category_id, search_item_id, name, unit, product_url, now,
             weight_g, unit_price, product_type, product_state, standard_id, image_url),
        )
        row = conn.execute(
            """SELECT id FROM products
               WHERE market_id=? AND search_item_id=? AND name=? AND unit IS ?""",
            (market_id, search_item_id, name, unit),
        ).fetchone()
    return row["id"]


def get_items_with_latest_prices(category_key: str) -> list[dict]:
    """품목별 + 마켓별 최신 가격 (메인 화면용)"""
    with get_db() as conn:
        items = conn.execute(
            """SELECT si.id, si.name, si.sort_order
               FROM search_items si
               JOIN categories c ON si.category_id = c.id
               WHERE c.key = ? AND si.is_active = 1
               ORDER BY si.sort_order, si.name""",
            (category_key,),
        ).fetchall()

        result = []
        for item in items:
            market_rows = conn.execute(
                """SELECT p.id AS product_id, p.name AS product_name, p.unit, p.product_url,
                          p.weight_g, p.unit_price, p.product_type, p.product_state, p.standard_id,
                          p.image_url,
                          m.name AS market_name, m.crawler_key,
                          ph.sale_price, ph.original_price, ph.discount_rate, ph.collected_at
                   FROM products p
                   JOIN markets m ON p.market_id = m.id
                   LEFT JOIN price_history ph ON ph.id = (
                       SELECT id FROM price_history
                       WHERE product_id = p.id
                       ORDER BY collected_at DESC LIMIT 1
                   )
                   WHERE p.search_item_id = ? AND m.is_active = 1
                   ORDER BY ph.sale_price ASC""",
                (item["id"],),
            ).fetchall()

            # 마켓당 최저가 1개만
            by_market: dict[str, dict] = {}
            for row in market_rows:
                r = dict(row)
                mname = r["market_name"]
                if mname not in by_market:
                    by_market[mname] = r
                elif r["sale_price"] and (
                    not by_market[mname]["sale_price"]
                    or r["sale_price"] < by_market[mname]["sale_price"]
                ):
                    by_market[mname] = r

            result.append({
                "item_id": item["id"],
                "item_name": item["name"],
                "markets": list(by_market.values()),
            })
    return result


def get_products_by_category(category_key: str) -> list[dict]:
    """카테고리별 상품 목록 (레거시 — api.py 호환용)"""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT p.id, p.name, p.unit, p.product_url,
                      si.name AS item_name,
                      m.name AS market_name, m.crawler_key,
                      ph.sale_price, ph.original_price, ph.discount_rate, ph.collected_at
               FROM products p
               JOIN markets m ON p.market_id = m.id
               JOIN categories c ON p.category_id = c.id
               LEFT JOIN search_items si ON p.search_item_id = si.id
               LEFT JOIN price_history ph ON ph.id = (
                   SELECT id FROM price_history
                   WHERE product_id = p.id
                   ORDER BY collected_at DESC LIMIT 1
               )
               WHERE c.key = ? AND m.is_active = 1
               ORDER BY si.sort_order, si.name, m.name""",
            (category_key,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_product_ids_by_search_item(search_item_id: int) -> list[int]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id FROM products WHERE search_item_id = ?", (search_item_id,)
        ).fetchall()
    return [r["id"] for r in rows]


def get_product_by_id(product_id: int) -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute(
            """SELECT p.*, m.name AS market_name, c.name AS category_name
               FROM products p
               JOIN markets m ON p.market_id = m.id
               JOIN categories c ON p.category_id = c.id
               WHERE p.id = ?""",
            (product_id,),
        ).fetchone()
    return dict(row) if row else None


# ── 가격 이력 ─────────────────────────────────────────────────────────────────

def insert_price(product_id: int, original_price: Optional[int],
                 discount_rate: float, sale_price: int) -> None:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO price_history (product_id, collected_at, original_price, discount_rate, sale_price)
               VALUES (?, ?, ?, ?, ?)""",
            (product_id, get_kst_now_str(), original_price, discount_rate, sale_price),
        )


def get_price_history(product_id: int, days: int = RETENTION_DAYS) -> list[dict]:
    cutoff = (get_kst_now() - timedelta(days=days)).isoformat()
    with get_db() as conn:
        rows = conn.execute(
            """SELECT collected_at, original_price, discount_rate, sale_price
               FROM price_history
               WHERE product_id = ? AND collected_at >= ?
               ORDER BY collected_at ASC""",
            (product_id, cutoff),
        ).fetchall()
    return [dict(r) for r in rows]


def get_price_history_multi(product_ids: list[int], days: int = RETENTION_DAYS) -> list[dict]:
    """여러 product_id의 가격 이력 (차트용 — 마켓별 선 그리기)"""
    if not product_ids:
        return []
    cutoff = (get_kst_now() - timedelta(days=days)).isoformat()
    placeholders = ",".join("?" * len(product_ids))
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT ph.product_id, ph.collected_at, ph.sale_price,
                       p.name, p.unit, m.name AS market_name
                FROM price_history ph
                JOIN products p ON ph.product_id = p.id
                JOIN markets m ON p.market_id = m.id
                WHERE ph.product_id IN ({placeholders}) AND ph.collected_at >= ?
                ORDER BY ph.collected_at ASC""",
            (*product_ids, cutoff),
        ).fetchall()
    return [dict(r) for r in rows]


# ── 90일 초과 데이터 정리 ─────────────────────────────────────────────────────

def purge_old_prices() -> int:
    cutoff = (get_kst_now() - timedelta(days=RETENTION_DAYS)).isoformat()
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM price_history WHERE collected_at < ?", (cutoff,)
        )
    deleted = cursor.rowcount
    if deleted > 0:
        logger.info(f"90일 초과 가격 이력 {deleted}건 삭제")
    return deleted
