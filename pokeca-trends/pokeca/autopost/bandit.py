"""投稿の「型」選び（UCB1）。成績の良い型ほど多く、成績が未知の型もときどき試す。"""
from __future__ import annotations

import math
from collections import defaultdict


def stats(evaluated: list[dict]) -> dict[str, dict]:
    """evaluated: reward（0〜1の相対評価）が付いた自分の投稿。"""
    s: dict[str, dict] = defaultdict(lambda: {"n": 0, "sum": 0.0})
    for p in evaluated:
        if p.get("reward") is None:
            continue
        s[p["archetype"]]["n"] += 1
        s[p["archetype"]]["sum"] += p["reward"]
    return {k: {**v, "mean": v["sum"] / v["n"]} for k, v in s.items()}


def choose(archetypes: list[str], evaluated: list[dict], c: float = 0.8, exclude: set[str] = frozenset()) -> str:
    arms = [a for a in archetypes if a not in exclude] or archetypes
    st = stats(evaluated)
    total = sum(st.get(a, {"n": 0})["n"] for a in arms)
    best, best_v = arms[0], -1.0
    for a in arms:
        n = st.get(a, {"n": 0})["n"]
        if n == 0:
            return a  # まだ試していない型を優先
        v = st[a]["mean"] + c * math.sqrt(math.log(total + 1) / n)
        if v > best_v:
            best, best_v = a, v
    return best
