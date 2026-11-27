"""使い方:
  python -m shorts check 台本.json                    長さ・文字量・必須項目の検査だけ（動画は作らない）
  python -m shorts make  台本.json --out output/shorts/  縦動画(MP4)・サムネイル(PNG)・投稿用テキスト(TXT)を作る

台本は JSON か YAML。書き方は README の「Shorts の縦動画を作る」と shorts/sample/ を参照。
自動投稿はしない。できた動画は監修者が確認してから、手でアップロードする。
"""

from __future__ import annotations

import argparse
import sys

from .render import RenderError, make
from .script import ScriptError, load_script, summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m shorts", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="台本の検査だけ")
    p.add_argument("script")
    p = sub.add_parser("make", help="動画を作る")
    p.add_argument("script")
    p.add_argument("--out", default="output/shorts/", help="出力先（既定: output/shorts/）")
    p.add_argument("--date", help="ファイル名の日付 YYYYMMDD（既定: 今日）")
    p.add_argument("--workers", type=int, help="同時に撮るページ数（既定: CPU 数、最大 4）")
    p.add_argument("--keep-frames", metavar="DIR", help="撮った PNG と HTML をこの場所に残す（確認用）")
    args = ap.parse_args(argv)

    try:
        script = load_script(args.script)
        print(summary(script))
        if args.cmd == "check":
            print("OK: 台本に問題はありません。")
            return 0
        r = make(script, args.out, date=args.date, workers=args.workers, keep_frames=args.keep_frames)
    except (ScriptError, RenderError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    print(f"動画: {r['mp4']}（{r['seconds']:.1f}秒、{r['bytes'] / 1_000_000:.2f} MB）")
    print(f"サムネイル: {r['png']}")
    print(f"投稿用テキスト: {r['txt']}")
    print(f"所要時間: {r['elapsed']:.1f}秒（{r['frames']}フレーム中 {r['captured']}枚を撮影）")
    print("次の手順: 監修者が動画を確認 → スマホの YouTube アプリからアップロード（自動投稿はしません）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
