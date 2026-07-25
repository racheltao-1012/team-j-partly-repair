from __future__ import annotations

import csv
import io
import json
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.case_similarity import (
    best_part_overlap,
    case_similarity,
    confirmed_part_name,
    normalised_tokens,
)
from app.impact_graph import DEFAULT_RELATIONS


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    vehicle_slug TEXT NOT NULL,
    vehicle_make TEXT,
    vehicle_model TEXT,
    vehicle_year TEXT,
    vehicle_trim TEXT,
    vin TEXT,
    status TEXT NOT NULL DEFAULT 'Reviewed',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    raw_part_name TEXT,
    predicted_part_id TEXT,
    predicted_part_name TEXT,
    oem_number TEXT,
    diagram_id TEXT,
    diagram_url TEXT,
    ai_confidence REAL,
    ai_action TEXT,
    technician_decision TEXT NOT NULL,
    rejection_reason TEXT,
    corrected_part_id TEXT,
    corrected_part_name TEXT,
    technician_note TEXT,
    hotspot_json TEXT
);

CREATE TABLE IF NOT EXISTS manual_regions (
    region_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    diagram_id TEXT,
    x1 REAL NOT NULL,
    y1 REAL NOT NULL,
    x2 REAL NOT NULL,
    y2 REAL NOT NULL,
    technician_note TEXT
);

CREATE TABLE IF NOT EXISTS local_vehicles (
    vehicle_id TEXT PRIMARY KEY,
    make TEXT NOT NULL,
    model TEXT NOT NULL,
    year INTEGER NOT NULL,
    trim TEXT,
    vin TEXT,
    source TEXT NOT NULL DEFAULT 'local_catalogue',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS local_parts (
    part_id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL REFERENCES local_vehicles(vehicle_id) ON DELETE CASCADE,
    part_name TEXT NOT NULL,
    oem_number TEXT NOT NULL,
    category TEXT,
    diagram_url TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(vehicle_id, part_name, oem_number)
);

CREATE TABLE IF NOT EXISTS supplier_quotes (
    quote_id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL,
    oem_number TEXT NOT NULL,
    part_name TEXT NOT NULL DEFAULT '',
    supplier TEXT NOT NULL DEFAULT '',
    unit_price REAL NOT NULL CHECK (unit_price > 0),
    currency TEXT NOT NULL DEFAULT 'NZD',
    stock_status TEXT NOT NULL DEFAULT 'unknown' CHECK (
        stock_status IN ('unknown', 'in_stock', 'out_of_stock', 'backorder')
    ),
    stock_quantity INTEGER CHECK (
        stock_quantity IS NULL OR stock_quantity >= 0
    ),
    estimated_arrival TEXT,
    notes TEXT NOT NULL DEFAULT '',
    is_preferred INTEGER NOT NULL DEFAULT 0 CHECK (
        is_preferred IN (0, 1)
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_supplier_quotes (
    case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    quote_id TEXT NOT NULL REFERENCES supplier_quotes(quote_id) ON DELETE CASCADE,
    PRIMARY KEY (case_id, quote_id)
);

CREATE TABLE IF NOT EXISTS photo_assessments (
    run_id TEXT PRIMARY KEY,
    vehicle_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    impact_zone TEXT,
    impact_direction TEXT,
    impact_severity REAL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assessment_images (
    image_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES photo_assessments(run_id) ON DELETE CASCADE,
    stored_path TEXT NOT NULL,
    content_type TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS part_relations (
    relation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL DEFAULT 'global',
    source_part TEXT NOT NULL,
    target_part TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    propagation_weight REAL NOT NULL CHECK (
        propagation_weight >= 0 AND propagation_weight <= 1
    ),
    impact_zone TEXT NOT NULL DEFAULT 'any',
    UNIQUE (
        scope, source_part, target_part, relation_type, impact_zone
    )
);

CREATE INDEX IF NOT EXISTS idx_cases_vehicle ON cases(vehicle_slug);
CREATE INDEX IF NOT EXISTS idx_items_raw_part ON case_items(raw_part_name);
CREATE INDEX IF NOT EXISTS idx_local_parts_vehicle ON local_parts(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_local_parts_oem ON local_parts(oem_number);
CREATE INDEX IF NOT EXISTS idx_supplier_quotes_lookup
    ON supplier_quotes(vehicle_id, oem_number);
CREATE INDEX IF NOT EXISTS idx_case_supplier_quotes_case
    ON case_supplier_quotes(case_id);
CREATE INDEX IF NOT EXISTS idx_photo_assessments_vehicle
    ON photo_assessments(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_assessment_images_run
    ON assessment_images(run_id);
CREATE INDEX IF NOT EXISTS idx_part_relations_source
    ON part_relations(source_part);
"""


CSV_FIELDS = (
    "case_id",
    "created_at",
    "vehicle_slug",
    "make",
    "model",
    "year",
    "trim",
    "vin",
    "source",
    "ai_raw_part_name",
    "predicted_part_id",
    "predicted_part_name",
    "oem_number",
    "diagram_id",
    "diagram_url",
    "ai_confidence",
    "ai_action",
    "technician_decision",
    "rejection_reason",
    "corrected_part_id",
    "corrected_part_name",
    "technician_note",
    "damage_type",
    "severity",
    "evidence_image_id",
    "evidence_box",
    "reason",
    "propagation_path",
    "probability_band",
    "supplier_quote_count",
    "supplier_quotes_json",
)


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            self._ensure_column(connection, "cases", "photo_run_id", "TEXT")
            self._ensure_column(connection, "case_items", "diagram_url", "TEXT")
            self._ensure_column(connection, "case_items", "damage_type", "TEXT")
            self._ensure_column(connection, "case_items", "severity", "REAL")
            self._ensure_column(
                connection,
                "case_items",
                "evidence_image_id",
                "TEXT",
            )
            self._ensure_column(
                connection,
                "case_items",
                "evidence_box_json",
                "TEXT",
            )
            self._ensure_column(connection, "case_items", "reason", "TEXT")
            self._ensure_column(
                connection,
                "case_items",
                "propagation_path_json",
                "TEXT",
            )
            self._ensure_column(
                connection,
                "case_items",
                "probability_band",
                "TEXT",
            )
            connection.executemany(
                """
                INSERT OR IGNORE INTO part_relations (
                    scope, source_part, target_part, relation_type,
                    propagation_weight, impact_zone
                ) VALUES ('global', ?, ?, ?, ?, ?)
                """,
                DEFAULT_RELATIONS,
            )

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
            )

    def create_vehicle(self, payload: dict[str, Any]) -> dict[str, Any]:
        vehicle_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO local_vehicles (
                    vehicle_id, make, model, year, trim, vin, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'local_catalogue', ?)
                """,
                (
                    vehicle_id,
                    str(payload["make"]).strip(),
                    str(payload["model"]).strip(),
                    int(payload["year"]),
                    str(payload.get("trim") or "").strip(),
                    str(payload.get("vin") or "").strip(),
                    created_at,
                ),
            )
        vehicle = self.get_local_vehicle(vehicle_id)
        if vehicle is None:
            raise RuntimeError("Vehicle was not saved")
        return vehicle

    def get_local_vehicle(self, vehicle_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    v.*,
                    COUNT(p.part_id) AS part_count,
                    SUM(CASE WHEN COALESCE(p.diagram_url, '') <> '' THEN 1 ELSE 0 END)
                        AS diagram_count
                FROM local_vehicles v
                LEFT JOIN local_parts p ON p.vehicle_id = v.vehicle_id
                WHERE v.vehicle_id = ?
                GROUP BY v.vehicle_id
                """,
                (vehicle_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_local_vehicles(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    v.*,
                    COUNT(p.part_id) AS part_count,
                    SUM(CASE WHEN COALESCE(p.diagram_url, '') <> '' THEN 1 ELSE 0 END)
                        AS diagram_count
                FROM local_vehicles v
                LEFT JOIN local_parts p ON p.vehicle_id = v.vehicle_id
                GROUP BY v.vehicle_id
                ORDER BY v.created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def create_part(
        self,
        vehicle_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self.get_local_vehicle(vehicle_id) is None:
            raise KeyError("Local vehicle not found")
        part_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO local_parts (
                        part_id, vehicle_id, part_name, oem_number,
                        category, diagram_url, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        part_id,
                        vehicle_id,
                        str(payload["part_name"]).strip(),
                        str(payload["oem_number"]).strip(),
                        str(payload.get("category") or "").strip(),
                        str(payload.get("diagram_url") or "").strip(),
                        created_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    "This part name and OEM number already exist for the vehicle"
                ) from exc
        part = self.get_part(part_id)
        if part is None:
            raise RuntimeError("Part was not saved")
        return part

    def get_part(self, part_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM local_parts WHERE part_id = ?",
                (part_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_parts(self, vehicle_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM local_parts
                WHERE vehicle_id = ?
                ORDER BY category, part_name, oem_number
                """,
                (vehicle_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def import_parts(
        self,
        vehicle_id: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, int]:
        if self.get_local_vehicle(vehicle_id) is None:
            raise KeyError("Local vehicle not found")
        created_at = datetime.now(timezone.utc).isoformat()
        created_count = 0
        updated_count = 0
        with self._connect() as connection:
            existing = {
                (str(row["part_name"]), str(row["oem_number"]))
                for row in connection.execute(
                    """
                    SELECT part_name, oem_number FROM local_parts
                    WHERE vehicle_id = ?
                    """,
                    (vehicle_id,),
                ).fetchall()
            }
            for row in rows:
                key = (
                    str(row["part_name"]).strip(),
                    str(row["oem_number"]).strip(),
                )
                if key in existing:
                    updated_count += 1
                else:
                    created_count += 1
                    existing.add(key)
                connection.execute(
                    """
                    INSERT INTO local_parts (
                        part_id, vehicle_id, part_name, oem_number,
                        category, diagram_url, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(vehicle_id, part_name, oem_number)
                    DO UPDATE SET
                        category = excluded.category,
                        diagram_url = excluded.diagram_url
                    """,
                    (
                        str(uuid.uuid4()),
                        vehicle_id,
                        str(row["part_name"]).strip(),
                        str(row["oem_number"]).strip(),
                        str(row.get("category") or "").strip(),
                        str(row.get("diagram_url") or "").strip(),
                        created_at,
                    ),
                )
        return {
            "imported_count": len(rows),
            "created_count": created_count,
            "updated_count": updated_count,
            "total_part_count": len(self.get_parts(vehicle_id)),
        }

    @staticmethod
    def _normalise_quote_values(payload: dict[str, Any]) -> dict[str, Any]:
        stock_status = str(payload.get("stock_status") or "unknown")
        if stock_status not in {
            "unknown",
            "in_stock",
            "out_of_stock",
            "backorder",
        }:
            raise ValueError("Unsupported stock status")

        raw_quantity = payload.get("stock_quantity")
        stock_quantity = (
            int(raw_quantity)
            if raw_quantity is not None and str(raw_quantity).strip() != ""
            else None
        )
        if stock_status == "in_stock":
            if stock_quantity is None or stock_quantity < 1:
                raise ValueError(
                    "Stock quantity must be at least 1 when availability is in stock"
                )
        elif stock_status == "out_of_stock":
            stock_quantity = 0
        else:
            # A missing quantity is unknown, not evidence that stock is zero.
            stock_quantity = None

        unit_price = float(payload["unit_price"])
        if unit_price <= 0:
            raise ValueError("Unit price must be greater than zero")

        estimated_arrival = payload.get("estimated_arrival")
        return {
            "part_name": str(payload.get("part_name") or "").strip(),
            "supplier": str(payload.get("supplier") or "").strip(),
            "unit_price": unit_price,
            "currency": str(payload.get("currency") or "NZD").strip().upper(),
            "stock_status": stock_status,
            "stock_quantity": stock_quantity,
            "estimated_arrival": (
                str(estimated_arrival) if estimated_arrival else None
            ),
            "notes": str(payload.get("notes") or "").strip(),
            "is_preferred": bool(payload.get("is_preferred", False)),
        }

    @staticmethod
    def _quote_from_row(row: sqlite3.Row) -> dict[str, Any]:
        quote = dict(row)
        quote["is_preferred"] = bool(quote["is_preferred"])
        return quote

    def create_supplier_quote(self, payload: dict[str, Any]) -> dict[str, Any]:
        quote_id = str(uuid.uuid4())
        vehicle_id = str(payload["vehicle_id"]).strip()
        oem_number = str(payload["oem_number"]).strip()
        if not vehicle_id or not oem_number:
            raise ValueError("Vehicle and OEM number are required")
        values = self._normalise_quote_values(payload)
        timestamp = datetime.now(timezone.utc).isoformat()

        with self._connect() as connection:
            if values["is_preferred"]:
                connection.execute(
                    """
                    UPDATE supplier_quotes
                    SET is_preferred = 0, updated_at = ?
                    WHERE vehicle_id = ? AND UPPER(oem_number) = UPPER(?)
                    """,
                    (timestamp, vehicle_id, oem_number),
                )
            connection.execute(
                """
                INSERT INTO supplier_quotes (
                    quote_id, vehicle_id, oem_number, part_name, supplier,
                    unit_price, currency, stock_status, stock_quantity,
                    estimated_arrival, notes, is_preferred, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quote_id,
                    vehicle_id,
                    oem_number,
                    values["part_name"],
                    values["supplier"],
                    values["unit_price"],
                    values["currency"],
                    values["stock_status"],
                    values["stock_quantity"],
                    values["estimated_arrival"],
                    values["notes"],
                    int(values["is_preferred"]),
                    timestamp,
                    timestamp,
                ),
            )
        quote = self.get_supplier_quote(quote_id)
        if quote is None:
            raise RuntimeError("Supplier quote was not saved")
        return quote

    def get_supplier_quote(self, quote_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM supplier_quotes WHERE quote_id = ?",
                (quote_id,),
            ).fetchone()
        return self._quote_from_row(row) if row else None

    def list_supplier_quotes(
        self,
        vehicle_id: str,
        oem_number: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM supplier_quotes
                WHERE vehicle_id = ? AND UPPER(oem_number) = UPPER(?)
                ORDER BY is_preferred DESC, unit_price, updated_at DESC
                """,
                (vehicle_id, oem_number),
            ).fetchall()
        return [self._quote_from_row(row) for row in rows]

    def update_supplier_quote(
        self,
        quote_id: str,
        changes: dict[str, Any],
    ) -> dict[str, Any] | None:
        existing = self.get_supplier_quote(quote_id)
        if existing is None:
            return None

        merged = {
            **existing,
            **{key: value for key, value in changes.items() if value is not None},
        }
        # A caller can explicitly clear these optional values with null.
        if "stock_quantity" in changes:
            merged["stock_quantity"] = changes["stock_quantity"]
        if "estimated_arrival" in changes:
            merged["estimated_arrival"] = changes["estimated_arrival"]
        values = self._normalise_quote_values(merged)
        timestamp = datetime.now(timezone.utc).isoformat()

        with self._connect() as connection:
            if values["is_preferred"]:
                connection.execute(
                    """
                    UPDATE supplier_quotes
                    SET is_preferred = 0, updated_at = ?
                    WHERE vehicle_id = ? AND UPPER(oem_number) = UPPER(?)
                      AND quote_id <> ?
                    """,
                    (
                        timestamp,
                        existing["vehicle_id"],
                        existing["oem_number"],
                        quote_id,
                    ),
                )
            connection.execute(
                """
                UPDATE supplier_quotes
                SET part_name = ?, supplier = ?, unit_price = ?, currency = ?,
                    stock_status = ?, stock_quantity = ?,
                    estimated_arrival = ?, notes = ?, is_preferred = ?,
                    updated_at = ?
                WHERE quote_id = ?
                """,
                (
                    values["part_name"],
                    values["supplier"],
                    values["unit_price"],
                    values["currency"],
                    values["stock_status"],
                    values["stock_quantity"],
                    values["estimated_arrival"],
                    values["notes"],
                    int(values["is_preferred"]),
                    timestamp,
                    quote_id,
                ),
            )
        return self.get_supplier_quote(quote_id)

    def delete_supplier_quote(self, quote_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM supplier_quotes WHERE quote_id = ?",
                (quote_id,),
            )
        return cursor.rowcount > 0

    def create_case(self, payload: dict[str, Any]) -> str:
        case_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO cases (
                    case_id, vehicle_slug, vehicle_make, vehicle_model,
                    vehicle_year, vehicle_trim, vin, status, created_at,
                    photo_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case_id,
                    payload["vehicle_slug"],
                    payload.get("vehicle_make"),
                    payload.get("vehicle_model"),
                    str(payload.get("vehicle_year") or ""),
                    payload.get("vehicle_trim"),
                    payload.get("vin"),
                    payload.get("status") or "Reviewed",
                    created_at,
                    payload.get("photo_run_id"),
                ),
            )
            for item in payload.get("items", []):
                connection.execute(
                    """
                    INSERT INTO case_items (
                        case_id, source, raw_part_name, predicted_part_id,
                        predicted_part_name, oem_number, diagram_id,
                        diagram_url, ai_confidence, ai_action, technician_decision,
                        rejection_reason, corrected_part_id, corrected_part_name,
                        technician_note, hotspot_json, damage_type, severity,
                        evidence_image_id, evidence_box_json, reason,
                        propagation_path_json, probability_band
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        case_id,
                        item.get("source") or "manual",
                        item.get("raw_part_name"),
                        item.get("predicted_part_id"),
                        item.get("predicted_part_name"),
                        item.get("oem_number"),
                        item.get("diagram_id"),
                        item.get("diagram_url"),
                        item.get("ai_confidence"),
                        item.get("ai_action"),
                        item.get("technician_decision") or "Pending",
                        item.get("rejection_reason"),
                        item.get("corrected_part_id"),
                        item.get("corrected_part_name"),
                        item.get("technician_note"),
                        json.dumps(item.get("hotspot")) if item.get("hotspot") else None,
                        item.get("damage_type"),
                        item.get("severity"),
                        item.get("evidence_image_id"),
                        (
                            json.dumps(item.get("evidence_box"))
                            if item.get("evidence_box")
                            else None
                        ),
                        item.get("reason"),
                        (
                            json.dumps(item.get("propagation_path"))
                            if item.get("propagation_path")
                            else None
                        ),
                        item.get("probability_band"),
                    ),
                )
            for region in payload.get("manual_regions", []):
                connection.execute(
                    """
                    INSERT INTO manual_regions (
                        case_id, diagram_id, x1, y1, x2, y2, technician_note
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        case_id,
                        region.get("diagram_id"),
                        region["x1"],
                        region["y1"],
                        region["x2"],
                        region["y2"],
                        region.get("technician_note"),
                    ),
                )
            quote_ids = list(dict.fromkeys(payload.get("quote_ids") or []))
            if quote_ids:
                placeholders = ",".join("?" for _ in quote_ids)
                existing_quotes = {
                    str(row["quote_id"]): str(row["vehicle_id"])
                    for row in connection.execute(
                        (
                            "SELECT quote_id, vehicle_id FROM supplier_quotes "
                            f"WHERE quote_id IN ({placeholders})"
                        ),
                        quote_ids,
                    ).fetchall()
                }
                missing_quote_ids = set(quote_ids) - set(existing_quotes)
                if missing_quote_ids:
                    raise ValueError("One or more supplier quotes no longer exist")
                if any(
                    vehicle_id != str(payload["vehicle_slug"])
                    for vehicle_id in existing_quotes.values()
                ):
                    raise ValueError(
                        "Supplier quotes must belong to the case vehicle"
                    )
                connection.executemany(
                    """
                    INSERT INTO case_supplier_quotes (case_id, quote_id)
                    VALUES (?, ?)
                    """,
                    [(case_id, quote_id) for quote_id in quote_ids],
                )
        return case_id

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            case_row = connection.execute(
                "SELECT * FROM cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()
            if not case_row:
                return None
            item_rows = connection.execute(
                "SELECT * FROM case_items WHERE case_id = ? ORDER BY item_id",
                (case_id,),
            ).fetchall()
            region_rows = connection.execute(
                "SELECT * FROM manual_regions WHERE case_id = ? ORDER BY region_id",
                (case_id,),
            ).fetchall()
            quote_rows = connection.execute(
                """
                SELECT q.*
                FROM supplier_quotes q
                JOIN case_supplier_quotes cq ON cq.quote_id = q.quote_id
                WHERE cq.case_id = ?
                ORDER BY q.is_preferred DESC, q.oem_number, q.unit_price
                """,
                (case_id,),
            ).fetchall()

        case = dict(case_row)
        items = []
        for row in item_rows:
            item = dict(row)
            hotspot_json = item.pop("hotspot_json", None)
            item["hotspot"] = json.loads(hotspot_json) if hotspot_json else None
            evidence_box_json = item.pop("evidence_box_json", None)
            item["evidence_box"] = (
                json.loads(evidence_box_json) if evidence_box_json else None
            )
            propagation_path_json = item.pop("propagation_path_json", None)
            item["propagation_path"] = (
                json.loads(propagation_path_json)
                if propagation_path_json
                else []
            )
            items.append(item)
        case["items"] = items
        case["manual_regions"] = [dict(row) for row in region_rows]
        case["supplier_quotes"] = [
            self._quote_from_row(row) for row in quote_rows
        ]
        return case

    def list_part_relations(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM part_relations
                ORDER BY source_part, propagation_weight DESC, target_part
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def create_photo_assessment(
        self,
        *,
        run_id: str,
        vehicle_id: str,
        provider: str,
        model: str,
        impact_zone: str,
        impact_direction: str,
        impact_severity: float,
        images: list[dict[str, Any]],
        result: dict[str, Any],
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO photo_assessments (
                    run_id, vehicle_id, provider, model, impact_zone,
                    impact_direction, impact_severity, result_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    vehicle_id,
                    provider,
                    model,
                    impact_zone,
                    impact_direction,
                    impact_severity,
                    json.dumps(result),
                    created_at,
                ),
            )
            connection.executemany(
                """
                INSERT INTO assessment_images (
                    image_id, run_id, stored_path, content_type,
                    sort_order, size_bytes
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        image["image_id"],
                        run_id,
                        image["stored_path"],
                        image["content_type"],
                        image["sort_order"],
                        image["size_bytes"],
                    )
                    for image in images
                ],
            )

    def get_photo_assessment(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM photo_assessments WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_photo_image(
        self,
        run_id: str,
        image_id: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM assessment_images
                WHERE run_id = ? AND image_id = ?
                """,
                (run_id, image_id),
            ).fetchone()
        return dict(row) if row else None

    def find_similar_cases(
        self,
        *,
        vehicle_slug: str,
        impact_zone: str,
        impact_severity: float,
        visible_items: list[dict[str, Any]],
        threshold: float = 0.55,
        limit: int = 5,
    ) -> dict[str, Any]:
        current_parts = [
            str(item.get("raw_part_name") or item.get("predicted_part_name") or "")
            for item in visible_items
            if item.get("raw_part_name") or item.get("predicted_part_name")
        ]
        current_damage_types = [
            str(item.get("damage_type") or "")
            for item in visible_items
            if item.get("damage_type")
        ]
        if not current_parts:
            return {
                "threshold": threshold,
                "match_count": 0,
                "matches": [],
                "recommendations": [],
                "message": (
                    "No visible photo damage was available for historical "
                    "similarity matching."
                ),
            }

        with self._connect() as connection:
            candidate_rows = connection.execute(
                """
                SELECT
                    c.case_id,
                    c.created_at,
                    p.impact_zone,
                    p.impact_severity
                FROM cases c
                JOIN photo_assessments p ON p.run_id = c.photo_run_id
                WHERE c.vehicle_slug = ?
                  AND c.photo_run_id IS NOT NULL
                ORDER BY c.created_at DESC
                """,
                (vehicle_slug,),
            ).fetchall()

            matched_cases: list[dict[str, Any]] = []
            recommendation_groups: dict[str, dict[str, Any]] = {}
            for case_row in candidate_rows:
                item_rows = [
                    dict(row)
                    for row in connection.execute(
                        """
                        SELECT * FROM case_items
                        WHERE case_id = ?
                        ORDER BY item_id
                        """,
                        (case_row["case_id"],),
                    ).fetchall()
                ]
                past_visible = [
                    item
                    for item in item_rows
                    if item.get("source") in {"visible_damage", "manual"}
                    and item.get("technician_decision") == "Confirm"
                ]
                if not past_visible:
                    continue
                score, signals = case_similarity(
                    current_zone=impact_zone,
                    current_severity=impact_severity,
                    current_parts=current_parts,
                    current_damage_types=current_damage_types,
                    past_zone=str(case_row["impact_zone"] or ""),
                    past_severity=float(case_row["impact_severity"] or 0),
                    past_parts=[
                        confirmed_part_name(item)
                        for item in past_visible
                        if confirmed_part_name(item)
                    ],
                    past_damage_types=[
                        str(item.get("damage_type") or "")
                        for item in past_visible
                        if item.get("damage_type")
                    ],
                )
                if score < threshold:
                    continue

                matched_cases.append(
                    {
                        "case_id": str(case_row["case_id"]),
                        "created_at": str(case_row["created_at"]),
                        "similarity": score,
                        "signals": signals,
                    }
                )
                for item in item_rows:
                    if item.get("technician_decision") != "Confirm":
                        continue
                    if item.get("source") not in {
                        "impact_path",
                        "historical_case",
                        "manual",
                        "catalogue_candidate",
                    }:
                        continue
                    part_name = confirmed_part_name(item)
                    if not part_name:
                        continue
                    if best_part_overlap([part_name], current_parts) >= 0.65:
                        continue
                    token_key = " ".join(sorted(normalised_tokens(part_name)))
                    key = token_key or part_name.lower()
                    group = recommendation_groups.setdefault(
                        key,
                        {
                            "part_name": part_name,
                            "oem_number": str(item.get("oem_number") or ""),
                            "support_count": 0,
                            "similarity_total": 0.0,
                            "case_ids": [],
                        },
                    )
                    group["support_count"] += 1
                    group["similarity_total"] += score
                    group["case_ids"].append(str(case_row["case_id"]))

        matched_cases.sort(key=lambda item: item["similarity"], reverse=True)
        matched_cases = matched_cases[: max(1, limit)]
        allowed_case_ids = {item["case_id"] for item in matched_cases}
        recommendations: list[dict[str, Any]] = []
        for group in recommendation_groups.values():
            supported_case_ids = [
                case_id
                for case_id in group["case_ids"]
                if case_id in allowed_case_ids
            ]
            if not supported_case_ids:
                continue
            support_count = len(set(supported_case_ids))
            average_similarity = (
                group["similarity_total"] / max(1, group["support_count"])
            )
            recommendations.append(
                {
                    "part_name": group["part_name"],
                    "oem_number": group["oem_number"] or None,
                    "support_count": support_count,
                    "case_ids": sorted(set(supported_case_ids)),
                    "relevance": round(average_similarity, 4),
                    "reason": (
                        f"Technician-confirmed in {support_count} similar "
                        f"saved case{'s' if support_count != 1 else ''}"
                    ),
                }
            )
        recommendations.sort(
            key=lambda item: (
                item["support_count"],
                item["relevance"],
                item["part_name"],
            ),
            reverse=True,
        )
        return {
            "threshold": threshold,
            "match_count": len(matched_cases),
            "matches": matched_cases,
            "recommendations": recommendations[:10],
            "message": (
                "Historical suggestions are shown only when the current "
                "photo pattern passes the similarity threshold."
            ),
        }

    def history(self, vehicle_slug: str) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT i.technician_decision, i.corrected_part_name, i.raw_part_name
                FROM case_items i
                JOIN cases c ON c.case_id = i.case_id
                WHERE c.vehicle_slug = ?
                """,
                (vehicle_slug,),
            ).fetchall()
            case_count = connection.execute(
                "SELECT COUNT(*) FROM cases WHERE vehicle_slug = ?",
                (vehicle_slug,),
            ).fetchone()[0]

        decisions = Counter(row["technician_decision"] or "Unknown" for row in rows)
        corrections = Counter(
            row["corrected_part_name"]
            for row in rows
            if row["corrected_part_name"]
        )
        return {
            "vehicle_slug": vehicle_slug,
            "past_case_count": case_count,
            "reviewed_item_count": len(rows),
            "decisions": dict(decisions),
            "common_corrections": [
                {"part_name": name, "count": count}
                for name, count in corrections.most_common(5)
            ],
        }

    def export_csv(self, case_id: str) -> str | None:
        case = self.get_case(case_id)
        if not case:
            return None
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for item in case["items"]:
            item_oem = str(item.get("oem_number") or "").strip().upper()
            item_quotes = [
                quote
                for quote in case["supplier_quotes"]
                if item_oem
                and str(quote.get("oem_number") or "").strip().upper() == item_oem
            ]
            writer.writerow(
                {
                    "case_id": case["case_id"],
                    "created_at": case["created_at"],
                    "vehicle_slug": case["vehicle_slug"],
                    "make": case["vehicle_make"],
                    "model": case["vehicle_model"],
                    "year": case["vehicle_year"],
                    "trim": case["vehicle_trim"],
                    "vin": case["vin"],
                    "source": item["source"],
                    "ai_raw_part_name": item["raw_part_name"],
                    "predicted_part_id": item["predicted_part_id"],
                    "predicted_part_name": item["predicted_part_name"],
                    "oem_number": item["oem_number"],
                    "diagram_id": item["diagram_id"],
                    "diagram_url": item.get("diagram_url"),
                    "ai_confidence": item["ai_confidence"],
                    "ai_action": item["ai_action"],
                    "technician_decision": item["technician_decision"],
                    "rejection_reason": item["rejection_reason"],
                    "corrected_part_id": item["corrected_part_id"],
                    "corrected_part_name": item["corrected_part_name"],
                    "technician_note": item["technician_note"],
                    "damage_type": item.get("damage_type"),
                    "severity": item.get("severity"),
                    "evidence_image_id": item.get("evidence_image_id"),
                    "evidence_box": json.dumps(
                        item.get("evidence_box")
                    ) if item.get("evidence_box") else "",
                    "reason": item.get("reason"),
                    "propagation_path": " -> ".join(
                        item.get("propagation_path") or []
                    ),
                    "probability_band": item.get("probability_band"),
                    "supplier_quote_count": len(item_quotes),
                    "supplier_quotes_json": json.dumps(item_quotes),
                }
            )
        return output.getvalue()
