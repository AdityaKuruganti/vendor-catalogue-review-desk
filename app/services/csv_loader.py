"""Loads vendor rows from a CSV file or uploaded bytes."""
import csv
import io
from pathlib import Path

from app.schemas import VendorRow


class CsvValidationError(ValueError):
    pass


def parse_csv_bytes(data: bytes, max_rows: int = 200) -> list[VendorRow]:
    try:
        text = data.decode("utf-8-sig")  # handles Excel's BOM
    except UnicodeDecodeError as e:
        raise CsvValidationError("CSV must be UTF-8 encoded.") from e

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise CsvValidationError("CSV is empty or has no header row.")

    headers = {h.strip().lower(): h for h in reader.fieldnames if h}
    if "raw_row" not in headers:
        raise CsvValidationError(
            f"CSV must contain a 'raw_row' column. Found: {list(headers)}"
        )

    rows: list[VendorRow] = []
    for line_no, rec in enumerate(reader, start=2):
        raw = (rec.get(headers["raw_row"]) or "").strip()
        if not raw:
            continue  # skip blank rows
        if len(rows) >= max_rows:
            raise CsvValidationError(f"Too many rows (limit is {max_rows}).")
        rows.append(
            VendorRow(
                sku=(rec.get(headers["sku"]) or "").strip() or None if "sku" in headers else None,
                vendor=(rec.get(headers["vendor"]) or "").strip() or None if "vendor" in headers else None,
                raw_row=raw,
            )
        )
    if not rows:
        raise CsvValidationError("CSV has no data rows.")
    return rows


def load_csv_file(path: str | Path, max_rows: int = 200) -> list[VendorRow]:
    p = Path(path)
    if not p.is_file():
        raise CsvValidationError(f"CSV file not found: {p}")
    return parse_csv_bytes(p.read_bytes(), max_rows=max_rows)
