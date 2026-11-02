# -*- coding: utf-8 -*-
p = r'shuzi\_verify_v57\test_music_and_qr.py'
s = open(p, encoding='utf-8').read()
old = """        # 模拟另一台设备：新 context（没有 localStorage 的“今日已报”标记）
        ctx2 = b.new_context(**ctx_args)
        ctx2.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);"
            "localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok), json.dumps(dev + '-b')))"""
new = """        # 模拟“手机登录”：新设备新会话（重新登录拿新令牌，最贴近真实场景）
        dev2 = dev + '-mobile'
        st2, r2 = api('/auth/password/login', 'POST',
                      {'identifier': ph, 'password': 'Pwd12345', 'device_id': dev2})
        d2 = r2.get('data') or {}
        tok2 = d2.get('access_token')
        ctx2 = b.new_context(**ctx_args)
        ctx2.add_init_script(
            "try{localStorage.setItem('yh.access_token',%s);"
            "localStorage.setItem('yh.refresh_token',%s);"
            "localStorage.setItem('yh.device_id',%s);}catch(e){}"
            % (json.dumps(tok2), json.dumps(d2.get('refresh_token') or ''), json.dumps(dev2)))"""
assert s.count(old) == 1, s.count(old)
s = s.replace(old, new)
s = s.replace("A('Q5 换设备后仍是同一份（不必重填）', '饮食 很好' in s3 and '心情 一般' in s3, s3[:120])",
              "A('Q5 手机登录后仍是同一份（不必重填）', st2 == 200 and '饮食 很好' in s3 and '心情 一般' in s3,\n          'login=%s :: %s' % (st2, s3[:110]))")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('patched Q5')
