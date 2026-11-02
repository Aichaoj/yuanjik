# -*- coding: utf-8 -*-
"""线上验收（v71 补发版）：版本、默认定时 5 分钟与不定时排最后、背面拾取、推荐接口。"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
B = 'https://shuzi.yuanjk.cn'


def get(p):
    r = urllib.request.Request(B + p)
    r.add_header('User-Agent', 'Mozilla/5.0')
    return urllib.request.urlopen(r, timeout=20).read().decode('utf-8', 'replace')


def main():
    v = json.loads(get('/version.json')).get('web')
    print('  [%s] V1 版本 -> %s' % ('PASS' if v == '71' else 'FAIL', v))

    h = get('/')
    sel = '<option value="5" selected>5 分钟</option>'
    ok_timer = (sel in h) and (h.find('不定时') > h.find('30 分钟') > 0)
    print('  [%s] V2 定时默认 5 分钟、不定时在最后' % ('PASS' if ok_timer else 'FAIL'))

    b = get('/body3d.js')
    print('  [%s] V3 背面拾取兜底已上线' % ('PASS' if 'thr = 0.085' in b else 'FAIL'))

    m = get('/music.js')
    print('  [%s] V4 播放即启用默认定时' % ('PASS' if 'mpTimer' in m and 'startTimer(Number' in m else 'FAIL'))

    d = json.loads(get('/api/v1/music/recommend')).get('data') or {}
    print('  [%s] V5 推荐接口在线 tones=%s tracks=%d' %
          ('PASS' if d.get('tones') else 'FAIL',
           [t['id'] for t in d.get('tones') or []], len(d.get('tracks') or [])))


if __name__ == '__main__':
    main()
