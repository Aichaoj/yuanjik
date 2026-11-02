# -*- coding: utf-8 -*-
"""修正 v64 三处：榜单 title 列 / 后台鉴权方法 / 后台路由注册 + serve 回填。"""

# 1) vault.py
V = r'shuzi\server\vault.py'
s = open(V, encoding='utf-8').read()

# 1.1 榜单 SQL 加 m.title
old_sql = """            'SELECT m.member_id AS mid, m.contribution AS contribution,'
            '       m.injections AS injections, s.nickname AS nickname'"""
assert s.count(old_sql) == 1
s = s.replace(old_sql, """            'SELECT m.member_id AS mid, m.contribution AS contribution,'
            '       m.injections AS injections, m.title AS title, s.nickname AS nickname'""")

# 1.2 后台鉴权方法（复用 admin_api 的令牌）
old_lb = "    def leaderboard(self, *, ctx, body, headers):"
assert s.count(old_lb) == 1
s = s.replace(old_lb, '''    def _require_admin(self, headers) -> str:
        """复用 admin_api 的令牌（与曲库/后台同一套，不新造鉴权）。"""
        api = getattr(self, 'admin_api', None)
        if api is None:
            raise AppError(Err.UNAUTHENTICATED, http_status=401, message='后台未启用')
        return api._require_admin(headers)

    def leaderboard(self, *, ctx, body, headers):''')

# 1.3 注册后台路由（自带令牌校验 → auth_required=False）
old_route = "        r.route('POST', '/v1/vault/redeem')(self.redeem)"
assert s.count(old_route) == 1
s = s.replace(old_route, old_route + """
        r.route('GET', '/v1/admin/vault/unrewarded', auth_required=False, rate_scope='api')(self.admin_unrewarded)
        r.route('POST', '/v1/admin/vault/replay', auth_required=False, rate_scope='api')(self.admin_replay)
        r.route('POST', '/v1/admin/vault/report', auth_required=False, rate_scope='api')(self.admin_report)""")

open(V, 'w', encoding='utf-8', newline='\n').write(s)
print('vault.py fixed')

# 2) serve.py 回填 admin_api
S = r'shuzi\server\serve.py'
t = open(S, encoding='utf-8').read()
old = "        self.vault.points_api = self.pay"
assert t.count(old) == 1
t = t.replace(old, old + "\n        self.vault.admin_api = self.admin")
open(S, 'w', encoding='utf-8', newline='\n').write(t)
print('serve.py fixed')
