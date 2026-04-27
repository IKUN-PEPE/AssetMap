import os

import requests

ZOOMEYE_API_KEY_ENV = "ZOOMEYE_API_KEY"


def get_api_key() -> str:
    api_key = os.getenv(ZOOMEYE_API_KEY_ENV, "").strip()
    if not api_key:
        raise RuntimeError(f"缺少环境变量 {ZOOMEYE_API_KEY_ENV}，请先配置 ZoomEye API Key")
    return api_key

def search(query='app:"nginx"'):
    url = "https://api.zoomeye.org/host/search"
    headers = {
        "API-KEY": get_api_key(),
        "User-Agent": "Mozilla/5.0"
    }
    params = {
        "query": query,
        "page": 1
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        print("状态码:", r.status_code)
        print("响应内容前500字符:")
        print(r.text[:500])

        data = r.json()
        matches = data.get("matches", [])

        for i, item in enumerate(matches[:5], 1):
            ip = item.get("ip")
            if isinstance(ip, list):
                ip = ip[0]

            portinfo = item.get("portinfo", {}) or {}
            port = portinfo.get("port")
            title = portinfo.get("title")

            print(f"[{i}] IP: {ip}  端口: {port}  标题: {title}")

    except Exception as e:
        print("请求失败:", repr(e))

if __name__ == "__main__":
    search()
