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
- [x] データ分析 & 戦略設計・OOS検証（→ `docs/ANALYSIS_FINDINGS.md`）
- [x] **EA①: GoldVBO（ボラブレイク）**（→ `experts/GoldVBO.mq4`）
- [x] **EA②: GoldTentei（天底ロジック/押し目）**（→ `experts/GoldTentei.mq4`）
- [x] **2戦略ポートフォリオ検証**（低相関+0.04, 合成でDD縮小 → `docs/PORTFOLIO_GUIDE.md`）
- [x] **XM実データ(2023-2025)で確定パラメータを再検証 → 優位性存続**（→ `docs/XM_VALIDATION.md`）
- [ ] Phase 3: **MT4ストラテジーテスター（全ティック）で実約定を確認**
- [ ] Phase 4: フォワードテスト（デモ・2戦略同時）
- [ ] Phase 5: 少額リアル運用

## 本命: 2戦略ポートフォリオ

性質の異なる（ほぼ無相関の）2EAを同口座で併用し、DDを抑えつつ資金を増やす。

| EA | 性質 | OOS実績(コスト$0.5) |
|----|------|---------------------|
| `GoldVBO` | ブレイク=強さを買う | PF1.27 / CAGR+19% / DD-12% |
| `GoldTentei` | 押し目=弱さを買う(H4トレンドMTF) | PF1.42 / CAGR+4% / DD-6.5% |
| **合成(推奨60/40)** | 低相関で分散 | **CAGR+13% / DD-8.5% / Sharpe1.23** |

設計・検証は [`docs/ANALYSIS_FINDINGS.md`](docs/ANALYSIS_FINDINGS.md)、
併用運用は [`docs/PORTFOLIO_GUIDE.md`](docs/PORTFOLIO_GUIDE.md) を参照。
⚠ 公開データ(2012-2022)の参考値。**XM実データでの再検証が前提**。

## クイックスタート

1. 導入・バックテスト手順: [`docs/BACKTEST_GUIDE.md`](docs/BACKTEST_GUIDE.md)
2. XM実データの出力: [`docs/DATA_EXPORT_GUIDE.md`](docs/DATA_EXPORT_GUIDE.md)
3. 2戦略の併用運用: [`docs/PORTFOLIO_GUIDE.md`](docs/PORTFOLIO_GUIDE.md)
4. PCなしで回す（スマホ↔VPS）: [`docs/MOBILE_VPS_WORKFLOW.md`](docs/MOBILE_VPS_WORKFLOW.md)

ゴールド銘柄名は `GOLD`。EA を `GOLD` の H1 チャートに適用。
2EAはマジックナンバーが別なので同チャート/同口座で併用可。

## 注意

自動売買は元本を失うリスクを伴います。必ず **デモ → 少額リアル** の順で
段階的に検証してから運用してください。本プロジェクトの成果物は投資助言ではありません。

---
※ 本プロジェクトは同リポジトリ内の他プロジェクトとは独立しており、`gold-ea/` 配下で完結します。
