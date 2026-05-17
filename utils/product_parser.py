import json
import re
from pathlib import Path
from typing import Optional

from config.settings import BASE_DIR

_RULES_PATH = BASE_DIR / "config" / "product_rules.json"

# (pattern, g 변환 함수) — 먼저 매칭된 것이 우선
_WEIGHT_PATTERNS: list[tuple[re.Pattern, callable]] = [
    (re.compile(r'(\d+(?:\.\d+)?)\s*kg', re.IGNORECASE), lambda m: float(m.group(1)) * 1000),
    (re.compile(r'(\d+(?:\.\d+)?)\s*g\b', re.IGNORECASE), lambda m: float(m.group(1))),
    (re.compile(r'(\d+(?:\.\d+)?)\s*ml\b', re.IGNORECASE), lambda m: float(m.group(1))),
    (re.compile(r'(\d+(?:\.\d+)?)\s*l\b', re.IGNORECASE), lambda m: float(m.group(1)) * 1000),
]

# "3봉", "2팩" 같은 수량 표현 — 중량에 곱해준다
_QUANTITY_PATTERN = re.compile(r'[×x\*]\s*(\d+)\s*(?:봉|팩|개|입|묶음)?', re.IGNORECASE)


def _load_rules() -> dict:
    with open(_RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


def parse_weight_g(text: str) -> Optional[int]:
    """상품명 또는 단위 텍스트에서 총 중량(g)을 추출. 실패 시 None.

    Examples:
        "햇흙양파 1.2kg"        → 1200
        "양파 500g×2봉"         → 1000
        "무농약 당근 1kg(4~5개)" → 1000
    """
    if not text:
        return None

    weight_g: Optional[float] = None
    for pattern, converter in _WEIGHT_PATTERNS:
        m = pattern.search(text)
        if m:
            weight_g = converter(m)
            break

    if weight_g is None:
        return None

    # 수량 곱하기 (예: "500g×2봉" → 1000g)
    qty_m = _QUANTITY_PATTERN.search(text)
    if qty_m:
        weight_g *= int(qty_m.group(1))

    return int(weight_g)


def calc_unit_price(sale_price: int, weight_g: int) -> Optional[float]:
    """100g당 가격 계산. weight_g가 0 이하면 None."""
    if weight_g and weight_g > 0:
        return round(sale_price / weight_g * 100, 1)
    return None


def tag_product(item_name: str, product_name: str) -> tuple[str, str]:
    """상품명을 분석해 (product_type, product_state) 반환.

    Args:
        item_name:    추적 품목명 (예: '양파')
        product_name: 실제 크롤링된 상품명 (예: '친환경 깐양파 1kg')

    Returns:
        product_type:  룰북 기반 유형 (예: '깐양파'), 룰 없으면 item_name
        product_state: '친환경' 또는 '일반'
    """
    rules = _load_rules()

    # state 판별
    state = "일반"
    for kw in rules.get("global_state_rules", {}).get("친환경", []):
        if kw in product_name:
            state = "친환경"
            break

    # type 판별
    item_type_rules: dict[str, list[str]] = rules.get("item_type_rules", {}).get(item_name, {})

    if not item_type_rules:
        return item_name, state

    fallback_type = item_name
    for type_name, keywords in item_type_rules.items():
        if not keywords:
            fallback_type = type_name  # 빈 키워드 = 기본 fallback
            continue
        for kw in keywords:
            if kw in product_name:
                return type_name, state

    return fallback_type, state
