import sys, json, urllib.request, base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

# ── 脱密（2026-10-10）：口令/密钥不再写在文件里，运行时从保险柜取 ──
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..', '..')))
from _zfcred import cred          # 见 _zfcred.py（本文件不含任何真值）

KEY = cred("SHUZI_AES_KEY", "shuzi.aes.key").encode()  # first 16 chars of the frontend constant

def aes_ecb_b64(plain: str) -> str:
    c = AES.new(KEY, AES.MODE_ECB)
    return base64.b64encode(c.encrypt(pad(plain.encode(), 16))).decode()

def post(url, payload, token=None, timeout=40):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Cache-Control", "no-cache")
    if token:
        req.add_header("Authorization", "Bearer " + token)
        req.add_header("Encryption", "")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

if __name__ == "__main__":
    username = "yuanqi"
    password = cred("SHUZI_ADMIN_PWD", "nexus.redcode.basic")
    r = post("https://adminapi.yuanjk.cn/login/index",
             {"username": username, "password": aes_ecb_b64(password)})
    print(json.dumps(r, ensure_ascii=False)[:600])
    tok = (r.get("data") or {}).get("token")
    if not tok:
        sys.exit(1)
    open(r"D:\Deepseek智能体\AI元健康\shuzi\_verify_v9\.token", "w").write(tok)
    print("TOKEN_SAVED")
