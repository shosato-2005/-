# 奨学金レコメンドツール

大阪教育大学の学生向けに、プロフィールを入力すると条件との一致度に応じて奨学金を★1〜5でランキング表示するStreamlitアプリ（プロトタイプ）。

## できること

- 居住地・学年・専攻・コース・GPA・世帯収入を入力すると、収録されている奨学金を★1〜5でスコアリング
- 併用可否（JASSO給付との併用可／民間給付との併用可／条件付き可／不可／不明）・申込方法（個人申請／大学経由）での絞り込み
- スコア順／総支給金額順／支給人数順での並び替え、表示件数の変更（10件／15件／全件）

## セットアップ・起動方法

```bash
pip install -r requirements.txt
cd backend
python -m streamlit run app.py
```

`streamlit`コマンドが直接使えない環境があるため、`python -m streamlit`の形で実行してください。

UIを介さずレコメンド結果だけを確認したい場合：

```bash
cd backend
python demo.py
```

## テストの実行方法

```bash
pip install -r requirements-dev.txt
pytest
```

## ディレクトリ構成

```
backend/
  app.py         # Streamlitフロントエンド
  models.py      # データモデル（UserProfile, Scholarship など）
  scoring.py     # スコアリングロジック
  recommend.py   # レコメンド処理のオーケストレーション
  demo.py        # UIなしで動作確認するためのCLI
  majors.py      # 専攻・コースの一覧と学部/分野へのマッピング
  data/          # 奨学金データ（JSON）
  tests/         # pytestによるコアロジックのテスト
```

## 注意点

- 入力した情報（世帯収入・GPAなど）は画面表示のみに使われ、保存・ログ出力はされません
- 現状は大阪教育大学の学生を対象にしたプロトタイプです

開発方針や設計上の判断の詳細は [CLAUDE.md](./CLAUDE.md) を参照してください。
