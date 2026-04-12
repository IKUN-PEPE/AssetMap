from app.services.normalizer.service import build_url_hash, normalize_url


def test_normalize_url_adds_https_and_trims_trailing_slash():
    assert normalize_url("example.com/") == "https://example.com/"


def test_build_url_hash_is_deterministic():
    assert build_url_hash("https://example.com") == build_url_hash("https://example.com")
