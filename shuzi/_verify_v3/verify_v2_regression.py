# -*- coding: utf-8 -*-
"""
AI 健康 · 元健康 —— 前端 v2「今日健康指数」验证脚本（Playwright）

★ 全部接口用 page.add_init_script 覆盖 window.fetch 做内存 stub，
  不写任何文件到 server 目录，也不依赖真实后端。
★ 被测页面由本机静态服务提供（python -m http.server --directory D:\\shuzi\\web），
  stub 只拦截 JS 发起的 fetch，静态资源仍走真实 HTTP。

输出：D:\\shuzi\\web\\_shots_v2\\*.png + 控制台断言报告 + report.json
"""
from __future__ import annotations

import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get('VERIFY_BASE', 'http://127.0.0.1:15241/')
OUT = r'D:\Deepseek智能体\AI元健康\shuzi\web\_shots_v3_v2reg'

# ── 三种状态的内存 stub 数据 ─────────────────────────────────────────
IDX_FULL = {
    "score": 82,
    "band_code": "B", "band": "良",
    "basis": "按出生时空与当日运气推算·非诊断",
    "formula": "demo-formula-v1", "ref": 0.35,
    "channels": [
        {"channel": "心", "raw": 0.12, "direction": "偏亢", "attention": True},
        {"channel": "肺", "raw": -0.08, "direction": "偏虚", "attention": False},
    ],
    "attention": [
        {"channel": "心", "direction": "偏亢", "raw": 0.12},
        {"channel": "肝", "direction": "偏虚", "raw": -0.19},
    ],
    "windows": [
        {"name": "心经当令", "start": "11:00", "end": "13:00", "kind": "golden"},
        {"name": "肺经当令", "start": "03:00", "end": "05:00", "kind": "normal"},
        {"name": "跨零时段", "start": "23:00", "end": "01:00", "kind": "golden"},
    ],
    "rule_ids": ["R-001", "R-014"],
    "phase_note": "今日时相平稳",
}

DAILY_INDEX = {
    "date": "2026-10-08",
    "baseline_established": False,
    "observation_count": 3,
    "min_observations": 7,
    "calibration": {
        "observation_count": 3, "min_observations": 7,
        "progress_text": "基线建立中（3/7）",
        "note": "校准完成后，系统才能给出「相对你自己」的节律偏移。",
    },
    "pillars": ["庚", "辰", "甲", "申"],
    "yunqi": {"year": "火运太过"},
    "channels": [],
    "focus": [],
    "level": None, "level_name": None,
    "text": {"text": "今日节律平稳，宜早睡、适度活动。", "guardrail_action": "pass",
             "guardrail_hits": [], "rule_version": "r1", "param_hash": "ph-demo"},
    "lineage": ["[R-001] 时相平稳｜出处：演示典籍｜要点：按当日时相安排作息"],
    "index": IDX_FULL,
    "personalized": None,
    "disclaimer": "本产品不属于医疗器械，不用于疾病的诊断、治疗或预防，不替代专业医疗意见。"
                  "所提供内容为基于个人时空节律的生活方式参考，如出现持续不适请及时就医。",
    "referral": "建议咨询执业医师或前往正规医疗机构。",
    "ai_generated": True,
    "rule_version": "r1", "engine_version": "e1", "param_hash": "ph-demo",
}

DAILY_NULL = json.loads(json.dumps(DAILY_INDEX))
DAILY_NULL["index"] = None
DAILY_NULL["calibration"] = {"observation_count": 0, "min_observations": 7,
                             "progress_text": "基线建立中（0/7）"}
DAILY_NULL["observation_count"] = 0

DAILY_PERSONALIZED = json.loads(json.dumps(DAILY_INDEX))
DAILY_PERSONALIZED["baseline_established"] = True
DAILY_PERSONALIZED["observation_count"] = 9
DAILY_PERSONALIZED["calibration"] = None
DAILY_PERSONALIZED["level"] = "L2"
DAILY_PERSONALIZED["level_name"] = "宜养"
DAILY_PERSONALIZED["focus"] = [{"channel": "心", "delta": 0.21, "direction": "偏亢"}]
DAILY_PERSONALIZED["channels"] = [
    {"channel": n, "delta": d, "direction": ("偏亢" if d > 0 else ("偏虚" if d < 0 else "平"))}
    for n, d in [("心", 0.21), ("肺", -0.11), ("肝", 0.06), ("脾", -0.03), ("肾", 0.09),
                 ("胆", -0.05), ("胃", 0.02), ("大肠", -0.07), ("小肠", 0.04), ("膀胱", -0.02),
                 ("三焦", 0.08), ("心包", -0.06)]
]
DAILY_PERSONALIZED["personalized"] = {
    "level_name": "宜养",
    "focus": [{"channel": "心", "direction": "偏亢", "raw": 0.18},
              {"channel": "肾", "direction": "偏虚", "raw": -0.14}],
    "summary": "结合你自己的历史记录，今日宜早睡、午后适度活动。",
}

HISTORY_ITEMS = [
    {"date": "2026-10-08", "observed": {"心": 0.12, "肺": -0.08}},
    {"date": "2026-10-07", "observed": {"心": 0.10}},
    {"date": "2026-10-06", "observed": {"心": 0.09}},
]

SCENARIOS = {
    "index": DAILY_INDEX,
    "index_null": DAILY_NULL,
    "personalized": DAILY_PERSONALIZED,
}

STUB_TEMPLATE = r"""
(function () {
  var SCEN = __SCEN__;                 // 全部场景数据
  var NAME = __NAME__;                 // 本次运行使用的场景名
  var HIST = __HIST__;
  window.__stubCalls = [];
  function envelope(data) {
    return new Response(JSON.stringify({
      code: 0, message: 'ok', data: data, trace_id: 'stub-trace-0001'
    }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }
  var realFetch = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = function (url, init) {
    var u = String(url || '');
    window.__stubCalls.push(u);
    if (u.indexOf('/auth/guest') >= 0) {
      return Promise.resolve(envelope({ access_token: 'stub-access', refresh_token: 'stub-refresh' }));
    }
    if (u.indexOf('/profile/birth') >= 0) { return Promise.resolve(envelope({ ok: true })); }
    if (u.indexOf('/rhythm/daily') >= 0) { return Promise.resolve(envelope(SCEN[NAME])); }
    if (u.indexOf('/rhythm/history') >= 0) {
      return Promise.resolve(envelope({ items: HIST, next_cursor: null, has_more: false }));
    }
    if (u.indexOf('/checkin') >= 0) {
      return Promise.resolve(envelope({ observation_count: 4, established: false, streak_days: 3 }));
    }
    return Promise.resolve(envelope({}));
  };
  window.__stubRealFetch = realFetch;
})();
"""

FORBIDDEN = ['生命先知', '先知日历', '八息象数', '八息基因', 'ZYDGENE', '中易道',
             '九元情绪', '华医道', '老祖太极', '加密', '抗量子', '密钥',
             '确诊', '治愈', '疗效']

RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:300]})
    print(('  [PASS] ' if ok else '  [FAIL] ') + name + (('  → ' + str(detail)[:200]) if detail else ''))


def visible_text_sans_compliance(page):
    """取今日节律屏的可见文字，剔除合规声明区与危机区（那两处是法定固定表述）"""
    return page.evaluate("""() => {
      const skipIds = ['complianceCard', 'crisisBox'];
      const root = document.querySelector('#screen-rhythm');
      const parts = [];
      (function walk(el) {
        for (const ch of el.children) {
          if (ch.id && skipIds.includes(ch.id)) continue;
          if (ch.children.length === 0) {
            const t = (ch.textContent || '').trim();
            if (t) parts.push(t);
          } else { walk(ch); }
        }
      })(root);
      return parts.join('\\n');
    }""")


def build_stub(scenario):
    return (STUB_TEMPLATE
            .replace('__SCEN__', json.dumps(SCENARIOS, ensure_ascii=False))
            .replace('__NAME__', json.dumps(scenario))
            .replace('__HIST__', json.dumps(HISTORY_ITEMS, ensure_ascii=False)))


def open_rhythm(page, scenario):
    """走完整建档流程 → 今日节律屏"""
    page.goto(BASE, wait_until='load')
    page.wait_for_selector('#screen-home:not([hidden])')
    page.click('#btnStart')
    page.wait_for_selector('#screen-profile:not([hidden])')
    page.fill('#inBirthDate', '1990-05-20')
    page.fill('#inBirthTime', '08:30')
    page.select_option('#inCity', '北京')
    page.check('#inConsent')
    page.click('#btnSubmitProfile')
    page.wait_for_selector('#screen-rhythm:not([hidden])', timeout=8000)
    page.wait_for_selector('#busy', state='hidden', timeout=8000)
    page.wait_for_selector('#indexBody .idx-score, #indexBody .idx-pending', timeout=8000)
    page.wait_for_timeout(300)
    # 等建档成功的 toast 自然消失，保证截图干净
    try:
        page.wait_for_selector('#toast', state='hidden', timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(200)


def run_scenario(pw, scenario, width, height):
    tag = '%dx%d' % (width, height)
    print('\n=== 场景 %s @ %s ===' % (scenario, tag))
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={'width': width, 'height': height},
                              device_scale_factor=1)
    try:
        ctx.grant_permissions(['clipboard-read', 'clipboard-write'],
                              origin=BASE.rstrip('/'))
    except Exception:
        pass
    page = ctx.new_page()
    console_errors, page_errors = [], []
    page.on('console', lambda m: console_errors.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: page_errors.append(str(e)))
    page.add_init_script(build_stub(scenario))
    open_rhythm(page, scenario)

    shot = os.path.join(OUT, 'shot_%s_%s.png' % (tag, scenario))
    page.screenshot(path=shot, animations='disabled')
    print('  截图 %s' % shot)

    # ── 通用断言 ───────────────────────────────────────────────
    check('[%s/%s] console 无 error' % (scenario, tag), not console_errors, console_errors)
    check('[%s/%s] 无未捕获异常' % (scenario, tag), not page_errors, page_errors)

    sw = page.evaluate('() => ({sw: document.documentElement.scrollWidth, iw: window.innerWidth})')
    check('[%s/%s] 无横向滚动' % (scenario, tag), sw['sw'] <= sw['iw'] + 1, sw)

    idx_box = page.evaluate("""() => {
      const el = document.querySelector('#indexCard');
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {top: r.top, bottom: r.bottom, h: window.innerHeight};
    }""")
    check('[%s/%s] 指数卡在首屏内' % (scenario, tag),
          idx_box and idx_box['top'] < idx_box['h'], idx_box)

    first_card = page.evaluate("""() => {
      const cards = [...document.querySelectorAll('#screen-rhythm > .card, #screen-rhythm > article.card')];
      return cards.length ? cards[0].id : null;
    }""")
    check('[%s/%s] 指数卡是结果页首卡' % (scenario, tag), first_card == 'indexCard', first_card)

    score_in_fold = page.evaluate("""() => {
      const el = document.querySelector('#indexScore') || document.querySelector('#indexPending');
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {bottom: r.bottom, h: window.innerHeight};
    }""")
    check('[%s/%s] 分数/生成中文案在首屏可见' % (scenario, tag),
          score_in_fold and score_in_fold['bottom'] < score_in_fold['h'], score_in_fold)

    tap = page.evaluate("""() => {
      const sel = ['#attentionBody .att-tag', '#btnCopyShare', '#btnCheckin', '#btnHistory',
                   '#btnBack', '#btnStart', '#btnHomeRhythm'];
      const out = [];
      for (const s of sel) {
        for (const e of document.querySelectorAll(s)) {
          if (e.offsetParent === null && e.getClientRects().length === 0) continue;
          const r = e.getBoundingClientRect();
          if (r.width > 0) out.push([s, Math.round(r.height)]);
        }
      }
      return out;
    }""")
    check('[%s/%s] 可见按钮点击区 ≥44px' % (scenario, tag),
          all(v >= 44 for _, v in tap), tap)

    ban = [w for w in FORBIDDEN if w in visible_text_sans_compliance(page)]
    check('[%s/%s] 结果页无禁用词（合规区外）' % (scenario, tag), not ban, ban)

    body = page.text_content('#screen-rhythm') or ''
    check('[%s/%s] 保留 AI 生成标识' % (scenario, tag), '本内容由 AI 生成' in body)
    check('[%s/%s] 保留免责声明' % (scenario, tag),
          page.is_visible('#complianceCard') and '不属于医疗器械' in body)
    check('[%s/%s] 分享文案含站点链接' % (scenario, tag),
          'https://shuzi.yuanjk.cn' in (page.text_content('#shareText') or ''),
          page.text_content('#shareText'))

    if scenario == 'index':
        check('[%s/%s] 分数=82' % (scenario, tag), page.text_content('#indexScore').strip() == '82',
              page.text_content('#indexScore'))
        band_cls = page.get_attribute('#indexBand', 'class')
        check('[%s/%s] 分档胶囊=良 / 蓝色' % (scenario, tag),
              page.text_content('#indexBand').strip() == '良' and 'tone-b' in band_cls, band_cls)
        basis = page.text_content('#indexBasis') or ''
        check('[%s/%s] basis 原文可见' % (scenario, tag), '按出生时空与当日运气推算' in basis, basis)
        tags = page.query_selector_all('#attentionBody .att-tag')
        check('[%s/%s] 今日关注标签=2' % (scenario, tag), len(tags) == 2, len(tags))
        check('[%s/%s] 首个标签="心 偏亢"' % (scenario, tag),
              '心' in tags[0].inner_text() and '偏亢' in tags[0].inner_text(),
              tags[0].inner_text())
        h44 = page.evaluate("""() => {
          const els = [...document.querySelectorAll('#attentionBody .att-tag, #btnCopyShare')];
          return els.map(e => e.getBoundingClientRect().height);
        }""")
        check('[%s/%s] 点击区 ≥44px' % (scenario, tag), all(h >= 44 for h in h44), h44)

        tags[0].click()
        page.wait_for_timeout(150)
        dtext = page.text_content('#attDetail') or ''
        check('[%s/%s] 标签展开显示 raw 0.12' % (scenario, tag),
              page.is_visible('#attDetail') and '0.12' in dtext, dtext[:160])
        check('[%s/%s] 展开说明无诊疗词' % (scenario, tag),
              not any(w in dtext for w in ['诊断', '确诊', '治疗', '治愈', '疗效', '疾病']), dtext[:160])
        page.screenshot(path=os.path.join(OUT, 'shot_%s_%s_attention_open.png' % (tag, scenario)),
                        animations='disabled')

        rows = page.query_selector_all('#windowsBody .win-row')
        check('[%s/%s] 黄金时段=3 条' % (scenario, tag), len(rows) == 3, len(rows))
        wtext = page.text_content('#windowsBody') or ''
        check('[%s/%s] 含 心经当令 11:00–13:00' % (scenario, tag),
              '心经当令' in wtext and '11:00–13:00' in wtext, wtext[:160])
        check('[%s/%s] 跨零时段拆成两段且不裁切' % (scenario, tag), page.evaluate(
            """() => {
                 const s=[...document.querySelectorAll('#windowsBody .win-seg')];
                 if (s.length !== 4) return false;
                 const lefts = s.map(e => parseFloat(e.style.left));
                 const wrapStart = s.find(e => parseFloat(e.style.left) === 0 && parseFloat(e.style.width) > 0);
                 const wrapEnd = s.find(e => parseFloat(e.style.left) + parseFloat(e.style.width) >= 99.9);
                 return !!wrapStart && !!wrapEnd && Math.max(...lefts) + 0.0 <= 100;
               }"""))
        check('[%s/%s] 校准进度 3/7' % (scenario, tag), '3/7' in (page.text_content('#calibBody') or ''),
              (page.text_content('#calibBody') or '')[:120])
        check('[%s/%s] personalized 卡隐藏' % (scenario, tag), not page.is_visible('#personalizedCard'))
        check('[%s/%s] 观察等级卡隐藏（冷启动）' % (scenario, tag), not page.is_visible('#levelCard'))
        check('[%s/%s] 顶部连续记录 chip 可见' % (scenario, tag),
              page.is_visible('#streakChip'), page.text_content('#streakChip'))

        # 键盘可用：聚焦第二个标签后按 Enter 应能展开
        page.evaluate("() => document.querySelectorAll('#attentionBody .att-tag')[1].focus()")
        page.keyboard.press('Enter')
        page.wait_for_timeout(150)
        check('[%s/%s] 键盘 Enter 可展开标签' % (scenario, tag), page.is_visible('#attDetail'))

        # 复制分享文案
        page.click('#btnCopyShare')
        page.wait_for_timeout(250)
        check('[%s/%s] 复制按钮有反馈 toast' % (scenario, tag), page.is_visible('#toast'),
              page.text_content('#toast'))

    elif scenario == 'index_null':
        check('[%s/%s] 显示"指数生成中"' % (scenario, tag),
              page.is_visible('#indexPending') and '指数生成中' in page.text_content('#indexPending'))
        check('[%s/%s] 页面未白屏（其余区块仍在）' % (scenario, tag),
              page.is_visible('#attentionBody') and page.is_visible('#windowsBody')
              and len((page.text_content('#attentionBody') or '').strip()) > 0)
        check('[%s/%s] 校准 0/7' % (scenario, tag), '0/7' in (page.text_content('#calibBody') or ''),
              (page.text_content('#calibBody') or '')[:120])
        check('[%s/%s] personalized 卡隐藏' % (scenario, tag), not page.is_visible('#personalizedCard'))
        check('[%s/%s] basis 兜底标识仍显示' % (scenario, tag),
              '推算' in (page.text_content('#indexBasis') or ''))

    elif scenario == 'personalized':
        check('[%s/%s] 个体化卡可见' % (scenario, tag), page.is_visible('#personalizedCard'))
        check('[%s/%s] 等级=宜养' % (scenario, tag),
              '宜养' in (page.text_content('#personalizedChip') or ''),
              page.text_content('#personalizedChip'))
        check('[%s/%s] 关注通道含 心' % (scenario, tag),
              '心' in (page.text_content('#personalizedBody') or ''))
        check('[%s/%s] 指数卡不变（仍有 82 分）' % (scenario, tag),
              page.text_content('#indexScore').strip() == '82')
        check('[%s/%s] 观察等级卡可见=宜养' % (scenario, tag),
              page.is_visible('#levelCard') and '宜养' in (page.text_content('#levelBody') or ''))
        check('[%s/%s] 校准卡隐藏（基线已建立）' % (scenario, tag), not page.is_visible('#calibCard'))
        check('[%s/%s] 十二通道条形图有 12 行' % (scenario, tag),
              len(page.query_selector_all('#channelsBody .chan-row')) == 12,
              len(page.query_selector_all('#channelsBody .chan-row')))

    # 全页留档（仅 430 宽）
    if width == 430:
        page.screenshot(path=os.path.join(OUT, 'shot_%s_%s_full.png' % (tag, scenario)),
                        full_page=True, animations='disabled')

    print('  console error 数 = %d，未捕获异常数 = %d' % (len(console_errors), len(page_errors)))
    ctx.close()
    browser.close()
    return {'scenario': scenario, 'viewport': tag,
            'console_errors': console_errors, 'page_errors': page_errors}


def run_error_scenario(pw, width, height):
    """接口异常：daily 返回业务错误码 → 页面显示可读错误，不白屏"""
    tag = '%dx%d' % (width, height)
    print('\n=== 场景 api_error @ %s ===' % tag)
    stub = r"""
    (function () {
      window.fetch = function (url) {
        var u = String(url || '');
        function env(payload, status) {
          return new Response(JSON.stringify(payload),
            { status: status || 200, headers: { 'Content-Type': 'application/json' } });
        }
        if (u.indexOf('/auth/guest') >= 0) {
          return Promise.resolve(env({ code: 0, message: 'ok', data: { access_token: 't' }, trace_id: 'x' }));
        }
        if (u.indexOf('/profile/birth') >= 0) {
          return Promise.resolve(env({ code: 0, message: 'ok', data: {}, trace_id: 'x' }));
        }
        return Promise.resolve(env({ code: 50000, message: '服务暂时不可用，请稍后重试。',
                                     data: null, trace_id: 'stub-err-1' }));
      };
    })();
    """
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={'width': width, 'height': height})
    page = ctx.new_page()
    console_errors, page_errors = [], []
    page.on('console', lambda m: console_errors.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: page_errors.append(str(e)))
    page.add_init_script(stub)
    open_rhythm(page, 'api_error')
    page.wait_for_timeout(300)
    page.screenshot(path=os.path.join(OUT, 'shot_%s_api_error.png' % tag), animations='disabled')

    check('[api_error/%s] 显示可读错误条' % tag,
          page.is_visible('#alertBox') and len(page.text_content('#alertText') or '') > 0,
          page.text_content('#alertText'))
    check('[api_error/%s] 页面未白屏' % tag,
          page.is_visible('#indexBody') and '暂时无法读取' in (page.text_content('#indexBody') or ''))
    check('[api_error/%s] 免责声明仍在' % tag,
          '不属于医疗器械' in (page.text_content('#complianceCard') or ''))
    check('[api_error/%s] console 无 error' % tag, not console_errors, console_errors)
    check('[api_error/%s] 无未捕获异常' % tag, not page_errors, page_errors)
    ctx.close()
    browser.close()


def main():
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    with sync_playwright() as pw:
        runs = []
        for (w, h) in [(430, 932), (1440, 900)]:
            for sc in ['index', 'index_null', 'personalized']:
                runs.append(run_scenario(pw, sc, w, h))
        for (w, h) in [(430, 932), (1440, 900)]:
            run_error_scenario(pw, w, h)

    passed = sum(1 for r in RESULTS if r['ok'])
    total = len(RESULTS)
    print('\n' + '=' * 62)
    print('断言通过 %d / %d' % (passed, total))
    ce = sum(len(r['console_errors']) for r in runs)
    pe = sum(len(r['page_errors']) for r in runs)
    print('console error 总数 = %d，未捕获异常总数 = %d' % (ce, pe))
    print('耗时 %.1fs' % (time.time() - t0))
    with open(os.path.join(OUT, 'report.json'), 'w', encoding='utf-8') as f:
        json.dump({'assertions': RESULTS, 'passed': passed, 'total': total,
                   'console_errors': ce, 'page_errors': pe, 'runs': runs},
                  f, ensure_ascii=False, indent=2)
    print('截图与报告目录：%s' % OUT)
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())

