"""デモ用のサンプルデータ生成（APIキー無しで全機能を試すため）。

※ 生成される投稿・ショップ・価格はすべて架空のサンプルです。
"""
from __future__ import annotations

import random
from datetime import date as Date, datetime, timedelta, timezone

from .models import Comment, Post

# (キーワード, 地域, 投稿テンプレ, 好意的コメント, 否定的コメント, 開始日オフセット, 盛り上がり)
TOPICS = [
    ("ネオンフロンティア", "ja",
     ["新弾ネオンフロンティアの収録リスト出た！SARのイラスト最高", "ネオンフロンティア予約抽選全部落ちた…",
      "ネオンフロンティア 箱買いしたいけど高い", "ネオンフロンティアのSAR、当たりはどれになりそう？"],
     ["イラスト神すぎる", "楽しみすぎて眠れない", "このSAR絶対欲しい", "収録内容最高では"],
     ["また転売の餌食になりそう", "抽選全部落選…最悪", "定価で買えないのおかしい"], 0, 1.0),
    ("ピカチュウex", "ja",
     ["ピカチュウex SAR 買取価格がまた上がってる", "ピカチュウexのSAR引いた！！震える",
      "ピカチュウex 高騰しすぎでは？"],
     ["おめでとう！神引き", "かわいいし上がるのも納得", "持っててよかった嬉しい"],
     ["高すぎて手が出ない", "転売ヤーが買い占めてるだけでしょ", "バブルだと思う、残念"], -3, 0.8),
    ("シティリーグ", "ja",
     ["シティリーグ優勝デッキまとめ。リザードン型が強い", "シティリーグ初参加してきた、楽しかった",
      "シティリーグの抽選倍率えぐい"],
     ["おめでとうございます！", "デッキレシピ助かる", "楽しかったなら最高"],
     ["抽選倍率おかしい", "また落選、運営なんとかして"], -5, 0.5),
    ("Charizard", "global",
     ["Charizard ex SIR pull from my first pack! insane", "Is the Charizard price going to crash?",
      "Charizard alt art finally graded PSA 10"],
     ["Congrats, amazing pull!", "That card is gorgeous", "Awesome, love it"],
     ["Prices are ridiculous right now", "Scalpers ruined this set", "Overpriced and I'm disappointed"], -2, 0.9),
    ("Fake", "global",
     ["PSA warning: Fake booster boxes being sold on marketplace", "Got scammed with a Fake resealed box",
      "How to spot Fake shrink wrap on booster boxes"],
     ["Great guide, thanks", "Super helpful, nice post"],
     ["This is terrible, scammers everywhere", "Awful, I got a fake too", "Worst experience ever"], -1, 0.6),
    ("再販", "ja",
     ["ポケセンオンラインで再販決定！", "再販あるけどまた瞬殺かな", "再販ありがたい、今度こそ買いたい"],
     ["再販ありがたい", "助かる！", "嬉しい今度こそ"],
     ["どうせ売り切れ", "転売対策してほしい", "買えない未来しか見えない"], 0, 0.7),
    ("World Championships", "global",
     ["World Championships decklists are out", "World Championships promo cards revealed!",
      "Watching World Championships finals, so hyped"],
     ["So hyped!", "Amazing games", "Great event"],
     ["The stream quality was terrible"], -4, 0.4),
]

SOURCES_JA = ["x", "x", "threads", "instagram"]
SOURCES_GL = ["reddit", "reddit", "x", "instagram", "threads"]


def posts_for_day(day: Date, seed: int = 0) -> list[Post]:
    rnd = random.Random(f"{day.isoformat()}-{seed}")
    today = Date.today()
    out: list[Post] = []
    n = 0
    for kw, region, texts, pos, neg, start, heat in TOPICS:
        age = (day - (today + timedelta(days=start))).days
        if age < 0:
            continue
        # 話題は数日かけて盛り上がり、その後落ち着く
        intensity = heat * max(0.15, 1.4 - 0.18 * abs(age - 1)) * rnd.uniform(0.7, 1.3)
        for i in range(max(1, int(intensity * 14))):
            n += 1
            src = rnd.choice(SOURCES_JA if region == "ja" else SOURCES_GL)
            likes = int(rnd.lognormvariate(4.5, 1.2) * intensity)
            ncom = rnd.randint(3, 12)
            ratio_pos = 0.6 if kw not in ("Fake", "再販") else 0.3
            comments = []
            if src != "instagram":  # Instagramは他人のコメント本文がAPIで取れない想定
                for j in range(ncom):
                    pool = pos if rnd.random() < ratio_pos else neg
                    if rnd.random() < 0.2:
                        pool = ["これってどこで買える？", "Where can I buy this?", "情報ありがとう"]
                    comments.append(Comment(id=f"demo-c-{day}-{n}-{j}", author=f"user{rnd.randint(1, 999)}",
                                            text=rnd.choice(pool), likes=int(rnd.expovariate(0.2))))
            created = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=rnd.randint(0, 23))
            out.append(Post(
                id=f"{src}:demo-{day}-{n}", source=src, region=region, author=f"sample_{n}",
                text=rnd.choice(texts) + ("" if rnd.random() < 0.5 else " #ポケカ" if region == "ja" else " #PokemonTCG"),
                url="#", created_at=created.isoformat(), likes=likes,
                comments_count=len(comments) or rnd.randint(2, 30), shares=int(likes * rnd.uniform(0.05, 0.3)),
                views=likes * rnd.randint(20, 60), lang="ja" if region == "ja" else "en", comments=comments,
            ))
    return out


# ---------- 買取表 ----------
CARDS = [  # (名前, 型番, レアリティ, 基準価格, 7日トレンド係数)
    ("ピカチュウex", "132/106", "SAR", 38000, 0.035), ("リザードンex", "201/165", "SAR", 52000, 0.004),
    ("ミュウex", "205/165", "SAR", 9800, -0.002), ("ナンジャモ", "096/071", "SAR", 61000, -0.012),
    ("サーナイトex", "101/078", "SAR", 7200, 0.001), ("ブラッキーex", "217/187", "SAR", 128000, 0.018),
    ("イーブイex", "210/187", "SAR", 21000, 0.009), ("ゲッコウガex", "120/101", "SAR", 6500, -0.02),
    ("リーリエの決心", "118/100", "SAR", 45000, 0.006), ("ニンフィアex", "221/187", "SAR", 18000, 0.012),
    ("メガゲンガーex", "098/080", "SAR", 15500, 0.03), ("ルギアV", "110/098", "SR", 33000, -0.004),
    ("ミモザ", "125/108", "SAR", 8800, -0.015), ("テツノツツミ", "082/071", "AR", 2400, 0.0),
    ("ネオンフロンティア BOX", "", "BOX", 9500, 0.022), ("ピカチュウ", "001/SV-P", "PROMO", 4200, 0.011),
]
SHOPS = {"サンプル買取店A": 1.0, "サンプル買取店B": 0.96, "サンプル買取店C": 0.92}


def buylist_for_day(day: Date) -> dict[str, list[dict]]:
    out = {}
    today = Date.today()
    t = (day - today).days  # 0 が今日、負の値が過去
    for shop, mult in SHOPS.items():
        rnd = random.Random(f"{shop}-{day}")
        rows = []
        for name, num, rar, base, trend in CARDS:
            if rnd.random() < 0.05:  # たまに掲載なし
                continue
            price = base * (1 + trend / 4) ** t * mult * rnd.uniform(0.97, 1.03)
            if name == "ピカチュウex" and t >= -3:   # 話題と連動した直近の急騰
                price *= 1 + 0.08 * (t + 4)
            price = int(round(price, -2))
            rows.append({"card_name": f"{name}【{rar}】" if rnd.random() < 0.5 else name,
                         "card_number": num, "rarity": rar, "price": f"¥{price:,}", "condition": ""})
        out[shop] = rows
    return out


# ---------- 自動投稿のシミュレーション（架空の反応） ----------
ARCHE_QUALITY = {"question": 1.5, "souba": 1.35, "voice": 1.15, "matome": 1.0, "sokuho": 0.9, "kaigai": 0.8}


def simulate_autopost(dates: list[str], hours_jst=(8, 12, 20)) -> None:
    """過去日付で 1日3サイクル の自動投稿を回し、架空の反応数値を付けて学習させる。"""
    from . import db
    from .autopost import cycle, feedback

    jst = timezone(timedelta(hours=9))
    counter = {"n": 0}

    def fake_post(pf, text, arche):
        counter["n"] += 1
        return f"demo-{pf}-{counter['n']}"

    for d in dates:
        for h in hours_jst:
            now = datetime.fromisoformat(f"{d}T{h:02d}:05:00").replace(tzinfo=jst).astimezone(timezone.utc)
            # 前のサイクルまでの投稿に架空の反応を付ける（本番では feedback.collect が API から取得）
            with db.connect() as conn:
                for p in db.own_posts(conn, "status='posted'"):
                    age = feedback.age_hours(p["created_at"], now)
                    if age < 6 or (p["metrics_at"] and feedback.age_hours(p["created_at"], datetime.fromisoformat(p["metrics_at"])) >= 24):
                        continue
                    rnd = random.Random(p["platform_id"])
                    q = ARCHE_QUALITY.get(p["archetype"], 1.0) * rnd.uniform(0.6, 1.4) * min(1, age / 24) ** 0.5
                    views = int(rnd.lognormvariate(7.5, 0.4) * min(1, age / 24))
                    likes = int(views * 0.02 * q)
                    m = {"views": views, "likes": likes, "replies": int(likes * 0.12 * q), "reposts": int(likes * 0.15),
                         "quotes": int(likes * 0.03), "bookmarks": int(likes * 0.1)}
                    pos = 55 if p["archetype"] != "kaigai" else 40
                    neg = 15 if p["archetype"] not in ("voice", "question") else 25
                    senti = {"overall": "好意的" if pos - neg > 25 else "賛否両論", "score": pos - neg, "analyzed": m["replies"],
                             "ratio": {"positive": pos, "negative": neg, "neutral": 100 - pos - neg}}
                    db.update_own_post(conn, p["id"], metrics=m, metrics_at=now.isoformat(), reply_sentiment=senti)
            feedback.rescore()
            feedback.update_playbook(d, use_ai=False)
            cycle.post_cycle(d, now=now, force_offline=True, simulate=fake_post)
