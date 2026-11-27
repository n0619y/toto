// PSA の申込画面でカードを順番に入力するブックマークレット本体。
//
// 始める場所: 「Select Item Type」の画面（Classic Submission を選んだ直後）か、それ以降の画面。
// やること: Trading Cards → Grading → 鑑定プランの選択（選択肢を出して選んでもらう）→
//           各カードを 検索 → 候補が1件に絞れたら選択 → 枚数 → Save。
// やらないこと: Proceed to Checkout / Review Order / Place Order / 規約のチェックは押さない。
// 候補が0件または複数件のカードは選ばずに飛ばし、最後にまとめて知らせる（誤ったカードを入れないため）。
//
// リストの書き方: 「plan=Priority; M3 061 x1; M3 045 x2」。; か改行で区切る。
// plan= を省くとプランの選択肢を表示する。x枚数 は省略すると1。
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const until = async (fn, ms = 8000) => {
    for (const end = Date.now() + ms; Date.now() < end; await sleep(150)) {
      const v = fn();
      if (v) return v;
    }
    return null;
  };
  const setValue = (el, v) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(el, v);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  };
  const searchBox = () =>
    [...document.querySelectorAll("input")].find((i) => /search collectibles/i.test(i.placeholder || ""));
  const qtyBox = () => {
    const label = [...document.querySelectorAll("label, div, span")].find(
      (e) => e.children.length === 0 && /^quantity$/i.test(e.textContent.trim()));
    if (!label) return null;
    if (label.control) return label.control;
    for (let p = label.parentElement, i = 0; p && i < 4; p = p.parentElement, i++) {
      const input = p.querySelector("input");
      if (input) return input;
    }
    return null;
  };
  const button = (text) =>
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === text && !b.disabled && b.offsetParent !== null);
  const itemCount = () => {
    const m = document.body.innerText.match(/Items\s*\((\d+)\)/i);
    return m ? Number(m[1]) : 0;
  };
  // 候補の行: 「2026 Pokemon Japanese ... TCG Cards」を含む、いちばん内側の要素
  const candidates = () => {
    const all = [...document.querySelectorAll("li, [role=option], a, button, div")].filter(
      (e) => /pokemon/i.test(e.textContent) && /TCG Cards/i.test(e.textContent) && e.offsetParent !== null);
    return all.filter((e) => !all.some((o) => o !== e && e.contains(o)));
  };
  const matches = (el, tokens) => {
    const text = el.textContent.toLowerCase();
    return tokens.every((t) => new RegExp("(^|[^a-z0-9])" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "([^a-z0-9]|$)").test(text));
  };

  const screenIs = (title) => [...document.querySelectorAll("h1, h2, h3, div, p")].some(
    (e) => e.children.length === 0 && e.textContent.trim() === title && e.offsetParent !== null);
  const leaf = (text) => [...document.querySelectorAll("label, span, div, p, td, button")].find(
    (e) => e.children.length === 0 && e.textContent.trim() === text && e.offsetParent !== null);
  const next = async (fromTitle) => {
    const b = await until(() => button("Select & Continue"));
    if (!b) return false;
    b.click();
    return !!(await until(() => !screenIs(fromTitle)));
  };
  const PLAN_RE = /^(Value|Standard|Priority|Express|Super Express|Premier|Premium \d+)( \(.*\))?$/;
  const planNames = () => [...new Set([...document.querySelectorAll("label, span, div, p, td")]
    .filter((e) => e.children.length === 0 && e.offsetParent !== null && PLAN_RE.test(e.textContent.trim()))
    .map((e) => e.textContent.trim()))];

  const onFlow = () => ["Select Item Type", "Select Submission Type", "Select Service Level"].some(screenIs) || searchBox();
  if (!onFlow()) {
    alert("PSA の申込画面（Select Item Type 〜 Enter Items）で実行してください。");
    return;
  }
  const raw = prompt("PSA入力リストを貼り付けてください\n例: plan=Priority; M3 061 x1; M3 045 x2");
  if (!raw) return;
  let plan = "";
  const items = [];
  for (const part of raw.split(/[;\n]+/).map((s) => s.trim()).filter(Boolean)) {
    const pm = part.match(/^plan\s*=\s*(.+)$/i);
    if (pm) { plan = pm[1].trim(); continue; }
    const m = part.match(/^(.*?)(?:\s*[x×]\s*(\d+))?$/i);
    items.push({ query: m[1].trim(), qty: Number(m[2] || 1) });
  }

  // --- カード入力の前の3画面を進める ---
  if (screenIs("Select Item Type")) {
    (leaf("Trading Cards") || {click() {}}).click();
    if (!(await next("Select Item Type"))) { alert("Item Type の画面から進めませんでした。手で進めてからもう一度実行してください。"); return; }
  }
  if (screenIs("Select Submission Type")) {
    (leaf("Grading") || {click() {}}).click();
    if (!(await next("Select Submission Type"))) { alert("Submission Type の画面から進めませんでした。手で進めてからもう一度実行してください。"); return; }
  }
  if (screenIs("Select Service Level")) {
    const names = await until(() => { const n = planNames(); return n.length ? n : null; });
    if (!names) { alert("鑑定プランの一覧を読み取れませんでした。手で選んでからもう一度実行してください。"); return; }
    let chosen = names.find((n) => n.toLowerCase() === plan.toLowerCase());
    if (!chosen) {
      const answer = prompt((plan ? `「${plan}」というプランが見つかりません。\n` : "") + "鑑定プランを番号で選んでください\n" +
        names.map((n, i) => `${i + 1}. ${n}`).join("\n"));
      chosen = names[Number(answer) - 1];
      if (!chosen) return;                              // キャンセルや範囲外なら何もしない
    }
    leaf(chosen).click();
    await sleep(300);
    if (!(await next("Select Service Level"))) { alert("Service Level の画面から進めませんでした。手で進めてからもう一度実行してください。"); return; }
  }
  if (!(await until(searchBox))) {
    alert("「Enter Items」画面の検索欄が見つかりません。");
    return;
  }
  if (!items.length) { alert("プランを選びました。カードのリストが空なので、ここで終わります。"); return; }

  const added = [], skipped = [];
  for (const item of items) {
    const box = await until(searchBox);
    if (!box) { skipped.push(item.query + "（検索欄が出ない）"); break; }
    const tokens = item.query.toLowerCase().split(/\s+/);
    box.focus();
    setValue(box, "pokemon japanese " + item.query);
    const hits = await until(() => {
      const c = candidates().filter((e) => matches(e, tokens));
      return c.length ? c : null;
    });
    await sleep(600);                                   // 候補の表示が落ち着くのを待つ
    const final = candidates().filter((e) => matches(e, tokens));
    if (!hits || final.length !== 1) {
      skipped.push(item.query + (final.length ? `（候補が${final.length}件）` : "（候補なし）"));
      setValue(searchBox() || box, "");
      continue;
    }
    const before = itemCount();
    final[0].click();
    const qty = await until(qtyBox);
    if (qty && item.qty !== 1) setValue(qty, String(item.qty));
    const save = await until(() => button("Save"));
    if (!save) { skipped.push(item.query + "（Save が押せない）"); continue; }
    save.click();
    if (await until(() => itemCount() > before)) added.push(`${item.query} ×${item.qty}`);
    else skipped.push(item.query + "（追加を確認できず）");
    await sleep(400);
  }
  alert(`追加 ${added.length}件 / 飛ばした ${skipped.length}件` +
        (skipped.length ? "\n\n手で入力が必要:\n" + skipped.join("\n") : "") +
        "\n\n内容を確認してから Proceed to Checkout に進んでください。");
})();
