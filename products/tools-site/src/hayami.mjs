// 早見ページ（/born/<西暦>/ と /era/<元号>/<年>/）に載せる値を、lib.js の関数でまとめて計算する。
// 使い方: node src/hayami.mjs 2026 11 27  → JSON を標準出力に出す（build.py がビルド時に1回だけ呼ぶ）。
import { fileURLToPath } from "node:url";
import * as L from "./lib.js";

export const BORN_MIN = 1926;   // 生まれ年ページの最初の年（昭和元年のある年）
// いまの学校制度（小学校6年・中学校3年・高校3年・大学4年）が始まった年。これより前に小学校へ入学する年代には、
// 入学・卒業年の表を出さない（lib.js の schoolYears はいまの制度の年数で数えるだけで、当時の学校の区切りとは合わないため）。
export const SCHOOL_SYSTEM_FROM = 1947;
const md = ([m, d]) => `${m}月${d}日`;
const wareki = (y) => L.warekiOfYear(y).map((w) => ({ ...w, fromLabel: md(w.from), toLabel: md(w.to) }));
// 入学は4月、卒業は3月。和暦はその月の元号で出す。
const school = (list) => list.map((s) => ({
  name: s.name, enter: s.enter, enterWareki: L.toWareki(s.enter, 4, 1).label, grad: s.grad, gradWareki: L.toWareki(s.grad, 3, 31).label,
}));

export function hayamiData(today) {
  const ty = today[0];
  const born = [];
  for (let y = BORN_MIN; y <= ty; y++) {
    born.push({
      year: y, wareki: wareki(y), warekiLabel: L.warekiYearLabel(y), eto: L.eto(y), etoKana: L.etoKana(y),
      now: L.hayamiNow({ kind: "born", year: y }, today),
      ages: Array.from({ length: 101 }, (_, i) => ({ age: i, year: y + i, wareki: L.warekiYearLabel(y + i) })),
      schoolOk: L.schoolYears(y, 4, 1)[0].enter >= SCHOOL_SYSTEM_FROM,
      school: { normal: school(L.schoolYears(y, 4, 2)), early: school(L.schoolYears(y, 4, 1)) },
      milestones: L.milestones(y).map((m) => ({ ...m, warekiKazoe: L.warekiYearLabel(m.yearKazoe), warekiMan: L.warekiYearLabel(m.yearMan) })),
      etoYears: L.etoYears(y),
    });
  }
  const era = [];
  for (const { name } of [...L.ERAS].reverse()) {
    const [lo, hi] = L.eraYearRange(name);
    for (let n = lo; n <= hi && L.toSeireki(name, n) <= ty; n++) {
      const y = L.toSeireki(name, n);
      const all = wareki(y), me = all.find((w) => w.era === name);
      era.push({
        era: name, slug: L.ERA_SLUGS[name], n, label: me.label, year: y, from: me.fromLabel, to: me.toLabel,
        other: all.find((w) => w.era !== name) ?? null,   // 同じ西暦年のもう一方の元号（改元のあった年だけ）
        eto: L.eto(y), etoKana: L.etoKana(y), now: L.hayamiNow({ kind: "era", era: name, n }, today),
        steps: Array.from({ length: 10 }, (_, i) => ({ after: (i + 1) * 10, year: y + (i + 1) * 10, wareki: L.warekiYearLabel(y + (i + 1) * 10) })),
      });
    }
  }
  return { today, bornMin: BORN_MIN, longevity: L.LONGEVITY, born, era };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const today = process.argv.slice(2, 5).map(Number);
  if (today.length !== 3 || !L.validDate(...today)) {
    console.error("使い方: node src/hayami.mjs <年> <月> <日>");
    process.exit(1);
  }
  process.stdout.write(JSON.stringify(hayamiData(today)));
}
