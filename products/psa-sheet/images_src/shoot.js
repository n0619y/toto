#!/usr/bin/env node
// 商品画像 5枚を dist/images/ に書き出す。
//   node products/psa-sheet/images_src/shoot.js
// 必要なもの: playwright(chromium)。1200×900 の画面を deviceScaleFactor 2 で撮るので、
// PNG の実ピクセルは 2400×1800(表示上のサイズは 1200×900)。
const path = require('path');
const fs = require('fs');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');

const SRC = __dirname;
const OUT = path.join(SRC, '..', 'dist', 'images');
const PAGES = ['01-cover', '02-ledger', '03-monthly', '04-simulator', '05-howto'];
const W = 1200, H = 900;

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
  let warnings = 0;
  for (const name of PAGES) {
    const page = await ctx.newPage();
    await page.goto(pathToFileURL(path.join(SRC, name + '.html')).href);
    await page.evaluate(() => document.fonts.ready);
    // はみ出しの簡易チェック: 画面外に出た要素、中身が切れているセル、フッターに重なる要素
    const problems = await page.evaluate(({ W, H }) => {
      const out = [];
      const footer = document.querySelector('.footer');
      const fTop = footer ? footer.getBoundingClientRect().top : H;
      for (const el of document.querySelectorAll('body *')) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        const label = el.tagName.toLowerCase() + ':' + (el.textContent || '').trim().slice(0, 16);
        if (r.right > W + 0.5 || r.bottom > H + 0.5 || r.left < -0.5 || r.top < -0.5) out.push('画面外 ' + label);
        if ((el.tagName === 'TD' || el.tagName === 'TH' || el.classList.contains('footer')) &&
            (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1)) out.push('中身が切れている ' + label);
        if (footer && !footer.contains(el) && el !== footer && !el.contains(footer) && r.bottom > fTop + 0.5) out.push('フッターに重なる ' + label);
      }
      return out;
    }, { W, H });
    const file = path.join(OUT, name + '.png');
    await page.screenshot({ path: file, clip: { x: 0, y: 0, width: W, height: H } });
    console.log(`wrote ${path.relative(process.cwd(), file)}` + (problems.length ? `  [要確認 ${problems.length}件]` : ''));
    for (const p of problems) console.log('   - ' + p);
    warnings += problems.length;
    await page.close();
  }
  await browser.close();
  if (warnings) process.exitCode = 1;
})();
