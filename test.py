import json
import requests

token = "ae3f6314-c2e1-4724-a800-5f2ebb9eb5f6"

headers = {
    "X-QuakeToken": token,
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0"
}

payload = {
    "query": 'app:"nginx"',
    "start": 0,
    "size": 10
}

url = "https://quake.360.net/api/v3/search/quake_service"

try:
    resp = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=30
    )

    print("HTTP状态码:", resp.status_code)
    print("响应头:", dict(resp.headers))
    print("响应正文:")
    print(resp.text)

    # 如果返回的是 JSON，再格式化输出
    try:
        data = resp.json()
        print("JSON格式化结果:")
        print(json.dumps(data, ensure_ascii=False, indent=2))
    except Exception:
        pass

except requests.exceptions.RequestException as e:
    print("请求失败:", e)