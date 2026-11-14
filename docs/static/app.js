// 小さな折れ線グラフ（ホバーで値表示）。外部ライブラリ不要。
function lineChart(el, points, opts = {}) {
  if (!points || points.length < 2) { el.innerHTML = '<p class="empty">データが2日分以上たまると表示されます</p>'; return; }
  const W = Math.max(300, Math.min(800, el.clientWidth || 640)), H = opts.height || 200, P = { l: 56, r: 12, t: 12, b: 24 };
  const ys = points.map(p => p[1]);
  let min = Math.min(...ys), max = Math.max(...ys);
  if (opts.baseline != null) { min = Math.min(min, opts.baseline); max = Math.max(max, opts.baseline); }
  const pad = (max - min) * 0.1 || max * 0.05 || 1; min -= pad; max += pad;
  const x = i => P.l + (W - P.l - P.r) * i / (points.length - 1);
  const y = v => P.t + (H - P.t - P.b) * (1 - (v - min) / (max - min));
  const fmt = opts.fmt || (v => v.toLocaleString());
  const step0 = (max - min) / 3, mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(v => v >= step0);
  const ticks = []; for (let t = Math.ceil(min / step) * step; t <= max; t += step) ticks.push(t);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${opts.label || ''}">`;
  ticks.forEach(t => s += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/>` +
    `<text x="${P.l - 6}" y="${y(t) + 4}" text-anchor="end" font-size="11" fill="var(--muted)">${fmt(+t.toFixed(4))}</text>`);
  if (opts.baseline != null) s += `<line x1="${P.l}" x2="${W - P.r}" y1="${y(opts.baseline)}" y2="${y(opts.baseline)}" stroke="var(--axis)" stroke-dasharray="3 3"/>`;
  [0, Math.floor((points.length - 1) / 2), points.length - 1].forEach(i =>
    s += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle" font-size="11" fill="var(--muted)">${points[i][0].slice(5)}</text>`);
  s += `<path d="${points.map((p, i) => (i ? 'L' : 'M') + x(i) + ' ' + y(p[1])).join(' ')}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round"/>`;
  const last = points[points.length - 1];
  s += `<circle cx="${x(points.length - 1)}" cy="${y(last[1])}" r="4" fill="var(--accent)" stroke="var(--surface)" stroke-width="2"/>`;
  s += `<line class="xh" y1="${P.t}" y2="${H - P.b}" stroke="var(--axis)" visibility="hidden"/><circle class="hd" r="4" fill="var(--accent)" stroke="var(--surface)" stroke-width="2" visibility="hidden"/>`;
  s += `<rect x="${P.l}" y="0" width="${W - P.l - P.r}" height="${H}" fill="transparent"/></svg><div class="tip"></div>`;
  el.innerHTML = s;
  const svg = el.querySelector('svg'), tip = el.querySelector('.tip'), xh = el.querySelector('.xh'), hd = el.querySelector('.hd');
  const move = e => {
    const r = svg.getBoundingClientRect(), px = (e.clientX - r.left) * W / r.width;
    const i = Math.max(0, Math.min(points.length - 1, Math.round((px - P.l) / (W - P.l - P.r) * (points.length - 1))));
    const cx = x(i), cy = y(points[i][1]);
    xh.setAttribute('x1', cx); xh.setAttribute('x2', cx); xh.setAttribute('visibility', 'visible');
    hd.setAttribute('cx', cx); hd.setAttribute('cy', cy); hd.setAttribute('visibility', 'visible');
    tip.style.display = 'block'; tip.innerHTML = `<b>${fmt(points[i][1])}</b> ${points[i][0]}`;
    const left = cx * r.width / W; tip.style.left = Math.min(left + 10, r.width - tip.offsetWidth) + 'px'; tip.style.top = (cy * r.height / H - 36) + 'px';
  };
  svg.addEventListener('pointermove', move);
  svg.addEventListener('pointerleave', () => { tip.style.display = 'none'; xh.setAttribute('visibility', 'hidden'); hd.setAttribute('visibility', 'hidden'); });
}

// ランキングの絞り込み（地域・媒体・カテゴリ）
function setupFilters() {
  const list = document.querySelectorAll('[data-topic]');
  if (!list.length) return;
  const state = {};
  document.querySelectorAll('.filters').forEach(group => {
    const key = group.dataset.key; state[key] = 'all';
    group.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return;
      group.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
      state[key] = b.dataset.v;
      list.forEach(el => {
        const ok = Object.entries(state).every(([k, v]) => v === 'all' || (el.dataset[k] || '').split(' ').includes(v));
        el.style.display = ok ? '' : 'none';
      });
    });
  });
}
document.addEventListener('DOMContentLoaded', setupFilters);
