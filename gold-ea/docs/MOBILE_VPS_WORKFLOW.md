# スマホのClaude ↔ VPSのMT4 連携ワークフロー

「物理PCを持っていなくても」スマホ（Claudeアプリ）だけで開発を続けつつ、
**Windows VPS上のMT4**でデータ取得・全ティック検証・本番運用までを回すための手順。

```
[スマホのClaude] EAを改良 → GitHubにpush
        │ (GitHubが受け渡し場所)
        ▼
[VPSのMT4]  git pullで.mq4取得 → コンパイル → 全ティック検証/運用
        │
        ▼
[結果のスクショ・数値] をスマホのClaudeに渡す → また改良…
```

- **開発の頭脳 = スマホのClaude**（このまま。移行不要）
- **実行・検証の場 = VPSのMT4**（ここだけ新規に用意）
- 両者の橋渡し = **GitHub**（今のpush習慣がそのまま活きる）

---

## 0. 全体像と費用感

| 項目 | 内容 | 目安 |
|---|---|---|
| Windows VPS | MT4を24時間動かす土台 | 月 500〜2,000円程度（XMの無料VPS条件を満たせば0円も可） |
| RDPアプリ | スマホからVPSに接続 | 無料（後述） |
| XM口座 | データ取得・デモ/リアル | 無料 |
| GitHub | EAの受け渡し | 無料 |

> **XMの無料VPS**: 一定の証拠金残高＋月間取引量などの条件を満たすと、XMがVPSを
> 無料提供する制度があります（条件は変動するため公式で要確認）。条件未達なら
> 市販のWindows VPS（後述の「FX向けVPS」）を借りればOK。

---

## 1. Windows VPSを用意する

### 選択肢
- **XMの無料VPS**（条件を満たすなら最有力。XM会員ページから申請）
- **FX向け市販VPS**（例: お名前.com デスクトップクラウド for FX, Ag VPS, FXTF系VPS 等）
  - スペック目安: **メモリ1.5GB以上 / Windows Server**。MT4を1〜2個動かすだけなら最小構成で足りる。
  - 取引サーバーに近い**ロンドン or ニューヨークのロケーション**だと約定が安定（任意）。

### 申し込み後にもらう情報（メモしておく）
- VPSの **IPアドレス**
- **ユーザー名**（多くは `Administrator`）
- **パスワード**

---

## 2. スマホからVPSに接続（RDP）

1. スマホに **Microsoftリモートデスクトップ（RD Client）** アプリを入れる（iOS/Android無料）。
2. 「PCを追加」→ VPSの **IP / ユーザー名 / パスワード** を入力。
3. 接続すると、スマホ画面に**Windowsのデスクトップ**が出る。以降はここでMT4を操作。

> タブレット＋Bluetoothキーボードがあると作業がかなり楽になります。

---

## 3. VPSにMT4とGitをインストール

VPSのデスクトップ（RDP越し）で:

1. **XMのMT4** をダウンロード＆インストール（XM公式 → MT4 for Windows）。
   - インストール後、XMの口座番号・パスワード・**取引サーバー**を選んでログイン。
2. **Git for Windows** をインストール（https://git-scm.com/download/win）。
   - これで `git pull` でこのリポジトリのEAを取り込めるようになる。

---

## 4. GitHubからEAを取り込む（初回）

VPSで「Git Bash」を開いて、このリポジトリをクローン:

```bash
# 任意の作業フォルダで
git clone https://github.com/n0619y/toto.git
cd toto
git checkout claude/gold-trading-ea-2l0ne5    # 開発ブランチ
```

> プライベートリポジトリの場合は、GitHubで**Personal Access Token (PAT)** を発行し、
> パスワードの代わりに使う（またはGitHub CLIでログイン）。

### EAファイルをMT4の所定フォルダへ配置
MT4の **[ファイル] → [データフォルダを開く]** で開いた `MQL4/` に、リポジトリの中身をコピー:

| リポジトリ | → MT4データフォルダ |
|---|---|
| `gold-ea/experts/GoldVBO.mq4` | `MQL4/Experts/` |
| `gold-ea/experts/GoldTentei.mq4` | `MQL4/Experts/` |
| `gold-ea/include/*.mqh` | `MQL4/Include/` |
| `gold-ea/scripts/ExportHistoryCSV.mq4` | `MQL4/Scripts/` |

> **コピーを自動化したい場合**: `MQL4/Experts` 等へ直接cloneせず、`git pull`後に
> コピーするミニ.batを作っておくと、更新のたびワンクリックで反映できる（任意）。

---

## 5. 更新を受け取る（2回目以降）

スマホのClaudeでEAを直して push したら、VPS側はこれだけ:

```bash
cd toto
git pull origin claude/gold-trading-ea-2l0ne5
# 変わった.mq4をMQL4/Experts等へコピー
```

その後、MetaEditorで **再コンパイル**（F7）→ ストラテジーテスターで再検証。

---

## 6. 検証する（重要な設定）

詳細は [`BACKTEST_GUIDE.md`](BACKTEST_GUIDE.md) と [`DATA_EXPORT_GUIDE.md`](DATA_EXPORT_GUIDE.md)。
ここでは**外してはいけない点**だけ:

- 銘柄 **GOLD** / 時間足 **H1**。
- モデルは **必ず「全ティック」**。
  - 特に **GoldVBO は逆指値ストップ注文で約定する設計**で、「始値のみ」モデルだと
    バー内のストップ約定を再現できず**結果が無意味**になる（`entry_parity.py` 参照）。
- KPI: PF>1.2 / 最大DD<20% を各EA個別に確認 → デモで2戦略同時フォワード。

---

## 7. 結果をスマホのClaudeに渡す

- テスターの**レポート画面のスクショ**、または「グラフ」「詳細」タブの数値をClaudeに共有。
- 「このパラメータでDDが大きい」「取引数が少ない」等を伝えれば、Claudeが原因を分析して
  EAを修正→push→VPSでpull、のループを回せます。

---

## よくある疑問

**Q. このClaudeプロジェクトごとPCに移す必要は？**
→ **不要**。開発はスマホのClaude＋GitHubで完結。VPSは「MT4を動かす場所」を足すだけ。

**Q. スマホのMT4アプリじゃダメ？**
→ ダメ。スマホ版MT4/MT5は**EA実行・バックテスト不可**（閲覧と手動発注のみ）。
　EAを動かすにはWindows版MT4（＝PCかVPS）が必須。

**Q. VPSは本番運用にも使える？**
→ むしろ本番向き。PCを切っても24時間EAが動き続けるので、デモ→リアルでもそのまま使える。

**Q. Macしかない場合は？**
→ Macに仮想Windows（Parallels等）を入れてもよいが、**VPSの方が手間が少なく24時間運用**にも向く。
