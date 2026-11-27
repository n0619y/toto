#!/usr/bin/env python3
"""配布用 zip (dist/psa-shushi-kanri-v1.0.zip) を作る。

    python3 products/psa-sheet/make_zip.py

中身(3ファイル、フォルダなし):
  - psa-shushi-kanri.xlsx          … build.py が作ったものをそのまま入れる(先に build.py / verify.py を実行)
  - よくある質問_FAQ.txt            … FAQ.md から Markdown の記号を落としたテキスト
  - はじめにお読みください.txt      … 下の README_TXT

テキストは Windows のメモ帳でも読めるよう UTF-8(BOM 付き)・CRLF にする。
日本語ファイル名は zip の UTF-8 フラグ付きで入る(Python の zipfile が自動で付ける)。
zip 内の時刻は固定なので、何度実行しても同じバイト列になる。
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build as B  # noqa: E402  (バージョン表記と xlsx のパスを借りる)

RELEASE_DATE = (2026, 11, 27)
XLSX = B.OUT
FAQ_MD = HERE / "FAQ.md"
OUT = HERE / "dist" / f"psa-shushi-kanri-{B.RELEASE}.zip"
FAQ_NAME = "よくある質問_FAQ.txt"
README_NAME = "はじめにお読みください.txt"

README_TXT = f"""PSA鑑定 収支管理シート {B.RELEASE}({RELEASE_DATE[0]}-{RELEASE_DATE[1]:02d}-{RELEASE_DATE[2]:02d})
はじめにお読みください

■ 入っているもの
  ・{XLSX.name}  … 収支管理シート本体(シート6枚)
  ・{FAQ_NAME}  … よくある質問
  ・{README_NAME}  … このファイル

■ はじめかた
  Excel の場合
    {XLSX.name} を開き、画面上部に「保護ビュー」の黄色い帯が出たら
    「編集を有効にする」を押してください。押すまで数字は表示されません。
  Googleスプレッドシートの場合
    Googleスプレッドシートで空のファイルを開き、
    「ファイル」→「インポート」→「アップロード」で {XLSX.name} を選び、
    「新しいスプレッドシートを作成する」で取り込んでください。

  開いたら、最初に「使い方」シートを読んでください。
  1. 「設定」シートの黄色いセルを、ご自身の実際の金額に書き換える(初期値は一例です)
  2. 「在庫台帳」のサンプル5行を消し(黄色いセルだけ Delete)、カード1枚を1行で記録する
  3. 「注文別集計」「月次集計」で収支を見る。仕入れ前は「シミュレーター」で試算する
  黄色いセルが入力欄、灰色のセルは数式(触らない)です。

■ この zip は消さずに取っておいてください
  数式を消してしまったときは、この zip に入っている元のファイルを開き直すのが
  いちばん確実です。

■ ご注意
  ・個別のサポート(使い方の質問、カスタマイズ、不具合の個別対応)は行っていません。
    困ったときは「{FAQ_NAME}」と「使い方」シートをご覧ください。
  ・返金・キャンセルは、購入した販売サイトの規定に従います。
  ・このファイルは収支の記録と試算のための道具です。利益が出ることや、計算結果が
    実際の費用・税額と一致することを保証するものではありません。
  ・税務と、関税・輸入時の税の扱いは、各自で税理士・税務署・税関などに確認してください。
  ・サンプルデータ(カード名・店名・金額・番号)はすべて架空です。
  ・購入者ご本人の利用に限ります。再配布・転売はご遠慮ください。
  ・本ファイルは PSA(Professional Sports Authenticator)社とは関係のない非公式のツールです。
"""


def md_to_text(md: str) -> str:
    """FAQ.md を、Markdown を知らない人が読めるテキストにする(見出し記号・強調・バッククォートを落とすだけ)。"""
    out = []
    for line in md.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            level, title = len(m.group(1)), m.group(2)
            if level == 1:
                out += [title, "=" * 40]
            elif level == 2:
                out += ["", "━━ " + title + " ━━"]
            else:
                out += ["■ " + title]
            continue
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line).replace("`", "")
        line = re.sub(r"^- ", "・", line)
        out.append(line)
    return "\n".join(out).strip() + "\n"


def as_windows_text(s: str) -> bytes:
    return b"\xef\xbb\xbf" + s.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")


def main() -> int:
    for p in (XLSX, FAQ_MD):
        if not p.exists():
            print(f"{p} がありません。")
            return 2
    faq = FAQ_MD.read_text(encoding="utf-8")
    if B.RELEASE not in faq:
        print(f"FAQ.md にバージョン表記 {B.RELEASE} がありません。")
        return 2
    files = [
        (XLSX.name, XLSX.read_bytes()),
        (FAQ_NAME, as_windows_text(md_to_text(faq))),
        (README_NAME, as_windows_text(README_TXT)),
    ]
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            info = zipfile.ZipInfo(name, date_time=(*RELEASE_DATE, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
    with zipfile.ZipFile(OUT) as z:
        bad = z.testzip()
        for i in z.infolist():
            utf8 = "UTF-8名" if i.flag_bits & 0x800 else "ASCII名"
            print(f"  {i.filename}  {i.file_size:,} bytes  [{utf8}]")
        if bad:
            print(f"壊れたファイル: {bad}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
