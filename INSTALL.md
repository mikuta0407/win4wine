# 導入手順

**日本語** · [English](.github/readme/INSTALL.en.md)

> [!WARNING]
> - Windows XP の ISO はご自身で入手してください。利用は自己責任でお願いします（[README の注意](README.md#注意)）。
> - 実験的なプロジェクトです。確かめているのは、**新しくインストールした Debian 13** に `scripts/setup.sh` で入れた場合だけです。
>   すでに使っている環境への導入は試していません。導入スクリプトはパッケージを入れ、LightDM の設定を変えることがあります
>   （下の「2. スクリプトがすること」）。仮想マシンや試験用のマシンで試すことをおすすめします。

## 必要なもの

- **Debian 13（trixie）amd64** のマシン（実機または仮想マシン）。デスクトップ環境は要りません。
  Arch Linux とその派生（CachyOS など）では、`scripts/setup.sh` が同じパッケージを pacman で入れ、今のディスプレイマネージャのままにします（パッケージの段階より先は未確認）。チェックアウトのパスに空白は使えません。
- **Windows XP Professional SP3（x86）の ISO**（または XP の Windows ディレクトリ）。**日本語版か英語版**です。
  どちらかは ISO から自動で判断します。
- ネットワーク（パッケージと Wine のソースの取得に使います）と、**40 GB ほどの空き**（Wine のソースとビルド）。
- sudo を使える利用者。

## 1. まとめて入れる

XP のシェルを使う利用者で（root ではなく）実行してください。パッケージとシステムのファイルには sudo を使います。

```sh
git clone https://github.com/mikuta0407/win4wine.git ~/win4wine
cd ~/win4wine
scripts/setup.sh --media /path/to/WindowsXPSP3.iso --greeter
```

| オプション | 意味 |
|---|---|
| `--media PATH` | XP の ISO または Windows ディレクトリ（必須）。`--shell win7` では Windows 7 SP1 x64 の ISO |
| `--greeter` | ログイン画面を XP のようこそ画面にします（LightDM をディスプレイマネージャにします） |
| `--no-greeter` | 今のログイン画面のままにします（既定）。XP のカーソルだけ入れます |
| `--theme luna\|classic` | 見た目です。`luna`（既定。XP の「Windows XP」のテーマ、XP 形式のスタートメニュー、壁紙 Bliss）か `classic`（XP の「Windows クラシック」のテーマ、クラシック形式のスタートメニュー、壁紙なし）。ReactOS のシェルでは `classic`（既定）、`lautus`、`lunar`、`mizu` |
| `--dpi N` | 画面の DPI（XP の「DPI 設定」）です。96（通常）、120（大きいサイズ）、または 19〜480 の任意の値。XP のシェル、セッションの Linux のアプリ、ようこそ画面に効きます |
| `--wayland` | Wayland のセッション「XP Shell (Wine, Wayland)」も入れます（labwc と wlroots をビルドします）。モニターごとの倍率、125%・150% などの倍率が使え、Wayland のアプリにも XP の枠が付きます。`--greeter` と一緒なら、ようこそ画面の既定のセッションになります。**X11 のセッション以上に実験的です**（確かめた範囲が狭く、既知の制限があります。[docs/wayland.md](docs/wayland.md)） |
| `--wine-install DIR` | 別の Debian 13 マシンでビルドした Wine（その `.local/wine-install` を写したもの）を使い、ここではビルドしません |
| `--jobs N` | Wine のビルドの並列数です（既定は CPU の数） |
| `--no-shadowfb` | 仮想マシンで、X の描き方を変えません（下の「2. スクリプトがすること」の 8） |
| `--shell reactos` | XP のシェルの代わりに ReactOS のシェルを入れます（`--media` は要りません。下の「ReactOS のシェル」） |
| `--shell win7` | Windows 7 のシェル（実験的）を入れます。`--media` に Windows 7 の ISO を渡します（下の「Windows 7 のシェル」） |
| `--lang ja\|en` | ReactOS のシェルの言語です（既定は今のロケールが日本語なら `ja`、ほかは `en`）。作った prefix はその言語のままなので、変えるときは `.local/prefix-reactos` を移してから実行します |

途中で失敗しても、そのまま実行し直せば、済んだ段階は飛ばします。ビルドしたものはすべて、このチェックアウトの `.local/` に入ります。

## 2. スクリプトがすること

1. パッケージを入れます（Wine のビルドの依存、Xorg、python3-xlib、fcitx5 + Mozc など）。ディスプレイマネージャが無ければ LightDM も入れます。
2. Wine 11.0 を取得し、パッチを当ててビルドします（`.local/wine-install`。4 コアで 1 時間半ほど。ログは `.local/wine-build.log`）。
   ビルドの間は、段階、コンパイルしたファイルの数と割合、残りの目安の時間、出力の最後の数行だけを画面に出します。
3. bridge（ウィンドウマネージャーと代理ウィンドウ）をビルドします。
4. ISO から必要なファイルだけを取り出します（`.local/assets`）。XP の言語（日本語か英語）もここで判断します。
5. XP の言語のロケール（`ja_JP.UTF-8` か `en_US.UTF-8`）を作ります。
6. XP 用の Wine の prefix を作ります（`.local/prefix`）。字体などはその XP に合わせます（下の「英語版の XP」）。
7. `~/.config/win4wine/session.json` を書き、セッション「XP Shell (Wine, X11)」を登録します。
8. 仮想マシンで、画面のメモリーから読み戻すのが遅い仮想のグラフィックカード（QEMU の標準の VGA、Hyper-V、VirtualBox の
   VBoxVGA・VBoxSVGA）なら、X がまずメモリーの中に描くようにします（`/etc/X11/xorg.conf.d/20-win4wine-shadowfb.conf`、
   modesetting の ShadowFB）。窓を動かしたときの X の負担がおよそ半分以下になります。マシンの X のすべてのセッションに効きます。
   `--no-shadowfb` で省けます。virtio-gpu や VMware の仮想のカードでは何もしません。
9. `--greeter` のときは XP のようこそ画面を入れます。
10. `--wayland` のときは labwc と wlroots にパッチを当ててビルドし（`.local/labwc-install`。ログは `.local/labwc-build.log`）、
   セッション「XP Shell (Wine, Wayland)」も登録します。

## 英語版の XP

英語版の XP SP3 の ISO を `--media` に渡すと、英語版の XP に合わせて入れます。オプションは同じです。

- ロケールは `en_US.UTF-8` です。日本語入力（fcitx5）は設定しません（`session.json` に `input_method` を書きません）。
- 字体は英語版の XP と同じです。Luna ではタイトルバーが Trebuchet MS、ほかは Tahoma 8 ポイント、スタートボタンと
  スタートメニューの利用者名が Franklin Gothic Medium、クラシックでは Tahoma 8 ポイントです。Linux のアプリの字体も Tahoma です。
- コマンド プロンプトは英語版の XP と同じ、ラスタ フォントの Terminal（8×12）です。
- ようこそ画面は英語版の XP の文言と字体（Arial、Tahoma、Franklin Gothic Medium）で描きます。
- 字体のファイルは ISO から取り出します（英語版の ISO にある Franklin Gothic、Arial の太字・斜体、Microsoft Sans Serif、Terminal）。
- 一つのマシンで日本語版と英語版を混ぜることは想定していません。ようこそ画面はマシンで一つなので、最後に `--greeter` で入れた方になります。
- 日本語版と英語版以外の XP は、英語版と同じ設定（ロケール `en_US.UTF-8` を含む）で入れます。一切試していないので、`setup.sh` は警告を出します（止まりはしません）。

日本語版から英語版へ（またはその逆に）切り替えるときは、取り出したファイルと prefix を別の場所に移してから、もう一方の ISO で
`setup.sh` を実行し直します。`setup.sh` は、それらが既にあれば作り直さないためです。ビルドした Wine はそのまま使います。
`session.json` のロケールと日本語入力の設定は `setup.sh` が書き換えます。ログオフし、Ctrl+Alt+F2 の文字の画面（または SSH）で:

```sh
cd ~/win4wine
mv .local/assets .local/assets-ja
mv .local/prefix .local/prefix-ja
scripts/setup.sh --media /path/to/English-XP.iso --greeter
```

うまく動いたら、`-ja` を付けたフォルダは消して構いません。

## ReactOS のシェル

XP の ISO が無いときは、ReactOS のシェル（クラシックの見た目）を入れられます。

```sh
scripts/setup.sh --shell reactos --lang ja
```

- ReactOS 0.4.16 のリリース（約 200 MB）を GitHub から取得し、SHA-256 を確かめて、シェルのファイルだけを `.local/assets-reactos` に
  取り出します。取得した zip は `.local/dl` に残ります。
- prefix は `.local/prefix-reactos`、設定は `~/.config/win4wine/reactos-session.json`、セッションは「**ReactOS Shell (Wine, X11)**」です。
  XP のシェルの設定とセッションには触れないので、両方を入れられます（Wine と bridge は共通です）。
- `--greeter` を付けると、ログイン画面が ReactOS のログオンの画面になります。
- `--theme` は `classic`（既定。Windows 2000 風のクラシック）か、ReactOS のテーマ `lautus`、`lunar`、`mizu` です。作った後でも
  `--theme` を付けて実行し直せば変わります。
- `--wayland` を付けると、Wayland のセッション「ReactOS Shell (Wine, Wayland)」も入れます（X11 のセッション以上に実験的です）。
- 詳しくは [docs/reactos.md](docs/reactos.md) にあります。

## Windows 7 のシェル（実験的）

Windows 7 SP1 x64 の ISO があれば、Windows 7 のシェル（Windows 7 ベーシックの見た目）を入れられます。

```sh
scripts/setup.sh --shell win7 --media /path/to/Windows7SP1x64.iso
```

- ISO の `sources/install.wim` から、シェルのファイルと、その言語の MUI ファイルだけを `.local/assets-win7` に取り出します
  （エディションは Professional を使います。無ければ最後のもの）。言語は ISO で決まります。
- prefix は `.local/prefix-win7`、設定は `~/.config/win4wine/win7-session.json`、セッションは「**Windows 7 Shell (Wine, X11)**」です。
  XP や ReactOS のシェルと並べて入れられます（Wine と bridge は共通です）。
- Windows 7 の Aero のカーソルを入れます。`--greeter` を付けると、ログイン画面も Windows 7 のログオン画面になります。
- `--wayland` を付けると、Wayland のセッション「Windows 7 Shell (Wine, Wayland)」も入れます（X11 のセッション以上に実験的です。
  [docs/wayland.md](docs/wayland.md)）。
- `--theme` はまだ使えません。`--dpi` は使えます。
- 確かめたのは日本語版の Windows 7 Professional SP1 です。英語版は、日本語版のメディアの文字（MUI）を英語の言語パック（KB2483139）のものに入れ替えて確かめました（英語版のメディアそのものはまだ試していません）。言語はメディアから判断し、英語版では英語のロケール（`en_US.UTF-8`）で入れます。詳しくは [docs/windows7.md](docs/windows7.md) にあります。

## 3. ログインする

ディスプレイマネージャを再起動するか、マシンを再起動してください。

- `--greeter` のとき: XP のようこそ画面で利用者を選び、パスワードを入れます。
- そうでないとき: ログイン画面でセッション「**XP Shell (Wine, X11)**」（`--wayland` のときは「**XP Shell (Wine, Wayland)**」も選べます）を選びます。

## 使い方

| やりたいこと | 方法 |
|---|---|
| 日本語入力の切り替え | Ctrl+Space または 全角/半角。通知領域のアイコンのクリックでも切り替えられます |
| Linux のアプリを起動 | スタート → すべてのプログラム（名前に「(Linux)」が付いています） |
| Windows のアプリを入れる | 端末で `wine setup.exe`。セッションの `PATH` の先頭にはこの Wine が入っています |
| セッションの外（ssh、ほかのデスクトップ）から Windows のアプリを起動 | `win4wine-wine setup.exe`（`~/.local/bin`）。セッションと同じ prefix・Wine・設定で動き、見た目もセッションと同じになります。シェルを複数入れたときは `--shell xp`・`reactos`・`win7` で選びます。素の `wine` では `~/.wine` と Wine の標準の見た目になります |
| スタートメニュー | Windows キー、Ctrl+Esc |
| ファイル名を指定して実行 / エクスプローラ | Win+R / Win+E |
| ログオフ・終了 | スタート → ログオフ / 終了オプション |

## 設定（`~/.config/win4wine/session.json`）

| キー | 既定 | 意味 |
|---|---|---|
| `wine`, `prefix` | （setup.sh が書きます） | 使う Wine と prefix の絶対パス |
| `locale` | `ja_JP.UTF-8`（英語版の XP では `en_US.UTF-8`） | セッションのロケール |
| `input_method` | `fcitx5`（英語版の XP では無し） | 入力メソッド。省くと起動しません |
| `linux_font` | `MS UI Gothic`（英語版の XP と、英語の ReactOS・Windows 7 のシェルでは `Tahoma`） | Linux のアプリの字体。`null` で変えません |
| `linux_menu` | `true` | Linux のアプリをスタートメニューに入れます |
| `welcome_screen` | `true` | ログイン後とログオフ中に XP の画面（Windows 7 のシェルでは「ようこそ」「ログオフしています」など）を出します |
| `cursor_theme` | `win4wine-xp` | カーソルのテーマ。`null` で使いません |
| `shutdown_command`, `reboot_command` | `systemctl poweroff` / `reboot` | 終了オプションで実行するコマンド |
| `outputs` | （無し） | Wayland のセッションの、出力ごとの設定。例: `{"HDMI-A-1": {"scale": 1.5}, "DP-1": {"scale": 1, "position": "2560,0"}}`（`mode` も書けます。出力の名前は `wlr-randr` で見られます） |
| `shell` | `xp` | `reactos` で ReactOS のシェル（`reactos-session.json` に setup.sh が書きます）、`win7` で Windows 7 のシェル（`win7-session.json`） |
| `primary` | 一番左の出力 | Wayland のセッションで Win32 の主モニターにする出力の名前。XP のデスクトップとタスクバーはここに出ます |
| `composite` | `true` | Wine の窓の中身を X サーバーに覚えさせます（Composite の自動リダイレクト）。窓を動かしたり閉じたりしたとき、下の Wine の窓が描き直すまで黒く見えることがなくなります。`false` で使いません |
| `window_snap` | `false` | `true` で窓を画面の半分に寄せられます（Windows 7 の Aero Snap 風。XP には無い機能です）。Win+←/→ で左右の半分、Win+↑ で最大化、Win+↓ で元に戻す・最小化。タイトルバーを画面の左右の端へドラッグすると半分に、上端へドラッグすると最大化します。最大化した窓は、タイトルバーをドラッグすると元の大きさに戻ります。次にログインしたときから効きます |

## 見た目と文字の大きさを変える

「画面のプロパティ」（デスクトップの右クリック → プロパティ）は、XP のシェルでも ReactOS のシェルでも開けません（その部品を
入れていないため。XP ではエラーになり、ReactOS では何も出ません）。テーマ（見た目）、DPI（文字や画面の部品の大きさ）、フォントのスムージング（ClearType）は `setup.sh` で変えます。セッションの Wine が動いている間は
変えられないので、ログオフしてから次のようにします。

1. スタート → ログオフ で、ログイン画面に戻ります。
2. Ctrl+Alt+F2 で文字の画面に切り替えて同じ利用者でログインします（別のマシンから SSH で入っても構いません）。
3. 次のどれかを実行します。

   ```sh
   cd ~/win4wine
   scripts/setup.sh --media /path/to/WindowsXPSP3.iso --theme classic   # XP の「Windows クラシック」。戻すときは --theme luna
   scripts/setup.sh --media /path/to/WindowsXPSP3.iso --dpi 120          # 文字の大きさ。96 が標準（XP の「通常のサイズ」）
   scripts/setup.sh --media /path/to/WindowsXPSP3.iso --font-smoothing cleartype   # ClearType。戻すときは --font-smoothing standard
   scripts/setup.sh --shell reactos --theme lautus                      # ReactOS のシェル: classic、lautus、lunar、mizu
   ```

4. `exit` で文字の画面からログアウトし、Ctrl+Alt+F7 でログイン画面に戻って、ログインし直します。

- テーマを変えると、XP でテーマを選んだときと同じく壁紙も変わります（クラシックは壁紙なし、luna は Bliss）。
- 済んでいる段階は飛ばすので、2 回目からはすぐ終わります（Wine のパッチが変わっていれば、その分を作り直します）。
- DPI を上げると、XP と同じく文字と寸法が大きくなり、アイコンは 32×32 のままです。Linux のアプリも同じ DPI で文字が大きくなります
  （GTK は 192 以上で部品も 2 倍になります）。
- `--font-smoothing cleartype` は、XP の「画面のフォントの縁を滑らかにする」で「ClearType」を選んだのと同じです（既定は XP と同じ「標準」）。
  XP と同じく、MS UI Gothic の小さい文字（メニューなど、22 ピクセルまで）はビットマップのままで、Tahoma や Arial などの文字と大きい文字が
  ClearType になります。Linux のアプリの文字も、液晶の RGB の並びに合わせて描かれます（X11 のセッション）。

Wayland のセッションでは、Linux のアプリは出力ごとの倍率（`outputs` の `scale`）で描かれ、XP のシェルは DPI で描かれて、
どの出力でもぼけません。DPI は主に使う出力の倍率に合わせてください（倍率 1.5 なら 144）。詳しくは [docs/wayland.md](docs/wayland.md) にあります。

## うまく動かないとき

- セッションのログは `~/.local/state/win4wine/` にあります（前回の分は `*.log.1`）。
- XP のシェルが続けて落ちると、Wine 標準の explorer と xterm に切り替わります。
- 2026-10-13 より前の `setup.sh` は、新しい prefix の見た目の設定（`Setting the theme failed`）で失敗することがありました。
  更新してから `scripts/setup.sh --media ISO --theme luna`（または `classic`）を実行し直してください。
- ようこそ画面が出ないときは `/var/log/lightdm/seat0-greeter.log` を見てください。必要なものが足りないと、通常の LightDM の画面に切り替わります。

## 元に戻す

```sh
greeter/install.sh --remove                     # ようこそ画面をやめる（LightDM の元の画面に戻ります）
sudo rm /usr/share/xsessions/xp-shell.desktop /usr/local/bin/xp-shell-session   # セッションの登録を消す
sudo rm /usr/share/wayland-sessions/xp-shell-wayland.desktop /usr/local/bin/xp-shell-wayland-session   # Wayland のセッションも
sudo rm /usr/share/xsessions/reactos-shell.desktop /usr/local/bin/reactos-shell-session   # ReactOS のシェルのセッションも
sudo rm /usr/share/wayland-sessions/reactos-shell-wayland.desktop /usr/local/bin/reactos-shell-wayland-session
sudo rm /usr/share/xsessions/windows7-shell.desktop /usr/local/bin/windows7-shell-session   # Windows 7 のシェルのセッションも
python3 session/linux_apps.py .local/prefix --wine .local/wine-install/bin/wine --remove   # 作ったスタートメニューの項目を消す
sudo rm -f /etc/X11/xorg.conf.d/20-win4wine-shadowfb.conf   # 仮想マシンの X の設定を消す（次に X を起動したときから）
```

ビルドしたもの、取り出したファイル、prefix は、このチェックアウトの `.local/` を消せば消えます。
スクリプトが入れたパッケージ（LightDM を含みます）と、ディスプレイマネージャの切り替えは元に戻しません。
