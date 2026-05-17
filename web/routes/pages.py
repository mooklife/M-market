from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from db import repository as repo

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
def index(request: Request, category: str = "vegetable"):
    categories = repo.get_categories()
    items_with_prices = repo.get_items_with_latest_prices(category)
    return templates.TemplateResponse(request, "index.html", {
        "categories": categories,
        "current_category": category,
        "items_with_prices": items_with_prices,
    })


@router.get("/item/{item_id}", response_class=HTMLResponse)
def item_detail(request: Request, item_id: int, category: str = "vegetable", days: int = 90):
    categories = repo.get_categories()

    # 품목 정보
    items = repo.get_search_items(category, active_only=False)
    item = next((i for i in items if i["id"] == item_id), None)

    # 마켓별 최신가
    all_items = repo.get_items_with_latest_prices(category)
    item_data = next((i for i in all_items if i["item_id"] == item_id), None)

    # 가격 이력
    product_ids = repo.get_product_ids_by_search_item(item_id)
    history = repo.get_price_history_multi(product_ids, days=days)

    return templates.TemplateResponse(request, "detail.html", {
        "categories": categories,
        "current_category": category,
        "item": item,
        "item_data": item_data,
        "history": history,
        "days": days,
    })


@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request, category: str = "vegetable"):
    markets = repo.get_markets(active_only=False)
    categories = repo.get_categories()
    search_items = repo.get_search_items(category, active_only=False)
    return templates.TemplateResponse(request, "admin.html", {
        "markets": markets,
        "categories": categories,
        "current_category": category,
        "search_items": search_items,
    })
