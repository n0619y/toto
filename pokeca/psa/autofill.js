// PSA の「Enter Items」画面でカードを順番に入力するブックマークレット本体。
//
// やること: リストの各行について 検索欄に入力 → 候補が1件に絞れたら選択 → 枚数を入れる → Save。
// やらないこと: Proceed to Checkout / Review Order / Place Order / 規約のチェックは押さない。
// 候補が0件または複数件のカードは選ばずに飛ばし、最後にまとめて知らせる（誤ったカードを入れないため）。
//
// リストの書き方: 「M3 061 x1; M3 045 x2」のように ; か改行で区切る。x枚数 は省略すると1。
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
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === text && !b.disabled);
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

  if (!searchBox()) {
    alert("PSA の「Enter Items」画面で実行してください（検索欄が見つかりません）。");
    return;
  }
  const raw = prompt("PSA入力リストを貼り付けてください\n例: M3 061 x1; M3 045 x2");
  if (!raw) return;
  const items = raw.split(/[;\n]+/).map((s) => s.trim()).filter(Boolean).map((s) => {
    const m = s.match(/^(.*?)(?:\s*[x×]\s*(\d+))?$/i);
    return { query: m[1].trim(), qty: Number(m[2] || 1) };
  });

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
