import pytest
from app.services.exposure_search.query_builder import QueryBuilder
from app.services.exposure_search.risk_classifier import RiskClassifier

def test_query_builder():
    builder = QueryBuilder(
        org_keywords=["深圳地铁"],
        title_keywords=["后台"],
        file_types=["pdf"],
        sites=["pan.baidu.com"]
    )
    queries = builder.build_queries()
    
    # Check for basic org search
    assert '"深圳地铁"' in queries
    # Check for title keyword search (updated pattern)
    assert '"深圳地铁" "后台"' in queries
    # Check for file type search
    assert '"深圳地铁" filetype:pdf' in queries
    # Check for site search (updated pattern: site:SITE {ORG})
    assert 'site:pan.baidu.com "深圳地铁"' in queries

def test_risk_classifier():
    classifier = RiskClassifier(org_keywords=["深圳地铁", "深铁", "SZMC"])
    
    # Test background/login detection
    tags, keywords = classifier.classify("深圳地铁后台管理系统", "http://example.com/login")
    assert "疑似后台/登录" in tags
    assert "深圳地铁" in keywords
    
    # Test document leak detection
    tags, keywords = classifier.classify("2024财务报表", "http://example.com/files/SZMC_internal.xlsx")
    assert "疑似表格泄露" in tags
    assert "szmc" in keywords
    
    # Test cloud disk detection
    tags, keywords = classifier.classify("深圳地铁内部资料", "https://pan.baidu.com/s/123")
    assert "疑似网盘分享" in tags

def test_risk_classifier_sensitive_config():
    classifier = RiskClassifier(org_keywords=["test"])
    tags, keywords = classifier.classify("Config File", "http://example.com/config.php?pass=123")
    assert "疑似敏感配置" in tags
