/* 前端静态自检（Node，不改任何源码）：
   ① 语法检查由 `node --check app.js` 单独做；
   ② 本脚本核对 index.html 的 id 是否重复、app.js 里 $('xxx') 引用的 id 是否都存在于 HTML、
      以及 index.html 里 data 属性/新增 id 是否与 app.js 对得上。
   用法：node D:\...\_verify_v11\_check_dom.js  */
const fs = require('fs');
const path = require('path');
const WEB = 'D:\\Deepseek智能体\\AI元健康\\shuzi\\web';
const html = fs.readFileSync(path.join(WEB, 'index.html'), 'utf8');
const js = fs.readFileSync(path.join(WEB, 'app.js'), 'utf8');
const css = fs.readFileSync(path.join(WEB, 'style.css'), 'utf8');

const htmlIds = (html.match(/\bid="[A-Za-z0-9_-]+"/g) || []).map(s => s.slice(4, -1));
const dup = htmlIds.filter((v, i) => htmlIds.indexOf(v) !== i);
console.log('index.html id 总数 = ' + htmlIds.length + '，重复 id = ' + (dup.length ? dup.join(',') : '无'));

const refs = [...new Set((js.match(/\$\('([A-Za-z0-9_-]+)'\)/g) || []).map(s => s.slice(3, -2)))];
const missing = refs.filter(id => htmlIds.indexOf(id) < 0);
console.log('app.js 通过 $() 引用的 id 数 = ' + refs.length + '，HTML 中缺失 = ' + (missing.length ? missing.join(',') : '无'));

// 新增样式类是否都在 CSS 里定义（只管本屏新增的 fam-* 前缀，避免误报既有类）
const famClasses = [...new Set((html.match(/class="[^"]*"/g) || []).join(' ').match(/\bfam-[a-z-]+/g) || [])];
const undef = famClasses.filter(c => css.indexOf('.' + c) < 0);
console.log('index.html 用到 fam-* 类 = ' + famClasses.length + '，CSS 未定义 = ' + (undef.length ? undef.join(',') : '无'));

// 页面里不得出现观察等级字样 L0–L4（家庭档案页只显示「基线建立中 n/7」）
const lv = (html + js).match(/\bL[0-4]\b/g) || [];
const lvInFamily = (html + js).split(/\n/).filter(l => /L[0-4]/.test(l) && /fam|family|家庭/.test(l));
console.log('新增前端文件里 L0–L4 字样 = ' + lv.length + ' 处（其中与家庭档案同行的 = ' + lvInFamily.length + ' 处）');
process.exit(dup.length || missing.length || undef.length ? 2 : 0);
