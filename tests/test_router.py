import pytest

from app.workflow.router import detect_demographic


@pytest.mark.parametrize("text,expected", [
    ("Women's Floral Summer Maxi Dress", "WOMEN"),
    ("W-DRS-RED-L dress", "WOMEN"),
    ("Ladies green kurta", "WOMEN"),
    ("Kids yellow t-shirt", "KIDS"),
    ("Girls pink frock", "KIDS"),
    ("Boys blue shorts", "KIDS"),
    ("Gents navy blue formal shirt", "MEN"),
    ("Men's black jeans", "MEN"),  # 'men' must NOT be mistaken for 'women'
])
def test_detect_demographic(text, expected):
    assert detect_demographic(text) == expected
