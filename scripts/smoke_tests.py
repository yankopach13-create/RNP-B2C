"""Smoke-тесты без сети + опционально Google Sheets (scripts/test_sheets.py)."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd

from config.constants import SHOP_GROUP_COLUMN_GENERAL  # noqa: E402
from data.loaders import normalize_app_data  # noqa: E402
from data.references import (  # noqa: E402
    _column_letter,
    _sheet_range_name,
    _sheet_write_plan,
    build_sheets_batch_write_body,
)
from features.categories import (  # noqa: E402
    get_level_maps,
    unique_category_pairs,
)
from features.data_prep import collect_new_shops, collect_unmatched_products  # noqa: E402
from features.fill_free_products import build_fill_free_table  # noqa: E402
from features.hookah_products import build_hookah_products_table  # noqa: E402
from features.checks_no_bk import (  # noqa: E402
    build_groups_no_bk_table,
    build_sellers_no_bk_table,
    build_shops_no_bk_table,
    collect_new_sellers,
)
from features.reference_update import (  # noqa: E402
    _mutate_categories_add_product,
    _mutate_pct_no_bk_append_seller,
    _mutate_shop_groups,
    category_triple_keys_set,
)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def test_column_letter() -> None:
    _assert(_column_letter(1) == "A", "col 1")
    _assert(_column_letter(26) == "Z", "col 26")
    _assert(_column_letter(27) == "AA", "col 27")


def test_sheet_range_name() -> None:
    _assert(_sheet_range_name("shop_groups") == "shop_groups!A:ZZ", "simple name")
    _assert(
        _sheet_range_name("My Sheet", "A1:B2") == "'My Sheet'!A1:B2",
        "quoted name",
    )


def test_sheet_write_plan() -> None:
    df = pd.DataFrame({"A": [1, 2], "B": ["x", "y"]})
    plan = _sheet_write_plan("categories", df, old_row_count=10, old_col_count=5)
    assert plan is not None
    _assert(plan.n_rows == 3, "header + 2 rows")
    _assert(plan.range_name == "categories!A1:B3", "update range")
    _assert(plan.tail_clear_range == "categories!A4:E10", "tail clear")
    body = build_sheets_batch_write_body([plan])
    _assert(body["valueInputOption"] == "USER_ENTERED", "input option")
    _assert(len(body["data"]) == 1, "one sheet in batch")
    _assert(body["data"][0]["range"] == plan.range_name, "batch range")


def test_collect_new_shops() -> None:
    sales = pd.DataFrame({"Магазин": ["A", "B", "A"]})
    groups = pd.DataFrame({"Магазин": ["A"], "Группа": ["G1"]})
    new = collect_new_shops(sales, groups)
    _assert(new == ["B"], f"new shops {new}")


def test_collect_unmatched_products() -> None:
    sales = pd.DataFrame(
        {
            "Товар ур.2": ["A", "A", "B"],
            "Товар ур.3": ["X", "X", "Y"],
            "Товар ур.4": ["1", "2", ""],
            "Категория": ["Прочие товары", "Cat", "Cat"],
        }
    )
    cats = pd.DataFrame(
        {
            "Категория товара РНП:": ["Cat/Gen"],
            "Товар ур.2": ["A"],
            "Товар ур.3": ["X"],
            "Товар ур.4": ["1"],
        }
    )
    unmatched = collect_unmatched_products(sales, cats)
    pairs = {(u2, u3) for u2, u3, _ in unmatched}
    _assert(("A", "X") in pairs, "A/X pair")
    _assert(("B", "Y") in pairs, "B/Y pair")
    keys = category_triple_keys_set(cats)
    _assert("a|||x|||1" in keys, "triple key")


def test_category_maps_cache() -> None:
    cats = pd.DataFrame(
        {
            "Категория товара РНП:": ["R/G"],
            "Товар ур.2": ["P"],
            "Товар ур.3": ["Q"],
            "Товар ур.4": [""],
        }
    )
    m1 = get_level_maps(cats)
    m2 = get_level_maps(cats)
    _assert(m1 is m2, "cache hit")
    pairs = unique_category_pairs(cats)
    _assert(len(pairs) == 1, "one category pair")


def test_mutate_shop_groups() -> None:
    df = pd.DataFrame(columns=["Магазин", "Группа", SHOP_GROUP_COLUMN_GENERAL])
    out, is_new, err = _mutate_shop_groups(df, "Shop1", "G1", None)
    _assert(err is None, "no error")
    _assert(is_new, "new shop")
    _assert(len(out) == 1, "one row")


def test_normalize_app_data_legacy() -> None:
  class LegacyAppData:
    sales = groups = categories = checks_clients = client_segments = None
    focus = lfl = turnover_week = turnover_90 = None
    groups_order_rnp = category_order_rnp = category_order_general = shops_order = None

  migrated = normalize_app_data(LegacyAppData())  # type: ignore[arg-type]
  _assert(migrated is not None, "migrated")
  _assert(migrated.focus_hookah is None, "focus_hookah default")
  _assert(migrated.focus_fill_free is None, "focus_fill_free default")


def test_hookah_sales_exact_match() -> None:
    sales = pd.DataFrame(
        {
            "Магазин": ["A", "A", "A"],
            "Товар ур.2": [
                "1.1 Бестабачная Смесь",
                "1.1 Бестабачная Смесь",
                "1.1 бестабачная смесь",
            ],
            "Количество": [10, 5, 99],
        }
    )
    qty = _sales_category_qty_from_table(sales, "1.1 Бестабачная Смесь")
    _assert(qty == "15", "exact match in 2nd column, case sensitive")


def _sales_category_qty_from_table(sales: pd.DataFrame, category: str) -> str:
    from features.hookah_products import _prepare_sales_for_hookah, _sales_category_qty

    prepared, _ = _prepare_sales_for_hookah(sales, None)
    return _sales_category_qty(prepared, category)


def test_hookah_products_table() -> None:
    sales = pd.DataFrame(
        {
            "Магазин": ["A", "A", "A"],
            "Товар ур.2": [
                "1.1 Бестабачная Смесь",
                "1.2 Уголь для кальяна",
                "Прочее",
            ],
            "Количество": [10, 5, 100],
            "Продажи с НДС": [1000, 500, 10_000],
            "Неделя": [10, 10, 10],
        }
    )
    hookah = pd.DataFrame(
        {
            "Магазин": ["Итого", "Shop A", "Итого"],
            "количество чеков": [100, 50, 200],
            "количество товара": [60, 30, 120],
        }
    )
    groups = pd.DataFrame({"Магазин": ["Shop A"], "Группа": ["Восток"]})
    table = build_hookah_products_table(sales, hookah, groups)
    values = dict(zip(table["Метрика"], table["Значение"]))
    _assert(values["1.1 Бестабачная Смесь"] == "10", "bks sales")
    _assert(values["1.2 Уголь для кальяна"] == "5", "coal sales")
    _assert(values["Кол-во чеков всей категории"] == "100", "category checks")
    _assert(values["Восток"] == "0,600", "east nesting")
    _assert(values["Юг"] == "", "south nesting empty")


def test_fill_free_products_table() -> None:
    fill_free = pd.DataFrame(
        {
            "Год-Неделя": ["2026-10", "2026-10", "2026-11", "2026-11"],
            "Магазин": ["Shop A", "Shop A", "Shop B", "Shop B"],
            "Неделя": [10, 10, 11, 11],
            "Клиентов": [1, 1, 1, 1],
            "Код клиента": ["C1", "C2", "C1", "C3"],
        }
    )
    groups = pd.DataFrame({"Магазин": ["Shop A", "Shop B"], "Группа": ["Восток", "Юг"]})
    table, warnings = build_fill_free_table(fill_free, groups, 11)
    _assert(not warnings, "no warnings")
    _assert(table is not None, "table built")
    week_col = "Неделя 11"
    values = {row["Группа"]: row for _, row in table.iterrows()}
    _assert(values["Весь B2C"]["Накопительно"] == "3", "b2c cumulative")
    _assert(values["Весь B2C"][week_col] == "2", "b2c week")
    _assert(values["Восток"]["Накопительно"] == "2", "east cumulative")
    _assert(values["Восток"][week_col] == "", "east week empty")
    _assert(values["Юг"]["Накопительно"] == "2", "south cumulative")
    _assert(values["Юг"][week_col] == "2", "south week")


def test_excel_export_hookah_and_fill_free_sheets() -> None:
    from data.loaders import AppData
    from features.excel_export import collect_rnp_b2c_sheets
    from features.excise_liquid import WeekCalculationConfig

    sales = None
    hookah = pd.DataFrame(
        {
            "Магазин": ["Shop A"],
            "количество чеков": [10],
            "количество товара": [6],
        }
    )
    fill_free = pd.DataFrame(
        {
            "Год-Неделя": ["2026-10"],
            "Магазин": ["Shop A"],
            "Неделя": [10],
            "Клиентов": [1],
            "Код клиента": ["C1"],
        }
    )
    data = AppData(
        sales=sales,
        groups=None,
        categories=None,
        checks_clients=None,
        client_segments=None,
        focus=None,
        lfl=None,
        turnover_week=None,
        turnover_90=None,
        focus_hookah=hookah,
        focus_fill_free=fill_free,
        groups_order_rnp=None,
        category_order_rnp=None,
        category_order_general=None,
        shops_order=None,
    )
    week_config = WeekCalculationConfig(
        lfl_week=9,
        report_week=10,
        excise_liquid_lfl=0.0,
        excise_liquid_report=0.0,
    )
    sheets = collect_rnp_b2c_sheets(data, None, week_config)
    names = [spec.name for spec in sheets]
    _assert("Кальянная продукция" in names, "hookah sheet")
    _assert("Fill free" in names, "fill free sheet")


def test_mutate_categories_add_product() -> None:
    df = pd.DataFrame(
        columns=[
            "Категория товара РНП:",
            "Товар ур.2",
            "Товар ур.3",
            "Товар ур.4",
            "Разрез 1",
            "Разрез 2",
        ]
    )
    out, added, err = _mutate_categories_add_product(
        df, "U2", "U3", "U4", "R/G"
    )
    _assert(err is None and added, "product added")
    _assert(len(out) == 1, "one row")
    _, added2, err2 = _mutate_categories_add_product(
        out, "U2", "U3", "U4", "R/G"
    )
    _assert(not added2 and err2 is not None, "duplicate blocked")


def test_checks_no_bk_new_sellers() -> None:
    ref = pd.DataFrame(
        {
            "Порядок продавцов": ["Иванов"],
            "Порядок магазинов": [""],
            "Порядок групп": [""],
        }
    )
    upload = pd.DataFrame(
        {
            "Магазин": ["S1", ""],
            "Кассир": ["", ""],
            "Кассир (продавец)": ["Иванов", "Новиков А.А."],
            "количество чеков": [1, 2],
            "Код клиента": ["", ""],
        }
    )
    new = collect_new_sellers(upload, ref)
    _assert(new == ["Новиков А.А."], f"new sellers {new}")

    df, added, err = _mutate_pct_no_bk_append_seller(ref, "Новиков А.А.")
    _assert(err is None and added, "seller appended")
    _assert(
        str(df["Порядок продавцов"].iloc[-1]) == "Новиков А.А.",
        "seller at end",
    )
    df2, added2, _ = _mutate_pct_no_bk_append_seller(df, "Новиков А.А.")
    _assert(not added2, "duplicate blocked")
    _assert(len(df2) == len(df), "no extra row on duplicate")


def test_checks_no_bk_pcts() -> None:
    ref = pd.DataFrame(
        {
            "Порядок продавцов": ["Иванов", "Петров"],
            "Порядок магазинов": ["Магазин A", "Магазин B"],
            "Порядок групп": ["Восток", "Юг"],
        }
    )
    upload = pd.DataFrame(
        {
            "Магазин": ["Магазин A", "Магазин A", "Магазин B", "Магазин B"],
            "Кассир": ["Иванов", "Иванов", "Петров", "Петров"],
            "количество чеков": [10, 5, 8, 2],
            "Код клиента": ["123", "", "456", ""],
        }
    )
    groups = pd.DataFrame(
        {"Магазин": ["Магазин A", "Магазин B"], "Группа": ["Восток", "Юг"]}
    )
    sellers = build_sellers_no_bk_table(ref, upload)
    _assert(
        sellers.loc[sellers["Продавец"] == "Иванов", "% без БК"].iloc[0] == "33,3%",
        "seller ivanov",
    )
    shops = build_shops_no_bk_table(ref, upload)
    _assert(
        shops.loc[shops["Магазин"] == "Магазин B", "% без БК"].iloc[0] == "20,0%",
        "shop b",
    )
    gr = build_groups_no_bk_table(ref, upload, groups)
    _assert(
        gr.loc[gr["Группа"] == "Восток", "% без БК"].iloc[0] == "33,3%",
        "group east",
    )


OFFLINE_TESTS = [
    test_column_letter,
    test_sheet_range_name,
    test_sheet_write_plan,
    test_collect_new_shops,
    test_collect_unmatched_products,
    test_category_maps_cache,
    test_normalize_app_data_legacy,
    test_hookah_sales_exact_match,
    test_hookah_products_table,
    test_fill_free_products_table,
    test_excel_export_hookah_and_fill_free_sheets,
    test_mutate_shop_groups,
    test_mutate_categories_add_product,
    test_checks_no_bk_new_sellers,
    test_checks_no_bk_pcts,
]


def run_offline_smoke() -> tuple[int, int]:
    passed = 0
    failed = 0
    for test in OFFLINE_TESTS:
        name = test.__name__
        try:
            test()
            print(f"  OK  {name}")
            passed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {name}: {exc}")
            traceback.print_exc()
            failed += 1
    return passed, failed


def run_sheets_smoke() -> bool:
    from data.references import sheets_configured

    if not sheets_configured():
        print("  SKIP Google Sheets (не настроен secrets / service account)")
        return True
    scripts_dir = str(ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    try:
        from test_sheets import main as sheets_main  # noqa: WPS433

        sheets_main()
        print("  OK  test_sheets")
        return True
    except SystemExit as exc:
        if exc.code == 0:
            print("  OK  test_sheets")
            return True
        print(f"  FAIL test_sheets: exit {exc.code}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL test_sheets: {exc}")
        traceback.print_exc()
        return False


def main() -> None:
    print("Smoke-тесты (offline):")
    passed, failed = run_offline_smoke()
    print()
    print("Smoke-тесты (Google Sheets, опционально):")
    sheets_ok = run_sheets_smoke()
    print()
    total_failed = failed + (0 if sheets_ok else 1)
    print(f"Итого: {passed} passed, {total_failed} failed/skipped-errors")
    if total_failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
