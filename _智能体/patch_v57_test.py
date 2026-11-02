# -*- coding: utf-8 -*-
p = r'shuzi\_verify_v57\test_music_and_qr.py'
s = open(p, encoding='utf-8').read()
s = s.replace("""def route_web(page):
    for name, ct in (('energy-flow.js', 'application/javascript'),
                     ('music.js', 'application/javascript'),
                     ('music.json', 'application/json'),
                     ('version.json', 'application/json')):
        page.route('**/%s*' % name, lambda r, n=name, c=ct: r.fulfill(
            path=os.path.join(WEB, n), content_type=c))
""", """def route_web(page):
    # v57：music.js / music.json / version.json / energy-flow.js 已进本地静态白名单，
    # 这里不再需要 page.route 兜底（线上 IIS 本来就直出）
    return
""")
open(p, 'w', encoding='utf-8', newline='\n').write(s)
print('routes removed:', 'page.route' not in s)
