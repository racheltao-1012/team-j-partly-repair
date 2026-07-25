import csv
import io
import json

from app.database import Database


def quote_payload(**overrides):
    payload = {
        "vehicle_id": "vehicle-1",
        "oem_number": "OEM-001",
        "part_name": "Front bumper cover",
        "supplier": "Supplier A",
        "unit_price": 312.45,
        "currency": "NZD",
        "stock_status": "unknown",
        "stock_quantity": None,
        "estimated_arrival": None,
        "notes": "Phone quote",
        "is_preferred": False,
    }
    payload.update(overrides)
    return payload


def case_payload(quote_ids):
    return {
        "vehicle_slug": "vehicle-1",
        "vehicle_make": "Test",
        "vehicle_model": "Car",
        "vehicle_year": "2026",
        "items": [
            {
                "source": "manual",
                "raw_part_name": "Front bumper cover",
                "predicted_part_name": "Front bumper cover",
                "oem_number": "OEM-001",
                "technician_decision": "Confirm",
            }
        ],
        "quote_ids": quote_ids,
    }


def test_quote_round_trip_keeps_blank_stock_unknown(tmp_path):
    database = Database(tmp_path / "inspection.db")
    database.initialise()

    saved = database.create_supplier_quote(quote_payload())
    assert saved["stock_status"] == "unknown"
    assert saved["stock_quantity"] is None

    reloaded = database.list_supplier_quotes("vehicle-1", "oem-001")
    assert len(reloaded) == 1
    assert reloaded[0]["quote_id"] == saved["quote_id"]
    assert reloaded[0]["stock_status"] == "unknown"
    assert reloaded[0]["stock_quantity"] is None


def test_quote_crud_and_only_one_preferred_quote(tmp_path):
    database = Database(tmp_path / "inspection.db")
    database.initialise()

    first = database.create_supplier_quote(
        quote_payload(supplier="Supplier A", is_preferred=True)
    )
    second = database.create_supplier_quote(
        quote_payload(supplier="Supplier B", unit_price=299, is_preferred=True)
    )

    assert database.get_supplier_quote(first["quote_id"])["is_preferred"] is False
    assert database.get_supplier_quote(second["quote_id"])["is_preferred"] is True

    updated = database.update_supplier_quote(
        first["quote_id"],
        {
            "unit_price": 280,
            "stock_status": "in_stock",
            "stock_quantity": 4,
            "is_preferred": True,
        },
    )
    assert updated is not None
    assert updated["unit_price"] == 280
    assert updated["stock_status"] == "in_stock"
    assert updated["stock_quantity"] == 4
    assert updated["is_preferred"] is True
    assert database.get_supplier_quote(second["quote_id"])["is_preferred"] is False

    assert database.delete_supplier_quote(second["quote_id"]) is True
    assert database.get_supplier_quote(second["quote_id"]) is None


def test_case_links_existing_quotes_without_copying_them(tmp_path):
    database = Database(tmp_path / "inspection.db")
    database.initialise()
    quote = database.create_supplier_quote(quote_payload())

    first_case_id = database.create_case(case_payload([quote["quote_id"]]))
    second_case_id = database.create_case(case_payload([quote["quote_id"]]))

    first_case = database.get_case(first_case_id)
    second_case = database.get_case(second_case_id)
    assert first_case is not None
    assert second_case is not None
    assert first_case["supplier_quotes"][0]["quote_id"] == quote["quote_id"]
    assert second_case["supplier_quotes"][0]["quote_id"] == quote["quote_id"]
    assert len(database.list_supplier_quotes("vehicle-1", "OEM-001")) == 1
    csv_body = database.export_csv(first_case_id)
    assert csv_body is not None
    csv_row = next(csv.DictReader(io.StringIO(csv_body)))
    exported_quotes = json.loads(csv_row["supplier_quotes_json"])
    assert exported_quotes[0]["stock_status"] == "unknown"


def test_out_of_stock_is_explicit_and_backorder_has_no_quantity(tmp_path):
    database = Database(tmp_path / "inspection.db")
    database.initialise()

    unavailable = database.create_supplier_quote(
        quote_payload(stock_status="out_of_stock", stock_quantity=None)
    )
    backorder = database.create_supplier_quote(
        quote_payload(
            supplier="Supplier B",
            stock_status="backorder",
            stock_quantity=8,
        )
    )

    assert unavailable["stock_status"] == "out_of_stock"
    assert unavailable["stock_quantity"] == 0
    assert backorder["stock_status"] == "backorder"
    assert backorder["stock_quantity"] is None
