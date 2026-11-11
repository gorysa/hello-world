# 前原ルーキーズ 30周年記念映像 ビルダー

構成表 `config/storyboard.yaml` を1か所編集するだけで、以下をまとめて再生成します。

| 出力 (`out/<解像度>p/`) | 内容 |
|---|---|
| `rough_cut.mp4` | 通し映像（約30分） |
| `digest.mp4` | 各パートの冒頭だけを繋いだ確認用（約2.5分） |
| `rough_cut.xml` | Premiere Pro 用タイムライン（ファイル → 読み込み） |
| `timeline.csv` | タイムコード付き構成表（Excelで開ける） |
| `contact_sheet.png` | 各パートのサムネイル一覧 |

## 使い方

```bash
pip install pyyaml pillow          # ffmpeg も必要
python video/scripts/build.py --res 720            # プレビュー（約9分）
python video/scripts/build.py --res 1080           # 本番画質
python video/scripts/build.py --only plan          # 尺の計算とCSVだけ（数秒）
python video/scripts/build.py --res 1080 --only xml --media-root D:/maehara30/video
```

## 構成（6名 × 最大5分のメッセージが主役）

```
OP 1:00 → 30年のあゆみ(写真・自動伸縮) → MSG1〜3 → 思い出の1ページ(写真30秒) → MSG4〜6 → エンドロール 1:30
```

- 各メッセージの前に8秒の紹介カード、冒頭10秒に名前テロップ。
- **「30年のあゆみ」は `flex: true`**：メッセージの実尺が決まると、総尺が30:00に収まるよう写真パートの長さが自動で伸び縮みします（1〜6分）。
  6名全員が5分ちょうどの場合は約34分になり、警告が出ます。
- BGMはメッセージ中に自動で音量を下げます（`bgm.duck_volume`）。

## 本物の素材への差し替え

1. 素材を `video/raw/` に置く（Gitには含めません）。
2. 構成表の `source:` にパスを書く。
   ```yaml
   - id: MSG1
     type: message
     name: 山田 太郎
     source: raw/msg_yamada.mp4    # ← 実尺は自動で読み取り
   ```
   写真は `photos:` の各行に `source: raw/photo/1996_01.jpg` を追加します。
3. 再実行する。`source` が空の素材や、ファイルが見つからない素材は、自動で絵文字ダミー（右上に赤い DUMMY バッジ）になります。

メッセージ音声は -18 LUFS に自動で揃えます。

## Premiere での扱い

- V1：本編カット / V2：テロップ（透過PNG） / A1：メッセージ音声 / A2：BGM
- XML内のパスは書き出したマシンの絶対パスです。素材のあるPCで実行するか、`--media-root` でパスを書き換えてください。
