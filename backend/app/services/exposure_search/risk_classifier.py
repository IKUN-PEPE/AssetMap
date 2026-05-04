import re

class RiskClassifier:
    def __init__(self, org_keywords: list[str]):
        self.org_keywords = [k.lower() for k in org_keywords]

    def classify(self, title: str, url: str, snippet: str = "") -> tuple[list[str], list[str]]:
        risk_tags = []
        matched_keywords = []
        
        text = f"{title} {url} {snippet}".lower()
        
        # Keyword matching
        for keyword in self.org_keywords:
            if keyword in text:
                matched_keywords.append(keyword)
        
        # Risk tagging
        rules = [
            (r"admin|login|portal|system|mgmt|manage|后台|登录|管理|门户|系统", "疑似后台/登录"),
            (r"vpn|sso|cas|auth|oauth|认证|拨号", "疑似登录页"),
            (r"oa|mail|email|outlook|exchange|office|协同", "疑似办公系统"),
            (r"pan\.baidu\.com|docs\.google\.com|drive\.google\.com|onedrive|share\.weiyun\.com|网盘|分享", "疑似网盘分享"),
            (r"github\.com|gitlab\.com|gitee\.com|code|repo|仓库|代码", "疑似代码托管"),
            (r"\.xls|\.xlsx|\.csv|表格|数据|清单", "疑似表格泄露"),
            (r"\.pdf|\.doc|\.docx|文档|方案|报告|手册", "疑似文档泄露"),
            (r"\.sql|\.db|\.backup|数据库|备份", "疑似数据库泄露"),
            (r"config|password|secret|key|token|conf|配置|密码|密钥", "疑似敏感配置"),
        ]
        
        for pattern, tag in rules:
            if re.search(pattern, text):
                risk_tags.append(tag)
                
        if not risk_tags:
            risk_tags.append("待人工确认")
            
        return list(set(risk_tags)), list(set(matched_keywords))
