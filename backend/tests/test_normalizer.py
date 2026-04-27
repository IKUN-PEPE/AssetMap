from app.services.normalizer.service import build_url_hash, normalize_url


def test_normalize_url_root_without_slash_is_compatible_with_historic_form():
    assert normalize_url("https://example.com") == "https://example.com/"


def test_normalize_url_root_with_slash_keeps_historic_form():
    assert normalize_url("https://example.com/") == "https://example.com/"


def test_normalize_url_adds_https_and_preserves_path_while_stripping_query_and_fragment():
    assert normalize_url("example.com/login?x=1#top") == "https://example.com/login"


def test_normalize_url_preserves_explicit_port():
    assert normalize_url("https://example.com:8443/admin") == "https://example.com:8443/admin"


def test_normalize_url_distinguishes_scheme_and_default_port_variants():
    assert normalize_url("http://example.com/login") == "http://example.com/login"
    assert normalize_url("https://example.com/login") == "https://example.com/login"
    assert normalize_url("https://example.com:443/admin") == "https://example.com:443/admin"


def test_normalize_url_strips_auth_and_lowercases_host_but_keeps_path():
    assert normalize_url("HTTPS://User:Pass@EXAMPLE.COM:8443/admin?x=1#top") == "https://example.com:8443/admin"


def test_normalize_url_supports_ipv6_and_keeps_path():
    assert normalize_url("https://[2001:db8::1]:8443/admin") == "https://[2001:db8::1]:8443/admin"


def test_normalize_url_distinguishes_different_paths():
    assert normalize_url("https://example.com/admin") != normalize_url("https://example.com/login")


def test_normalize_url_returns_empty_string_for_invalid_url():
    assert normalize_url("https:///broken") == ""


def test_build_url_hash_is_deterministic():
    assert build_url_hash("https://example.com/admin") == build_url_hash("https://example.com/admin")


def test_build_url_hash_treats_root_with_and_without_slash_as_same_value():
    assert build_url_hash("https://example.com") == build_url_hash("https://example.com/")
