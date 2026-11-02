# -*- coding: utf-8 -*-
import re, io, collections, json, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
html = io.open(r'D:\Deepseek智能体\AI元健康\shuzi\web\index.html', encoding='utf-8').read()
ids = re.findall(r'\sid="([^"]+)"', html)
dup = [k for k, v in collections.Counter(ids).items() if v > 1]
print('index.html id 总数:', len(ids), '重复:', dup)
js = io.open(r'D:\Deepseek智能体\AI元健康\shuzi\web\app.js', encoding='utf-8').read()
print('function renderInvite 次数:', js.count('function renderInvite'))
print('function maybeAutoBindInvite:', js.count('function maybeAutoBindInvite'))
print('function saveNickname:', js.count('function saveNickname'))
print('function copyInvite:', js.count('function copyInvite'))
need = ['inviteLink', 'inviteSharePreview', 'myReferrer', 'inNickname',
        'btnSaveNickname', 'homeInviteHint', 'nicknameErr', 'btnCopyInvite', 'inviteCode']
print('HTML 缺失元素:', [i for i in need if ('id="%s"' % i) not in html])
for f in ['index.html', 'style.css', 'app.js']:
    print(f, os.path.getsize(os.path.join(r'D:\Deepseek智能体\AI元健康\shuzi\web', f)), 'bytes')
rep = json.load(io.open(r'D:\Deepseek智能体\AI元健康\shuzi\web\_shots_v6\report.json', encoding='utf-8'))
print('断言:', rep['assertions_passed'], '/', rep['assertions_total'], '失败:', rep['assertions_failed'])
print('console errors:', rep['console_errors'], ' page errors:', rep['page_errors'])
print('截图数:', len(rep['screenshots']))
