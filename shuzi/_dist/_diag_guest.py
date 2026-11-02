# 诊断：直接构造 Stack 并调用游客登录，抓完整堆栈（不改任何代码）
import os
import sys
import traceback

STAGE = r"D:\shuzi\_dist\_stage_site"
sys.path.insert(0, r"D:\shuzi\server")
sys.path.insert(0, STAGE)
os.environ["SHUZI_SRC_ROOT"] = STAGE
os.environ["SHUZI_DATA"] = os.path.join(STAGE, "data", "state.db")

import serve  # noqa: E402

try:
    st = serve.Stack()
    print("Stack 构造成功")
    h = getattr(st, "handler", None) or getattr(st, "api", None)
    print("可用属性:", [a for a in dir(st) if not a.startswith("_")][:20])
except Exception:
    print("=== Stack 构造失败堆栈 ===")
    traceback.print_exc()
    sys.exit(1)

# 走 HTTP 处理器里的同一入口
for name in ("guest_login", "handle_guest", "api_guest"):
    fn = getattr(st, name, None)
    if fn:
        print("调用", name)
        try:
            print(fn({"device_id": "diag-device-1"}, {}, "127.0.0.1"))
        except Exception:
            print("=== 调用堆栈 ===")
            traceback.print_exc()
        break
else:
    print("未找到 guest 入口，改为直接跑 Router")
    try:
        import json
        status, body = st.router.handle("POST", "/v1/auth/guest", body={"device_id": "d1"}, headers={}, client_ip="127.0.0.1")
        print(status, json.dumps(body, ensure_ascii=False)[:300])
    except Exception:
        traceback.print_exc()
