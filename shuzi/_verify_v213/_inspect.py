# -*- coding: utf-8 -*-
import sqlite3
c = sqlite3.connect(r'D:\Deepseek智能体\AI元健康\shuzi\data\state.db')
print([r[1] for r in c.execute("PRAGMA table_info(profile)")])
print(c.execute("SELECT COUNT(*) FROM profile").fetchone())
q = """SELECT p.member_id, ap.phone, p.birth_local
       FROM profile p
       LEFT JOIN account a ON a.member_id = p.member_id
       LEFT JOIN account_password ap ON ap.account_id = a.account_id
       WHERE ap.phone IN ('13900000201','13900000202')"""
print(c.execute(q).fetchall())
print(c.execute("SELECT COUNT(*) FROM member_spacetime").fetchone())
print(c.execute("SELECT member_id FROM member_spacetime LIMIT 5").fetchall())
