"""Open Food Facts 产品映射与营养换算（纯函数）。"""

from __future__ import annotations

import math
import re
from typing import Any

NON_DIAGNOSTIC = "非医疗器械，不用于诊断"
_BARCODE_RE = re.compile(r"^\d{8,14}$")
_KJ_PER_KCAL = 4.184


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _text(value: Any, limit: int = 300) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text[:limit] if text else None


def normalize_barcode(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("条码必须是字符串")
    digits = value.strip()
    if not _BARCODE_RE.match(digits):
        raise ValueError("条码必须是 8..14 位数字")
    return digits


def _nutriment(nutriments: dict[str, Any], key: str) -> float | None:
    value = _number(nutriments.get(key))
    return round(value, 2) if value is not None else None


def normalize_product(product: dict[str, Any], barcode: str | None = None) -> dict[str, Any]:
    if not isinstance(product, dict):
        raise TypeError("产品必须是对象")
    nutriments = product.get("nutriments") if isinstance(product.get("nutriments"), dict) else {}
    energy_kcal = _nutriment(nutriments, "energy-kcal_100g")
    if energy_kcal is None:
        energy_kj = _nutriment(nutriments, "energy_100g")
        if energy_kj is not None:
            energy_kcal = round(energy_kj / _KJ_PER_KCAL, 2)
    name = (
        _text(product.get("product_name_zh"), 200)
        or _text(product.get("product_name"), 200)
        or _text(product.get("generic_name"), 200)
        or "未知食品"
    )
    allergens = product.get("allergens")
    if isinstance(allergens, list):
        allergens = ", ".join(str(item)[:40] for item in allergens[:20])
    return {
        "barcode": _text(product.get("code") or product.get("_id"), 32) or (barcode or ""),
        "name": name,
        "brands": _text(product.get("brands"), 200),
        "quantity": _text(product.get("quantity"), 80),
        "nutriscoreGrade": (_text(product.get("nutriscore_grade"), 4) or "").lower() or None,
        "novaGroup": int(product["nova_group"])
        if isinstance(product.get("nova_group"), (int, float))
        else None,
        "per100g": {
            "energyKcal": energy_kcal,
            "proteinG": _nutriment(nutriments, "proteins_100g"),
            "carbohydrateG": _nutriment(nutriments, "carbohydrates_100g"),
            "fatG": _nutriment(nutriments, "fat_100g"),
            "sugarsG": _nutriment(nutriments, "sugars_100g"),
            "saltG": _nutriment(nutriments, "salt_100g"),
            "sodiumG": _nutriment(nutriments, "sodium_100g"),
            "fiberG": _nutriment(nutriments, "fiber_100g"),
        },
        "allergens": _text(allergens, 300),
        "ingredientsText": _text(product.get("ingredients_text"), 2000),
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def lookup_result(barcode: str, product: dict[str, Any] | None, *, found: bool) -> dict[str, Any]:
    return {
        "found": bool(found) and product is not None,
        "barcode": barcode,
        "product": normalize_product(product, barcode) if found and product is not None else None,
        "attribution": "Open Food Facts 数据 © Open Food Facts contributors, ODbL 1.0",
        "source": "https://world.openfoodfacts.org",
        "nonDiagnostic": NON_DIAGNOSTIC,
    }


def to_record(product: dict[str, Any], consumed_grams: float = 100.0) -> dict[str, Any]:
    if not isinstance(consumed_grams, (int, float)) or isinstance(consumed_grams, bool):
        raise TypeError("摄入量必须是数字")
    if not 0.1 <= float(consumed_grams) <= 5000:
        raise ValueError("摄入量必须在 0.1..5000 克")
    factor = float(consumed_grams) / 100.0
    per100 = product.get("per100g") if isinstance(product.get("per100g"), dict) else {}

    def scaled(key: str) -> float | None:
        value = _number(per100.get(key))
        return round(value * factor, 2) if value is not None else None

    return {
        "barcode": product.get("barcode", ""),
        "name": product.get("name", "未知食品"),
        "consumedGrams": round(float(consumed_grams), 2),
        "energyKcal": scaled("energyKcal"),
        "proteinG": scaled("proteinG"),
        "carbohydrateG": scaled("carbohydrateG"),
        "fatG": scaled("fatG"),
        "sugarsG": scaled("sugarsG"),
        "saltG": scaled("saltG"),
        "source": "openfoodfacts",
        "nonDiagnostic": NON_DIAGNOSTIC,
    }
