import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from db.database import init_db
from web.routes import api, pages
from utils.logger import setup_custom_logger

logger = setup_custom_logger("WebApp", log_prefix="web")

app = FastAPI(title="M-Market 가격 비교", version="1.0.0")

app.include_router(pages.router)
app.include_router(api.router)


@app.on_event("startup")
async def startup():
    init_db()
    from crawler.runner import sync_markets_from_json
    sync_markets_from_json()
    logger.info("M-Market 서버 시작")
