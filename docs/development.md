# 開発

使うだけなら、[INSTALL.md](../INSTALL.md) の `scripts/setup.sh` で足ります。この文書は、パッチや bridge を変えて試すときの手順です。

## リポジトリの構成

| 場所 | 中身 |
|---|---|
| `wine/` | 基にする Wine（`upstream.env`）、パッチ（`patches/` と `series`）、ビルド（`build.sh`）、パッチの適用（`patch-state.py`） |
| `bridge-wm/` | X11 の WM（`wm.py`）、Win32 の代理（`proxy.c`）、トレイの仲介（`tray.py`）、調査用の道具（`inspect.c`） |
| `wayland/` | Wayland のセッション: labwc と wlroots の版（`upstream.env`）、パッチ（`patches/`）、ビルド（`build.sh`）、labwc の設定（`labwc/`）、起動（`session.sh`） |
| `session/` | セッションの起動と見張り（`supervisor.py`）、Linux のアプリのスタートメニュー（`linux_apps.py`）、セッションの外から使う `win4wine-wine`（`wine.py`。Wine の環境は `wineenv.py`）、セッションの登録 |
| `prefix/` | prefix の作成（`create.py`）、更新（`stage.py`）、見た目と DPI（`display.py`）、レジストリの設定（registry profile） |
| `extract/` | ISO から必要なファイルだけを取り出す（`extract.py`）、XP の言語の判断（`media.py`） |
| `greeter/` | LightDM の XP のようこそ画面、ログオン・ログオフの画面、XP のカーソル |
| `scripts/` | まとめて入れる（`setup.sh`）、開発用の chroot（`debian.sh`）、ARM64 で Box64 を通す Wine（`box64-wine.sh`）、コミット前の検査 |
| `tests/` | 統合試験と、Wine と実際の XP の両方で動かす公開 API のプローブ（C） |
| `localres/`, `.local/` | ISO、取り出したファイル、prefix、ビルド、ログ、画面。**Git の管理外です** |

## Git の設定

```sh
git config core.hooksPath .githooks
```

コミット前の検査（`scripts/check-staged.py`）は、`localres/`・`.local/` のファイル、PE、レジストリのハイブ、字体、NUL を含む
バイナリを拒否します（`git add -f` でも拒否します）。例外は `docs/images/` の PNG（README のスクリーンショット）だけです。

## chroot での開発環境

ホストで git、sudo、debootstrap が使え、15 GB 以上の空きが要ります。chroot は `.local/debian` に作られ、中の `/work` がこのリポジトリです。

```sh
scripts/debian.sh init
scripts/debian.sh run /bin/bash
```

chroot の中で次のように作ります。

```sh
cd /work
./wine/build.sh > .local/wine-build.log 2>&1    # Wine の取得、パッチ、ビルド
# 進み具合を見るなら: scripts/progress.py .local/wine-build.log Wine -- ./wine/build.sh
./bridge-wm/build.sh                            # .local/bridge（proxy.exe、linux-launch.exe など）
./tests/build.sh                                # プローブ
./extract/extract.py localres/WindowsXPSP3.iso .local/assets
Xvfb :95 -screen 0 1280x800x24 -nolisten tcp > .local/xvfb.log 2>&1 &
export DISPLAY=:95 WINE=/work/.local/wine-install/bin/wine
./prefix/create.py .local/assets .local/prefix-dev --home /home/builder --wine "$WINE"
```

- `wine/build.sh` は `WINE_SOURCE`、`WINE_BUILD`、`WINE_INSTALL`、`JOBS` で場所と並列数を変えられます。
  Wine は新しい WoW64 の方式（`--enable-archs=i386,x86_64`）でビルドするので、i386 のライブラリは要りません。
- パッチを変えたら、**新しいソースとビルドディレクトリで configure から**ビルドして確かめてください。使い回したビルド
  ディレクトリでは古いオブジェクトが残り、漏れ（ヘッダーの登録など）に気づけません。
- `extract.py` と `create.py` は、出力先がすでにあると止まります。やり直すときは別の名前で作ってください。
- `wayland/build.sh` は labwc を取得し、wlroots と libsfdo を subproject として取得してパッチを当て、静的に組み込みます
  （`LABWC_SOURCE`、`LABWC_BUILD`、`LABWC_INSTALL`、`JOBS`）。chroot には `scripts/setup.sh` の `--wayland` のパッケージが
  要ります。入れ子で試すときは、chroot の Xvfb の上で `WLR_BACKENDS=x11 WLR_X11_OUTPUTS=2 WLR_RENDERER=pixman` として
  `wayland/session.sh LABWC --config CONFIG` を動かします（出力の名前は `X11-1`、`X11-2`）。

## パッチ

```sh
python3 wine/patch-state.py SOURCE wine/patches --apply   # 未改変の Wine 11.0 に全部当たるか
```

labwc と wlroots のパッチも同じ道具で確かめられます（`wine/patch-state.py SOURCE wayland/patches/labwc --apply`。
wlroots は `SOURCE/subprojects/wlroots` に `wayland/patches/wlroots` を当てます）。

一覧、並び、書式、opt-in の判定は [patches.md](patches.md) にあります。`.local/wine-upstream` を直接変えたものを成果物にせず、
必ずパッチにしてください。

## 試験

| 試験 | 内容 |
|---|---|
| `tests/wm_integration.py` | WM 単体（Alt+Tab、フォーカス、最小化、Windows キーの受け渡し） |
| `tests/wine_restore.py` | Win32 から最小化して元に戻した Wine の窓が、もう一度表示される（`WINE` と `WINEPREFIX` を渡します） |
| `tests/bridge_integration.py` | WM と proxy と XP のシェル |
| `tests/native_frames.py` | Linux のウィンドウの XP の枠（Luna とクラシック） |
| `tests/xterm_redraw.py`, `tests/wm_latency.py` | 再描画と遅れ |
| `tests/wayland_compositor.py` | Wayland のセッションの labwc を Wine なしで（入れ子、倍率 1.5）: X の空間、作業領域、IPC、枠の対応、重なり順、最大化、最前面。`DISPLAY`（Xvfb）と `LABWC` を渡します |
| `tests/tray_host.py` | トレイの仲介（StatusNotifierItem と XEmbed） |
| `tests/linux_apps.py` | Linux のアプリのスタートメニュー |
| `tests/recovery_integration.py CONFIG.json` | シェルが落ちたときの切り替え |
| `tests/reactos_session.py CONFIG.json` | ReactOS のシェルのセッション: タスクバーとデスクトップ、`explorer.exe` で開くフォルダ（0090）、ログオフ（0024） |
| `tests/reactos_greeter.py ASSETS [OUTDIR]` | ReactOS のログイン画面の配置（英語と日本語）。ASSETS は `extract/reactos.py` が取り出したもの |
| `tests/greeter_layout.py ASSETS`, `tests/cursor_theme.py ASSETS` | ようこそ画面の配置（96・120・144 DPI）、カーソル（32 と 64） |
| `tests/patch_state.py`, `tests/font_*.py`, `tests/workarea.py`, `tests/dpi_settings.py`, `tests/box64_wine.py` | 単体の試験 |
| `tests/xp_language.py [ja=ASSETS] [en=ASSETS]` | 日本語版と英語版の XP で変わるレジストリの設定と、取り出したファイルの言語の判断 |
| `tests/*.c` | 公開 API のプローブ。同じものを Wine と実際の XP で動かして数値を比べます（DPI は `dpi-metrics.c`、`char-widths-dpi.c`、`caption-glyph-dpi.c`、`text-bits-dpi.c`） |

## ウィンドウの中で試す（`xp.sh`）

Arch / CachyOS などで、いま使っているデスクトップ（KDE など）を離れずに XP のセッションを試すための入口です。
システムのファイルには触れません（必要なパッケージは足りないときに表示します）。

```sh
./xp.sh setup /path/to/WindowsXP-SP3.iso   # Wine、bridge、取り出し、prefix（setup.sh と同じ .local/ に作る）
./xp.sh run 1280x800                       # Xephyr の窓の中で本物のセッション（supervisor.py）を動かす
./xp.sh log proxy                          # 動いているセッションのログ（既定は xp-shell）
./xp.sh kill                               # セッションと prefix のプロセスを止める
```

`run` のセッションは自分の D-Bus で動き（tray.py がデスクトップの StatusNotifierWatcher を取らない）、スタートメニューの
「終了」はその窓のセッションを終えるだけです（`shutdown_command` を `true` にします）。`XP_PREFIX`、`XP_LOG`、`XP_DISPLAY`、
`XP_WINEDEBUG` で、別の prefix、ログの場所、X のディスプレイ、Wine のデバッグ チャンネルを選べます。

## 手作業での導入

`setup.sh` を使わずに入れるときは、Wine、bridge、取り出したファイル、prefix を上と同じに作り、`~/.config/win4wine/session.json` を
書いてください（キーは [INSTALL.md](../INSTALL.md#設定configwin4winesessionjson)）。

```sh
./session/install.sh                         # /usr/local/bin/xp-shell-session と xsessions の登録
./session/install.sh --wayland .local/labwc-install/bin/labwc   # 任意: Wayland のセッションも（labwc は wayland/build.sh で）
./greeter/install.sh /absolute/path/assets   # 任意: ようこそ画面
```

`session/install.sh` が入れる起動用のスクリプトはこのチェックアウトを指すので、チェックアウトを移したら入れ直してください。

## 既存の環境を更新する

1. セッションを止め、wineserver が終わったことを確かめます。
2. Wine の install を入れ替えます。
3. `./prefix/stage.py --wine "$WINE" "$WINEPREFIX"` を実行します。wine.inf の更新を見て wineboot、XP の COM の再登録、
   registry profile の適用、XP の DLL の配置を行います。セッションの起動時にも自動で動きます。
4. `bridge-wm/build.sh` で bridge を作り直し、セッションを起動し直します。

見た目と DPI は、セッションを止めてから `prefix/display.py --theme luna|classic --menu xp|classic --dpi N` で変えます（`--theme` は XP のテーマと同じく壁紙も変えます。classic はなし、luna は Bliss）。N は XP と
同じく 96（通常）、120（大きいサイズ）、またはカスタムの 19〜480 です。セッションは同じ DPI を Linux のアプリにも渡します
（`Xft.dpi`、fontconfig、カーソルの大きさ、192 以上では GTK の `GDK_SCALE`。`session/dpi.py`）。ようこそ画面の DPI は
`/etc/win4wine/greeter.json` の `"dpi"` で決めます（XP でもマシン全体の設定です）。

## 既存の XP のハイブから取り込む

`python3-hivex` を入れ、読み取り専用で変換します。名前空間の CLSID と NLS の限られた値だけを扱い、サービス、ドライバ、
ログオン、製品情報は移しません。

```sh
./prefix/hive-to-reg.py --software .../SOFTWARE --system .../SYSTEM --output .local/shell-hive.reg
```
