"""Coverage for country-specific WAHA proxy configuration parsing."""
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from waha_service import _region_proxies


def test_region_proxies_normalizes_regions_and_excludes_bad_entries():
    parsed = _region_proxies(
        '{"ke":{"server":"ke.example:3128","username":"merchant","password":"secret"},'
        '"US":{"server":"us.example:3128"},"ZA":{},"bad":"proxy"}'
    )

    assert parsed == {
        "KE": {"server": "ke.example:3128", "username": "merchant", "password": "secret"},
        "US": {"server": "us.example:3128"},
    }


def test_region_proxies_rejects_invalid_json():
    assert _region_proxies("not-json") == {}
