# CLAUDE.md — 前原ルーキーズ 30周年記念映像

このリポジトリの主作業は `video/` の記念映像制作です（ルートの index.html 等は GitHub Pages の初期ファイルで無関係）。
**ユーザーへの返答は必ず日本語で。**

## 案件概要
- 対象：前原ルーキーズ（少年野球）30周年記念式典で上映する約30分の映像
- 納品：DVD 約6枚（11月18日(水)）／ 式典：11月21日(土)
- DVD制作は後工程。**現在は映像編集フェーズ**
- 編集の仕上げは人が Premiere Pro で行う。Claude Code は素材処理・叩き台生成・定型作業を担当

## スケジュール（2026年）
| 日付 | 作業 |
|---|---|
| 11/11(水) | 素材受領予定（未着。ダミーで先行制作済み） |
| 11/12〜17 | 編集・仕上げ（構成、メッセージ編集、音声調整） |
| 11/17(火) | DVDオーサリング・書き込み・再生確認 |
| 11/18(水) | 納品期限 |
| 11/21(土) | 式典で上映 |

## 構成の決定事項
- メッセージは **6名 × 最大5分**。これが映像の主役
- 並び：OP 1:00 → 30年のあゆみ(写真, 自動伸縮) → MSG1〜3 → 思い出の1ページ(写真) → MSG4〜6 → エンドロール 1:30
- 各メッセージ前に8秒の紹介カード、冒頭10秒に名前テロップ（左からスライドイン）
- 「30年のあゆみ」は `flex: true`。総尺を30:00に合わせて1〜6分で自動伸縮（全員5分だと約34分になり警告）
- 素材未着の箇所は絵文字ダミー（📸写真 / 👤🎤メッセージ、右上に赤い DUMMY バッジ）
- BGM はメッセージ中に自動ダッキング。メッセージ音声は -18 LUFS に正規化
- 仮の値：名前・肩書き・写真キャプションは全て架空。チームカラーは仮で紺 #0B2A5B / 金 #E8B400

## 仕組み（video/）
- `config/storyboard.yaml` … **構成表。編集はここだけ**。`source:` に素材パスを書けば本物に差し替わる
- `scripts/build.py` … ビルド本体（グラフィック→クリップ→音声→結合→要約版→XML）
- `scripts/timeline.py` … 構成表 → フレーム単位タイムライン計算（29.97fps）
- `scripts/graphics.py` … カード・テロップ PNG 生成（Pillow、1920x1080 基準で拡縮）
- `scripts/xml_export.py` … Premiere 用 FCP7 XML（V1本編 / V2テロップ / A1メッセージ音声 / A2 BGM）
- `scripts/doctor.py` … ローカル環境チェック
- `assets/fonts/` … IPAゴシック・Noto Color Emoji を同梱（OS 非依存にするため）
- `raw/`（素材置き場）と `out/`（出力）は Git 管理外

## コマンド
```bash
python video/scripts/doctor.py                 # 環境チェック（最初に）
python video/scripts/build.py --only plan      # 尺計算と timeline.csv だけ（数秒）
python video/scripts/build.py --res 720        # プレビュー全出力（4コアで約9分）
python video/scripts/build.py --res 1080       # 本番画質
python video/scripts/build.py --res 1080 --only xml   # Premiere用XMLだけ再生成
```
出力は `video/out/<res>p/`：rough_cut.mp4 / digest.mp4(約2.5分) / rough_cut.xml / timeline.csv / contact_sheet.png

## 注意点・既知の事項
- Premiere での XML 読み込みは**未検証**（クラウドでは Premiere が無かったため）。最初にローカルで開いて確認すること
- XML 内パスは実行マシンの絶対パス。素材のある PC で `--only xml` を再実行すれば正しくなる
- ffmpeg の drawtext に Windows の `C:` を渡すとフィルタ構文と衝突するため、ダミーメッセージのクリップは clips フォルダを cwd にして相対パスで描画している
- 縦動画はぼかし拡大背景＋中央配置で 16:9 化
- 実写写真は Ken Burns（2倍拡大後 zoompan、奇数枚ズームイン・偶数枚ズームアウト）

## 次にやること
1. ローカルで `doctor.py` → `build.py --res 720` を通し、Premiere で `rough_cut.xml` を開けるか確認
2. 6名の名前・肩書き、チームカラー、年表の出来事を構成表に反映
3. 素材が届いたら `video/raw/` に置き、素材一覧（ffprobe で尺・解像度・音声有無）と不足リストを作る
4. メッセージを文字起こし（Whisper）→ 字幕・カット候補
5. 後工程：DVD（NTSC 720x480 16:9 MPEG-2、DVD-R、メニュー無し自動再生）と6枚+予備の焼き・再生確認

## Git
- 作業ブランチ：`claude/nifty-clarke-9rzvr5`
- 動画・素材ファイルはコミットしない（容量・個人情報）
