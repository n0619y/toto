// フレームを連番 PNG として撮る。使い方: node capture.js plan.json
//
// 実時間では録画しない。ページ内の CSS アニメーションはすべて一時停止してあり、
// 各フレームで「時刻 t の状態」に合わせてから 1 枚ずつ撮る。同じ入力なら同じ画像になる。
// plan.json: { html, width, height, workers, frames: [{file, ms}] }
const fs = require('fs');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');

async function main() {
  const plan = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const browser = await chromium.launch();
  const result = { overflow: [], fonts: [], captured: 0 };
  try {
    const context = await browser.newContext({
      viewport: { width: plan.width, height: plan.height },
      deviceScaleFactor: 1,
    });
    const open = async () => {
      const page = await context.newPage();
      await page.goto(pathToFileURL(plan.html).href);
      await page.evaluate(() => document.fonts.ready);
      await page.evaluate(() => window.__init());
      return page;
    };
    const first = await open();
    const report = await first.evaluate(() => window.__inspect());
    result.overflow = report.overflow;
    result.fonts = report.fonts;
    if (result.overflow.length === 0 && result.fonts.length === 0) {
      const workers = Math.max(1, Math.min(plan.workers || 1, plan.frames.length));
      const pages = [first];
      while (pages.length < workers) pages.push(await open());
      let next = 0;
      await Promise.all(pages.map(async (page) => {
        for (;;) {
          const job = plan.frames[next++];
          if (!job) return;
          await page.evaluate((ms) => window.__setTime(ms), job.ms);
          await page.screenshot({ path: job.file, type: 'png' });
          result.captured++;
        }
      }));
    }
  } finally {
    await browser.close();
  }
  process.stdout.write(JSON.stringify(result));
}

main().catch((e) => { console.error(e && e.stack || String(e)); process.exit(1); });
