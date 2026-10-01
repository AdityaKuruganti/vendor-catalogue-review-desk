import pytest

from app.services.csv_loader import CsvValidationError, load_csv_file, parse_csv_bytes


def test_sample_csv_loads():
    rows = load_csv_file("data/sample_vendor_rows.csv")
    assert len(rows) == 10
    assert rows[0].sku == "W-DRS-RED-L"
    assert "Maxi Dress" in rows[0].raw_row


def test_missing_raw_row_column():
    with pytest.raises(CsvValidationError, match="raw_row"):
        parse_csv_bytes(b"sku,name\nA,B\n")


def test_blank_rows_skipped_and_bom_handled():
    data = "\ufeffraw_row\nMen shirt blue\n\n  \nKids tee red\n".encode("utf-8")
    assert [r.raw_row for r in parse_csv_bytes(data)] == ["Men shirt blue", "Kids tee red"]


def test_row_limit():
    data = ("raw_row\n" + "\n".join(f"item {i}" for i in range(5))).encode()
    with pytest.raises(CsvValidationError, match="Too many"):
        parse_csv_bytes(data, max_rows=3)
