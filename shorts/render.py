"""台本（Script）から縦動画（MP4）・サムネイル（PNG）・投稿用テキスト（TXT）を作る。

流れ: HTML/CSS を組む → Playwright（node）でフレームを PNG に撮る → ffmpeg で MP4 にする。

- 時間は実時間で進めない。CSS アニメーションを一時停止し、各フレームの時刻の状態に合わせて撮る。
- 動きのない区間は、同じ PNG を使い回す（撮る枚数が数分の一になる）。
  進行バーだけは毎フレーム変わるので、HTML には土台だけを描き、伸びる部分は ffmpeg で重ねる。
"""

from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import script as S
from .script import FPS, HEIGHT, WIDTH, Script, ScriptError

HERE = Path(__file__).resolve().parent
CAPTURE_JS = HERE / "capture.js"
FONT_FAMILY = "IPAGothic"
INK = "#17324A"  # 文字の色（濃紺）。背景との明暗差を確保するため固定
BAR_HEIGHT = 16

# 動きの長さ（フレーム数）
SCENE_IN = 9
CARD_IN = 12
CARD_OUT = 6
LINE_IN = 12
LINE_FIRST = 10


class RenderError(RuntimeError):
    pass


# ---- 色 ---------------------------------------------------------------------
def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix(a: str, b: str, ratio: float) -> str:
    """a に b を ratio だけ混ぜた色。"""
    ca, cb = _rgb(a), _rgb(b)
    return "#" + "".join(f"{round(x + (y - x) * ratio):02X}" for x, y in zip(ca, cb))


# ---- 時間の割り付け ---------------------------------------------------------
def timeline(script: Script) -> list[dict]:
    """各シーンの開始フレームと、行が現れるフレームを決める。"""
    out, start = [], 0
    last = len(script.scenes) - 1
    for i, sc in enumerate(script.scenes):
        n = len(sc.lines)
        stagger = min(18, max(4, int((sc.frames * 0.45 - LINE_IN) // max(n, 1))))
        latest = max(0, sc.frames - CARD_OUT - LINE_IN)
        first = 6 if i == 0 else LINE_FIRST
        out.append({
            "start": start,
            "frames": sc.frames,
            "fade_in": i > 0,
            "fade_out": i < last,
            "lines": [start + min(first + j * stagger, latest) for j in range(n)],
        })
        start += sc.frames
    return out


def animations(tl: list[dict]) -> list[tuple[int, int]]:
    """すべての動きを (開始フレーム, 長さ) で並べる。"""
    anims = []
    for sc in tl:
        if sc["fade_in"]:
            anims += [(sc["start"], SCENE_IN), (sc["start"], CARD_IN)]
        if sc["fade_out"]:
            anims.append((sc["start"] + sc["frames"] - CARD_OUT, CARD_OUT))
        anims += [(f, LINE_IN) for f in sc["lines"]]
    return anims


def frame_plan(tl: list[dict], total: int) -> list[int]:
    """各フレームが「どの撮影済みフレームと同じ絵か」を返す（同じ絵なら撮り直さない）。

    フレーム f は時刻 f+0.5（フレームの中央）で撮る。動きはフレームの境目で始まり・終わるので、
    境目ちょうどの時刻を撮ることがなく、ここでの計算とブラウザの状態が食い違わない。
    """
    anims = animations(tl)
    seen: dict[tuple, int] = {}
    plan = []
    for f in range(total):
        t = f + 0.5
        key = tuple(min(1.0, max(0.0, (t - s) / d)) for s, d in anims)
        plan.append(seen.setdefault(key, f))
    return plan


# ---- HTML -------------------------------------------------------------------
def _ms(frames: float) -> str:
    return f"{frames * 1000 / FPS:.4f}ms"


def _anim(name: str, start: int, dur: int) -> str:
    return f"{name} {_ms(dur)} cubic-bezier(.2,.7,.2,1) {_ms(start)} both paused"


def build_html(script: Script, tl: list[dict]) -> str:
    d = script.design
    primary, secondary, accent = d["primary_color"], d["secondary_color"], d["accent_color"]
    e = html.escape
    total = len(script.scenes)
    sections = []
    for sc, t in zip(script.scenes, tl):
        scene_style = f' style="animation:{_anim("fade", t["start"], SCENE_IN)}"' if t["fade_in"] else ""
        card_anims = []
        if t["fade_in"]:
            card_anims.append(_anim("rise", t["start"], CARD_IN))
        if t["fade_out"]:
            card_anims.append(_anim("out", t["start"] + t["frames"] - CARD_OUT, CARD_OUT))
        card_style = f' style="animation:{",".join(card_anims)}"' if card_anims else ""
        head_rows = "".join(f'<div class="row">{e(r)}</div>' for r in sc.head_rows)
        mark = '<div class="mark">！</div>' if sc.kind == "warning" else ""
        lines = ""
        for rows, f in zip(sc.body_rows, t["lines"]):
            inner = "".join(f'<div class="row">{e(r)}</div>' for r in rows)
            lines += f'<div class="line" style="animation:{_anim("line", f, LINE_IN)}">{inner}</div>'
        body = f'<div class="body" style="font-size:{sc.body_size}px">{lines}</div>' if lines else ""
        sections.append(
            f'<section class="scene k-{sc.kind}" data-scene="{sc.index}"{scene_style}>'
            f'<div class="num">{sc.index} / {total}</div>'
            f'<div class="zone"><div class="card"{card_style}>'
            f'<div class="head" style="font-size:{sc.head_size}px">{mark}<div class="htext">{head_rows}</div></div>'
            f"{body}</div></div></section>"
        )
    css = f"""
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{width:{WIDTH}px;height:{HEIGHT}px;overflow:hidden;background:{secondary}}}
body{{font-family:"{FONT_FAMILY}",monospace;color:{INK};font-kerning:none;font-feature-settings:"palt" 0}}
.scene{{position:absolute;inset:0;background:{secondary}}}
.zone{{position:absolute;left:40px;top:222px;width:1000px;height:{S.CARD_MAX_HEIGHT + 16}px;
  display:flex;align-items:center}}
.card{{width:1000px;background:#fff;border:8px solid #fff;border-radius:44px;overflow:hidden;
  box-shadow:0 18px 50px rgba(23,50,74,.16)}}
.head{{display:flex;align-items:center;gap:30px;padding:{S.HEAD_PAD_Y}px 42px;background:{primary};
  font-weight:bold;line-height:{S.HEAD_LINE_HEIGHT}}}
.htext{{flex:1;min-width:0}}
.mark{{flex:none;width:80px;height:80px;border-radius:50%;background:{INK};color:#fff;
  font-size:56px;line-height:80px;text-align:center}}
.body{{padding:{S.BODY_PAD_Y}px 42px;line-height:{S.BODY_LINE_HEIGHT}}}
.line{{border-left:12px solid {accent};padding-left:28px}}
.line + .line{{margin-top:{S.BODY_GAP_EM}em}}
.row{{white-space:nowrap;overflow:hidden}}
.num{{position:absolute;right:40px;top:80px;height:76px;line-height:76px;padding:0 30px;border-radius:38px;
  background:{INK};color:#fff;font-size:38px;font-weight:bold}}
.sup{{position:absolute;left:40px;top:80px;height:76px;line-height:76px;padding:0 28px;border-radius:38px;
  background:#fff;white-space:nowrap;overflow:hidden;max-width:{S.SUPERVISOR_WIDTH + 56}px;
  box-shadow:0 6px 18px rgba(23,50,74,.14)}}
.track{{position:absolute;left:0;top:0;width:100%;height:{BAR_HEIGHT}px;background:{mix(INK, "#FFFFFF", 0.78)}}}
.k-hook{{background:{mix(primary, "#FFFFFF", 0.55)}}}
.k-hook .head{{background:#fff;border-bottom:10px solid {accent}}}
.k-warning{{background:{mix(accent, "#FFFFFF", 0.72)}}}
.k-warning .card{{border-color:{accent}}}
.k-warning .head{{background:{accent}}}
.k-warning .line{{border-left-color:{INK}}}
.k-cta .head{{background:{INK};color:#fff}}
.k-disclaimer{{background:{mix(INK, "#FFFFFF", 0.88)}}}
.k-disclaimer .head{{background:{mix(INK, "#FFFFFF", 0.25)};color:#fff}}
.k-disclaimer .line{{border-left-color:{mix(INK, "#FFFFFF", 0.25)}}}
@keyframes fade{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes rise{{from{{transform:translateY(70px)}}to{{transform:none}}}}
@keyframes out{{from{{opacity:1}}to{{opacity:0}}}}
@keyframes line{{from{{opacity:0;transform:translateX(-50px)}}to{{opacity:1;transform:none}}}}
"""
    js = """
window.__init = () => {
  window.__anims = document.getAnimations();
  for (const a of window.__anims) a.pause();
};
window.__setTime = (ms) => { for (const a of window.__anims) a.currentTime = ms; };
window.__inspect = () => {
  const overflow = [], fonts = [];
  const ctx = document.createElement('canvas').getContext('2d');
  ctx.font = '100px "%FONT%"';
  if (Math.abs(ctx.measureText('あいう').width - 300) > 1 || Math.abs(ctx.measureText('abcd').width - 200) > 1)
    fonts.push('%FONT%');
  for (const sec of document.querySelectorAll('.scene')) {
    const n = Number(sec.dataset.scene);
    for (const row of sec.querySelectorAll('.row'))
      if (row.scrollWidth > row.clientWidth + 1) overflow.push({scene: n, text: row.textContent});
    const card = sec.querySelector('.card'), zone = sec.querySelector('.zone');
    if (card.offsetHeight > zone.clientHeight + 1) overflow.push({scene: n, text: '(高さ)'});
  }
  const sup = document.querySelector('.sup');
  if (sup.scrollWidth > sup.clientWidth + 1) overflow.push({scene: 0, text: sup.textContent});
  return {overflow, fonts};
};
""".replace("%FONT%", FONT_FAMILY)
    return (
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">'
        f"<title>{e(script.title)}</title><style>{css}</style></head><body>"
        + "".join(sections)
        + '<div class="track"></div>'
        + f'<div class="sup" style="font-size:{script.supervisor_size}px">{e(script.supervisor)}</div>'
        + f"<script>{js}</script></body></html>"
    )


# ---- 投稿用テキスト ---------------------------------------------------------
def post_text(script: Script) -> str:
    """タイトル案・説明文・ハッシュタグ。台本にある言葉を並べるだけで、内容は足さない。"""
    content = [s for s in script.scenes if s.kind != "disclaimer"]
    titles = [script.title]
    with_tag = f"{script.title} #Shorts"
    if len(with_tag) <= S.TITLE_MAX_CHARS:
        titles.append(with_tag)
    hook = next((s for s in content if s.kind == "hook"), None)
    if hook and hook.heading != script.title:
        cand = f"{hook.heading}｜{script.title}"
        if len(cand) <= S.TITLE_MAX_CHARS:
            titles.append(cand)
    out = ["■ タイトル案"] + [f"{i}. {t}" for i, t in enumerate(titles, 1)]
    out += ["", "■ 説明文", script.title, ""]
    out += [f"・{s.heading}" for s in content]
    out += ["", script.supervisor, script.disclaimer, "", " ".join(script.hashtags)]
    out += ["", "■ ハッシュタグ", " ".join(script.hashtags)]
    out += ["", f"（動画の長さ: {script.total_seconds:.1f}秒 / 投稿前に監修者が動画を確認してください）"]
    return "\n".join(out) + "\n"


# ---- 書き出し ---------------------------------------------------------------
def today_str() -> str:
    return f"{datetime.now(ZoneInfo('Asia/Tokyo')):%Y%m%d}"


def _need(cmd: str) -> str:
    path = shutil.which(cmd)
    if not path:
        raise RenderError(f"{cmd} が見つかりません。インストールしてから実行してください。")
    return path


def _check_font() -> None:
    fc = shutil.which("fc-list")
    if not fc:
        return  # ブラウザ側の検査（__inspect）で確かめる
    found = subprocess.run([fc, ":lang=ja", "family"], capture_output=True, text=True).stdout
    if FONT_FAMILY not in found:
        raise RenderError(
            f"日本語フォント {FONT_FAMILY} が見つかりません（Ubuntu なら apt install fonts-ipafont-gothic）。"
        )


def _run(cmd: list[str], what: str, **kw) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if proc.returncode != 0:
        raise RenderError(f"{what}に失敗しました:\n{(proc.stderr or proc.stdout).strip()[-2000:]}")
    return proc


def make(script: Script, out_dir: str | Path, date: str | None = None, workers: int | None = None,
         keep_frames: str | Path | None = None) -> dict:
    """動画・サムネイル・投稿用テキストを out_dir に書き出し、パスと所要時間を返す。"""
    t0 = time.monotonic()
    node, ffmpeg = _need("node"), _need("ffmpeg")
    _check_font()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"{date or today_str()}_{S.slugify(script.title)}"
    total = script.total_frames
    tl = timeline(script)
    plan = frame_plan(tl, total)
    unique = sorted(set(plan))
    workers = workers or min(4, os.cpu_count() or 1)

    with tempfile.TemporaryDirectory(prefix="shorts_") as tmp:
        work = Path(keep_frames) if keep_frames else Path(tmp)
        (work / "u").mkdir(parents=True, exist_ok=True)
        seq = Path(tmp) / "seq"
        seq.mkdir()
        page = work / "index.html"
        page.write_text(build_html(script, tl), encoding="utf-8")
        plan_file = work / "plan.json"
        plan_file.write_text(json.dumps({
            "html": str(page.resolve()), "width": WIDTH, "height": HEIGHT, "workers": workers,
            "frames": [{"file": str((work / "u" / f"{f:05d}.png").resolve()),
                        "ms": (f + 0.5) * 1000 / FPS} for f in unique],
        }), encoding="utf-8")

        res = json.loads(_run([node, str(CAPTURE_JS), str(plan_file)], "フレームの撮影").stdout)
        if res["fonts"]:
            raise RenderError(f"フォント {FONT_FAMILY} がブラウザで使えません（別のフォントで代用されています）。")
        if res["overflow"]:
            where = "、".join(
                ("監修表記" if o["scene"] == 0 else f"シーン{o['scene']}") + f"「{o['text'][:16]}」"
                for o in res["overflow"]
            )
            raise ScriptError(f"文字が画面からはみ出します: {where}。短くしてください。")
        t_capture = time.monotonic()

        for f, src in enumerate(plan):
            os.symlink((work / "u" / f"{src:05d}.png").resolve(), seq / f"{f:05d}.png")

        # サムネイル: 1枚目のシーンで、行が出そろった時点の絵
        first = tl[0]
        thumb_frame = min(max(first["lines"], default=0) + LINE_IN, max(0, first["frames"] - CARD_OUT - 1))
        shutil.copyfile(work / "u" / f"{plan[thumb_frame]:05d}.png", f"{base}.png")

        seconds = total / FPS
        bar = script.design["accent_color"].replace("#", "0x")
        _run([
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-framerate", str(FPS), "-i", str(seq / "%05d.png"),
            "-f", "lavfi", "-i", f"color=c={bar}:s={WIDTH}x{BAR_HEIGHT}:r={FPS}",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-filter_complex",
            f"[0:v][1:v]overlay=x='-w+w*(n+1)/{total}':y=0:format=rgb:shortest=1,"
            "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p[v]",
            "-map", "[v]", "-map", "2:a", "-frames:v", str(total), "-t", f"{seconds:.6f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high", "-r", str(FPS),
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart",
            "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
            f"{base}.mp4",
        ], "動画の書き出し（ffmpeg）")

    Path(f"{base}.txt").write_text(post_text(script), encoding="utf-8")
    t1 = time.monotonic()
    return {
        "mp4": f"{base}.mp4", "png": f"{base}.png", "txt": f"{base}.txt",
        "seconds": seconds, "frames": total, "captured": len(unique),
        "elapsed": t1 - t0, "elapsed_capture": t_capture - t0,
        "bytes": os.path.getsize(f"{base}.mp4"),
    }
