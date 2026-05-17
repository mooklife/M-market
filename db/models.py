# 테이블명 및 컬럼명 상수 — SQL 문자열 직접 기재 금지, 이 상수만 사용

TBL_CATEGORIES = "categories"
TBL_MARKETS = "markets"
TBL_SEARCH_ITEMS = "search_items"
TBL_PRODUCTS = "products"
TBL_PRICE_HISTORY = "price_history"

DDL_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS categories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    key             TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    search_keyword  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS markets (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    url            TEXT NOT NULL,
    crawler_key    TEXT UNIQUE NOT NULL,
    is_active      INTEGER DEFAULT 1,
    login_required INTEGER DEFAULT 0,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS search_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL,
    name        TEXT NOT NULL,
    is_active   INTEGER DEFAULT 1,
    sort_order  INTEGER DEFAULT 0,
    FOREIGN KEY (category_id) REFERENCES categories(id),
    UNIQUE (category_id, name)
);

CREATE TABLE IF NOT EXISTS products (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id      INTEGER NOT NULL,
    category_id    INTEGER NOT NULL,
    search_item_id INTEGER,
    name           TEXT NOT NULL,
    unit           TEXT,
    product_url    TEXT,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (market_id)      REFERENCES markets(id),
    FOREIGN KEY (category_id)    REFERENCES categories(id),
    FOREIGN KEY (search_item_id) REFERENCES search_items(id),
    UNIQUE (market_id, search_item_id, name, unit)
);

CREATE TABLE IF NOT EXISTS price_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id     INTEGER NOT NULL,
    collected_at   TEXT NOT NULL,
    original_price INTEGER,
    discount_rate  REAL DEFAULT 0.0,
    sale_price     INTEGER NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE INDEX IF NOT EXISTS idx_price_history_product_date
    ON price_history (product_id, collected_at DESC);
"""

# (key, name, search_keyword)
SEED_CATEGORIES = [
    ("vegetable", "야채",   "야채"),
    ("fruit",     "과일",   "과일"),
    ("grocery",   "식료품", "식료품"),
]
