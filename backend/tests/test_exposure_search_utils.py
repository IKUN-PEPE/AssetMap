import pytest

from app.api.exposure_search import classify_result_import_type
from app.services.exposure_search.query_builder import QueryBuilder
from app.services.exposure_search.risk_classifier import RiskClassifier


def test_query_builder():
    builder = QueryBuilder(
        org_keywords=["娣卞湷鍦伴搧"],
        title_keywords=["鍚庡彴"],
        file_types=["pdf"],
        sites=["pan.baidu.com"],
    )
    queries = builder.build_queries()

    assert '"娣卞湷鍦伴搧"' in queries
    assert '"娣卞湷鍦伴搧" "鍚庡彴"' in queries
    assert '"娣卞湷鍦伴搧" filetype:pdf' in queries
    assert 'site:pan.baidu.com "娣卞湷鍦伴搧"' in queries


def test_risk_classifier():
    classifier = RiskClassifier(org_keywords=["娣卞湷鍦伴搧", "娣遍搧", "SZMC"])

    tags, keywords = classifier.classify("娣卞湷鍦伴搧鍚庡彴绠＄悊绯荤粺", "http://example.com/login")
    assert "疑似后台/登录" in tags
    assert "娣卞湷鍦伴搧" in keywords

    tags, keywords = classifier.classify("2024璐㈠姟鎶ヨ〃", "http://example.com/files/SZMC_internal.xlsx")
    assert "疑似表格泄露" in tags
    assert "szmc" in keywords

    tags, keywords = classifier.classify("娣卞湷鍦伴搧鍐呴儴璧勬枡", "https://pan.baidu.com/s/123")
    assert "疑似网盘分享" in tags


def test_risk_classifier_sensitive_config():
    classifier = RiskClassifier(org_keywords=["test"])
    tags, keywords = classifier.classify("Config File", "http://example.com/config.php?pass=123")
    assert "疑似敏感配置" in tags


def test_classify_result_import_type_identifies_assets_and_clues():
    assert classify_result_import_type("https://example.com/portal", None) == "asset"
    assert classify_result_import_type("https://example.com/a.pdf", "pdf") == "clue"
    assert classify_result_import_type("https://github.com/example/repo", None) == "clue"
    assert classify_result_import_type("https://pan.baidu.com/s/123456", None) == "clue"
