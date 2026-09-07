"""Coverage for country-specific WAHA proxy configuration parsing."""
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from waha_service import _region_nodes, _region_proxies


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


def test_region_nodes_normalize_only_http_urls():
    parsed = _region_nodes(
        '{"ke":"https://102.204.0.72.sslip.io/",'
        '"US":"http://us.example","ZA":"not-a-url","bad":42}'
    )

    assert parsed == {
        "KE": "https://102.204.0.72.sslip.io",
        "US": "http://us.example",
    }


def test_region_nodes_reject_invalid_json():
    assert _region_nodes("not-json") == {}
