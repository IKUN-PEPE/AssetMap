class QueryBuilder:
    def __init__(
        self,
        org_keywords: list[str],
        title_keywords: list[str] = None,
        url_keywords: list[str] = None,
        file_types: list[str] = None,
        sites: list[str] = None
    ):
        self.org_keywords = org_keywords
        self.title_keywords = title_keywords or []
        self.url_keywords = url_keywords or []
        self.file_types = file_types or []
        self.sites = sites or []

    def build_queries(self) -> list[str]:
        queries = []
        
        for org in self.org_keywords:
            # Basic org search
            queries.append(f'"{org}"')
            
            # Title keywords
            for tk in self.title_keywords:
                queries.append(f'"{org}" "{tk}"')
                queries.append(f'intitle:"{org}" "{tk}"')
            
            # URL keywords
            for uk in self.url_keywords:
                queries.append(f'"{org}" inurl:{uk}')
            
            # File types
            for ft in self.file_types:
                queries.append(f'"{org}" filetype:{ft}')
            
            # Sites (Google Dorking style)
            for site in self.sites:
                queries.append(f'"{org}" site:{site}')

        return list(set(queries))
