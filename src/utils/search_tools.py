"""Web検索ツール。

優先順位:
  1. Tavily API（環境変数 TAVILY_API_KEY が設定されている場合）
  2. requests + beautifulsoup4 による DuckDuckGo HTML 検索のフォールバック

robots.txt 遵守・User-Agent 設定・アクセス間隔（1秒）を守ります。
検索が完全に失敗した場合も例外で全体を止めず、空リストを返してフォールバックします。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import List
from urllib.parse import quote_plus, urlparse
from urllib.robotparser import RobotFileParser

from dotenv import load_dotenv

from .common import get_logger, load_settings

load_dotenv()
logger = get_logger()


@dataclass
class SearchResult:
    """検索結果1件。"""

    title: str
    url: str
    snippet: str = ""
    content: str = ""  # 本文（取得できた場合）


class SearchTools:
    """Tavily 優先・bs4 フォールバックの検索ツール。"""

    def __init__(self) -> None:
        cfg = load_settings()["search"]
        self.results_per_query: int = cfg.get("results_per_query", 6)
        self.interval: float = cfg.get("request_interval_sec", 1.0)
        self.user_agent: str = cfg.get("user_agent", "PediatricContentBot/1.0")
        self.timeout: int = cfg.get("timeout_sec", 20)
        self.tavily_key = os.getenv("TAVILY_API_KEY")
        self._use_tavily = bool(self.tavily_key and not self.tavily_key.startswith("tvly-xxxx"))
        self._robots_cache: dict = {}
        if self._use_tavily:
            logger.info("検索エンジン: Tavily API を使用します")
        else:
            logger.info("検索エンジン: Tavily未設定のため requests+bs4 フォールバックを使用します")

    # ------------------------------------------------------------------ public
    def search(self, query: str, max_results: int | None = None) -> List[SearchResult]:
        """クエリで検索し、SearchResult のリストを返す。失敗時は空リスト。"""
        n = max_results or self.results_per_query
        try:
            if self._use_tavily:
                return self._search_tavily(query, n)
            return self._search_fallback(query, n)
        except Exception as exc:
            logger.warning("検索失敗 (query=%r): %s — 空の結果で継続します", query, exc)
            return []

    # ----------------------------------------------------------------- Tavily
    def _search_tavily(self, query: str, n: int) -> List[SearchResult]:
        import requests

        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self.tavily_key,
                "query": query,
                "max_results": n,
                "search_depth": "advanced",
                "include_raw_content": True,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        results: List[SearchResult] = []
        for item in data.get("results", []):
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", "")[:500],
                    content=(item.get("raw_content") or item.get("content") or "")[:6000],
                )
            )
        time.sleep(self.interval)
        return results

    # --------------------------------------------------------------- fallback
    def _search_fallback(self, query: str, n: int) -> List[SearchResult]:
        """DuckDuckGo の HTML版を使ったシンプルな検索フォールバック。"""
        import requests
        from bs4 import BeautifulSoup

        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {"User-Agent": self.user_agent}
        resp = requests.get(url, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        results: List[SearchResult] = []
        for a in soup.select("a.result__a")[:n]:
            href = a.get("href", "")
            title = a.get_text(strip=True)
            snippet_el = a.find_parent("div", class_="result__body")
            snippet = ""
            if snippet_el:
                s = snippet_el.select_one(".result__snippet")
                snippet = s.get_text(strip=True) if s else ""
            results.append(SearchResult(title=title, url=href, snippet=snippet))

        time.sleep(self.interval)

        # 各結果ページの本文を控えめに取得（robots.txt遵守）
        for r in results:
            r.content = self._fetch_page_text(r.url)
        return results

    def fetch_raw_html(self, url: str) -> str:
        """robots.txt を遵守してページの生HTMLを取得する（スクレイピング用）。

        取得不可・失敗時は空文字を返す。アクセス間隔(1秒)とUAを守る。
        """
        if not url or not self._can_fetch(url):
            logger.debug("robots.txt によりスキップ: %s", url)
            return ""
        try:
            import requests

            headers = {"User-Agent": self.user_agent}
            resp = requests.get(url, headers=headers, timeout=self.timeout)
            time.sleep(self.interval)
            return resp.text if resp.status_code == 200 else ""
        except Exception as exc:
            logger.debug("HTML取得失敗 (%s): %s", url, exc)
            return ""

    def _can_fetch(self, url: str) -> bool:
        """robots.txt を確認して取得可否を返す。取得不能時は安全側で True。"""
        try:
            parsed = urlparse(url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            if base not in self._robots_cache:
                rp = RobotFileParser()
                rp.set_url(base + "/robots.txt")
                try:
                    rp.read()
                except Exception:
                    rp = None  # robots.txt が読めない場合は制限しない
                self._robots_cache[base] = rp
            rp = self._robots_cache[base]
            if rp is None:
                return True
            return rp.can_fetch(self.user_agent, url)
        except Exception:
            return True

    def _fetch_page_text(self, url: str) -> str:
        """ページ本文テキストを取得（robots.txt遵守、1秒間隔、最大6000字）。"""
        if not url or not self._can_fetch(url):
            return ""
        try:
            import requests
            from bs4 import BeautifulSoup

            headers = {"User-Agent": self.user_agent}
            resp = requests.get(url, headers=headers, timeout=self.timeout)
            time.sleep(self.interval)
            if resp.status_code != 200:
                return ""
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = " ".join(soup.get_text(" ").split())
            return text[:6000]
        except Exception as exc:
            logger.debug("本文取得失敗 (%s): %s", url, exc)
            return ""
