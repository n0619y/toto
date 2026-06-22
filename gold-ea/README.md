# FX GOLD EA Project

XAU/USD（ゴールド）向け MetaTrader 4 (MQL4) 自動売買 EA の開発プロジェクト。

> **目標**: 統計的な優位性と適切なリスク管理に基づき、長期的に期待値がプラスになる
> （＝資金が増える）EA を作成し、データで検証する。

## ディレクトリ構成

```
gold-ea/
├── README.md          このファイル
├── docs/              要件定義・設計・開発記録
│   └── REQUIREMENTS.md  要件定義書
├── experts/           EA 本体（.mq4）
├── include/           共通モジュール（.mqh）— 資金管理・リスク管理など
├── presets/           パラメータプリセット（.set）
└── backtest/          バックテスト結果・レポート
```

## ステータス

- [x] Phase 0: 要件定義（→ `docs/REQUIREMENTS.md`）
- [x] Phase 1: EA骨格 + 資金/リスク管理（→ `include/`）
- [x] Phase 2: 戦略MVP（EMAクロス → `experts/GoldTrendEA.mq4`。※ベンチマーク用）
- [x] データ分析 & 本命戦略の設計・OOS検証（→ `docs/ANALYSIS_FINDINGS.md`）
- [x] **本命EA: GoldVBO（ボラブレイク）実装**（→ `experts/GoldVBO.mq4`）
- [ ] Phase 3: **XM実データでMT4バックテスト**（データ出力 → `docs/DATA_EXPORT_GUIDE.md`）
- [ ] Phase 4: フォワードテスト（デモ）
- [ ] Phase 5: 少額リアル運用

## 本命EA: GoldVBO

データ分析（XAUUSD 2012-2022 H1）とアウトオブサンプル検証に基づく
ボラティリティ・ブレイクアウトEA。設計と検証結果は
[`docs/ANALYSIS_FINDINGS.md`](docs/ANALYSIS_FINDINGS.md) を参照。

- OOS実績（公開データ・コスト$0.5/往復）: PF 1.27 / CAGR +17% / 最大DD -12.7%
- **時刻に非依存**な設計（タイムゾーン不明問題を回避）
- ⚠ 公開データの参考値。**XM実データでの再検証が前提**。

## クイックスタート

1. 導入・バックテスト手順: [`docs/BACKTEST_GUIDE.md`](docs/BACKTEST_GUIDE.md)
2. XM実データの出力: [`docs/DATA_EXPORT_GUIDE.md`](docs/DATA_EXPORT_GUIDE.md)

ゴールド銘柄名は `GOLD`。EA を `GOLD` の H1 チャートに適用。

## 注意

自動売買は元本を失うリスクを伴います。必ず **デモ → 少額リアル** の順で
段階的に検証してから運用してください。本プロジェクトの成果物は投資助言ではありません。

---
※ 本プロジェクトは同リポジトリ内の他プロジェクトとは独立しており、`gold-ea/` 配下で完結します。
