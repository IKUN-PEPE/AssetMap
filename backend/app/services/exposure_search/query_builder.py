class QueryBuilder:
    def __init__(
        self,
        org_keywords: list[str],
        title_keywords: list[str] = None,
        url_keywords: list[str] = None,
        file_types: list[str] = None,
        sites: list[str] = None,
        exclude_keywords: list[str] = None
    ):
        self.org_keywords = [k.strip() for k in org_keywords if k.strip()]
        self.title_keywords = title_keywords or []
        self.url_keywords = url_keywords or []
        self.file_types = file_types or []
        self.sites = sites or []
        # Default exclusions to reduce noise
        self.exclude_keywords = exclude_keywords or ["招聘", "新闻", "公告", "采购", "招标"]

    def build_queries(self) -> list[str]:
        if not self.org_keywords:
            return []

        queries = []
        
        # Helper: Combined Org Query (e.g. ("A" OR "B" OR "C"))
        if len(self.org_keywords) > 1:
            combined_org = "(" + " OR ".join([f'"{k}"' for k in self.org_keywords]) + ")"
        else:
            combined_org = f'"{self.org_keywords[0]}"'

        # Noise string (e.g. -招聘 -新闻)
        noise_reduction = " " + " ".join([f"-{k}" for k in self.exclude_keywords])

        # 1. Basic & Aliases
        for org in self.org_keywords:
            queries.append(f'"{org}"')
            queries.append(f'"{org}"{noise_reduction}')
        
        if len(self.org_keywords) > 1:
            queries.append(combined_org)
            queries.append(f'{combined_org}{noise_reduction}')

        # 2. Admin / Backend / Login
        admin_keywords = ["后台管理", "管理系统", "登录", "统一认证", "SSO", "VPN", "OA", "运维平台"]
        # Use user-provided keywords if available, otherwise defaults
        tk_list = self.title_keywords if self.title_keywords else admin_keywords
        
        for tk in tk_list:
            # Pattern: "{ORG}" "{TK}"
            queries.append(f'{combined_org} "{tk}"')
            # Pattern: intitle:"{ORG}" "{TK}"
            queries.append(f'intitle:{combined_org} "{tk}"')
            # Pattern: intitle:"{TK}" "{ORG}"
            queries.append(f'intitle:"{tk}" {combined_org}')

        # 3. URL Keywords
        uk_list = self.url_keywords if self.url_keywords else ["login", "admin", "manage", "sso", "vpn", "oa", "api", "swagger"]
        for uk in uk_list:
            queries.append(f'inurl:{uk} {combined_org}')

        # 4. File Types
        for ft in self.file_types:
            queries.append(f'{combined_org} filetype:{ft}')
            # Sensitive documents
            sensitive_docs = ["通讯录", "账号", "密码", "资产清单", "系统清单", "接口文档", "测试报告"]
            for sd in sensitive_docs:
                queries.append(f'{combined_org} "{sd}" filetype:{ft}')

        # 5. Site Specific (GitHub, Pan, etc.)
        for site in self.sites:
            queries.append(f'site:{site} {combined_org}')
            
            if site == "github.com":
                github_extras = ["password", "token", "secret", "config", "application.yml", ".env"]
                for ext in github_extras:
                    queries.append(f'site:github.com {combined_org} {ext}')
            
            if "pan.baidu.com" in site or "baidu" in site:
                pan_extras = ["提取码", "分享链接", "下载地址"]
                for ext in pan_extras:
                    queries.append(f'site:pan.baidu.com {combined_org} "{ext}"')

        # Limit to a reasonable number of high-quality queries to avoid rate limiting
        # Deduplicate and return
        return list(set(queries))
