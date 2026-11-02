import json, urllib.request

tok = open(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\.token").read().strip()

def post(path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request("https://adminapi.yuanjk.cn" + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + tok)
    req.add_header("Encryption", "")
    req.add_header("Cache-Control", "no-cache")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))

r = post("/product/getproductlistadminmanager", {"pageNumber": 1, "pageSize": 500, "name": ""})
lst = r["data"]["list"]
print("totalCount", r["data"]["totalCount"], "returned", len(lst))

# dedupe by coverUrl code -> keep first (they are PF/ZH variants of same goods)
bycode = {}
for it in lst:
    cu = it.get("coverUrl") or ""
    code = cu.split("/")[-1].split("_")[0] if cu else ""
    if not code:
        continue
    if code not in bycode:
        bycode[code] = {
            "code": code,
            "name": it.get("name"),
            "categoryName": it.get("categoryName"),
            "sku": it.get("sku"),
            "price": it.get("price"),
            "marketPrice": it.get("marketPrice"),
            "coverUrl": cu,
            "count": 0,
        }
    bycode[code]["count"] += 1

out = {
    "totalCount": r["data"]["totalCount"],
    "distinct_codes": len(bycode),
    "products": [bycode[k] for k in sorted(bycode)],
}
with open(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\products_admin.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("saved", len(bycode))
