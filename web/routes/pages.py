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
    products_raw = repo.get_products_by_category(category)

    grouped: dict[str, list] = {}
    for p in products_raw:
        grouped.setdefault(p["name"], []).append(p)

    return templates.TemplateResponse(request, "index.html", {
        "categories": categories,
        "current_category": category,
        "grouped_products": sorted(grouped.items()),
    })


@router.get("/product/{product_name}", response_class=HTMLResponse)
def product_detail(request: Request, product_name: str, category: str = "vegetable", days: int = 90):
    categories = repo.get_categories()
    all_products = repo.get_products_by_category(category)
    matched = [p for p in all_products if p["name"] == product_name]

    product_ids = list({p["id"] for p in matched})
    history = repo.get_price_history_multi(product_ids, days=days)

    return templates.TemplateResponse(request, "detail.html", {
        "categories": categories,
        "product_name": product_name,
        "current_category": category,
        "matched_products": matched,
        "history": history,
        "days": days,
    })


@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    markets = repo.get_markets(active_only=False)
    categories = repo.get_categories()
    return templates.TemplateResponse(request, "admin.html", {
        "markets": markets,
        "categories": categories,
    })
