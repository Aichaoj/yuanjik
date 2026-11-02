/* shuzi.yuanjk.cn entry button - injected on the yuanjk H5 top-level screens (home + login).
   Added 2026-10-08. Rollback: delete this file and the <script> tag in index.html. */
(function () {
  var HOST = 'https://shuzi.yuanjk.cn';
  var TEXT = 'AI\u5065\u5eb7';
  function isEntryPage() {
    var p = location.pathname || '/';
    if (p === '/' || p === '' || p === '/index.html') return true;
    if (p.indexOf('/pages/index/index') >= 0) return true;
    if (p.indexOf('/pages/user_login/login/index') >= 0) return true;
    return false;
  }
  function mount() {
    var el = document.getElementById('shuzi-entry-btn');
    if (!isEntryPage()) { if (el) el.style.display = 'none'; return; }
    if (el) { el.style.display = 'flex'; return; }
    if (!document.body) return;
    var a = document.createElement('a');
    a.id = 'shuzi-entry-btn';
    a.href = HOST;
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = TEXT;
    a.style.cssText = 'position:fixed;right:12px;top:70px;z-index:99999;display:flex;' +
      'align-items:center;gap:6px;padding:9px 15px;border-radius:999px;' +
      'background:linear-gradient(135deg,#D6234A 0%,#FF7A9A 100%);color:#fff;' +
      'font-size:14px;font-weight:600;line-height:1;text-decoration:none;' +
      'box-shadow:0 6px 16px rgba(214,35,74,.35);';
    document.body.appendChild(a);
  }
  if (document.readyState === 'complete' || document.readyState === 'interactive') { mount(); }
  else { window.addEventListener('DOMContentLoaded', mount); }
  window.addEventListener('load', mount);
  setInterval(mount, 1500);
})();