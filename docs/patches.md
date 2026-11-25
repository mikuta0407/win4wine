# Wine のパッチ

`wine/patches/` には、未改変の Wine 11.0（`wine/upstream.env` の commit）に上から順に当てる 151 本のパッチがあります。
当てるのは `wine/build.sh` で、実際の適用は `wine/patch-state.py` が行います（途中まで当たったソースにも、足りない分だけを当てます）。

番号の付け直しや、以前の番号との対応表は [history/patch-history.md](history/patch-history.md) にあります。
古い記録に出てくるパッチ番号は、書いた時点の番号なので、そちらで読み替えてください。

## opt-in（`WIN4WINE_EXTERNAL_SHELL`）

XP のシェルのための変更は、環境変数 `WIN4WINE_EXTERNAL_SHELL` があるプロセスでだけ効きます。セッション（`session/supervisor.py`）と
prefix の補助ツールがこの変数を設定します。同じ Wine で普通の Windows のアプリを動かしても、挙動は変わりません。

- 判定は 0019 が加える `include/wine/win4wine.h` の `win4wine_external_shell()` に 1 つにまとめています。
  ntdll は Rtl の関数で、wow64.dll（0023）は ntdll の関数で同じ変数を読みます。
- opt-in なしで効くのは、文書化された Win32 の挙動の修正（0001〜0018、0084、0085、0086、0091、0144〜0146）、普通のアプリの見た目と動作を変えない 0025・0026、
  Windows 7 のシェルが呼ぶ API と Wine の修正（0094〜0112）の多くと、版 4 のスタイルでだけ効くテーマの修正（0113〜0119）です。
- 0024 は `WIN4WINE_SESSION_REQUEST` があるときだけ効きます。
- 0090 は、さらに `WIN4WINE_FOLDER_SHELL` があるときだけ効きます（ReactOS のシェルのセッションだけが設定します）。
- ReactOS のシェルのセッションは `WIN4WINE_SHELL=reactos` も設定します。0067 はそのとき、XP のための部品の差し替えをしません。
- 「XP のセッション」と書いたものは、`WIN4WINE_EXTERNAL_SHELL` があって `WIN4WINE_SHELL` が無いとき（XP のシェルのセッション）だけ効きます。ReactOS と Windows 7 のシェルには影響しません。
- Windows 7 のシェルのセッションと見た目（0120〜0137）の多くは、`WIN4WINE_EXTERNAL_SHELL` があって `WIN4WINE_SHELL=win7` のときだけ効きます（どこまでかは表の opt-in の欄にあります。0120 は wineserver が起動したときの環境で判断します）。シェルの種類の判定は、0019 のヘッダーの `win4wine_shell()` 一つにまとめています。
  0122 はそのとき 0079 と 0080 の XP のための置き換えをしません。

## 一覧

下の表の「opt-in」が「あり」のものは、上の環境変数があるときだけ効きます。

### Wine 一般の修正（0001〜0011）

文書化された挙動に合わせる修正で、すべての Wine のアプリに効きます。

| 番号 | 内容 | opt-in |
|---|---|---|
| 0001 | uxtheme: GetThemeSysColor の色番号をテーマの色に対応させる | なし |
| 0002 | uxtheme: GetThemeFont で DC を省略できるようにする | なし |
| 0003 | uxtheme: テーマの字体をシステムに文字の高さ（画素）で適用する | なし |
| 0004 | uxtheme: 空白で区切ったテーマの字体の属性を読む | なし |
| 0005 | uxtheme: 片側だけ無効にしたスクロールバーの矢印を無効の形で描く | なし |
| 0006 | uxtheme: SetWindowTheme で空の文字列を受け付ける | なし |
| 0007 | uxtheme: 共有のテーマ画像の読み込みと転送を 1 スレッドずつにする | なし |
| 0008 | win32u: caption の右クリックを離した位置を WM_NCHITTEST で判定する | なし |
| 0009 | win32u: TrackMouseEvent の追跡で、カーソルの下の窓をすべての窓から探す（上に重なった別の窓へ移ると WM_MOUSELEAVE。以前はデスクトップのアイコン一覧の上のタスクバーにカーソルがあっても追跡が終わらず、Windows 7 のシェルが待機中も毎秒 25〜175 回起きていた） | なし |
| 0010 | wineboot: スタートアップ フォルダの隠しかつ system のファイル（フォルダの名前のための desktop.ini）を起動しない。Wine は隠しファイルごと列挙して desktop.ini をメモ帳で開き、prefix の更新（`wineboot -u`）の後で wineserver が終わらず、Windows 7 のシェルのセッションの準備が時間切れになっていた | なし |
| 0011 | ntdll: FILE_BASIC_INFORMATION の FileAttributes が 0 のときは属性を変えない（文書どおり。SetFileTime などがこう呼ぶ）。Wine は 0 を書き込み、時刻を設定しただけで隠し・system・読み取り専用の属性が消えた。Windows 7 のシェルは known folder の属性を付けた後に時刻を設定するので、Links の印が消えて desktop.ini が読まれなくなっていた | なし |

### XP の部品が呼ぶ API（0012〜0018）

| 番号 | 内容 | opt-in |
|---|---|---|
| 0012 | services: XP の explorer が待つ SCM の準備完了のイベントを出す | なし |
| 0013 | setupapi: ドッキングステーションが無いと答える | なし |
| 0014 | wuaueng: 終了時の更新の確認に「更新なし」と答える | なし |
| 0015 | user32: DestroyReasons を加える | なし |
| 0016 | user32: SetSysColorsTemp（そのプロセスだけの一時的なシステムの色とブラシ。GetSysColor・GetSysColorBrush がそれを返す）。XP の画面のプロパティが配色の見本を描くのに使う（AshesTom） | なし |
| 0017 | winmm: PlaySound のサウンドのパスの環境変数を展開する（XP のサウンドの設定は `%SystemRoot%\media\...`）。XP の起動・ログオフ・エラーなどの音が鳴る（AshesTom） | なし |
| 0018 | kernelbase: GetGeoInfo の GEO_FRIENDLYNAME と GEO_OFFICIALNAME に国の英語名を返す。XP の「地域と言語のオプション」が開く（AshesTom） | なし |

### 外部シェルの基盤（0019〜0024）

| 番号 | 内容 | opt-in |
|---|---|---|
| 0019 | include: opt-in と、セッションのシェルの種類（XP・Windows 7・ReactOS）の判定を加える | — |
| 0020 | explorer: シェルのウィンドウと endpoint を外部のシェルに任せる | あり |
| 0021 | kernelbase: explorer.exe の名前を、名前を変えた XP のシェルに解決する | あり |
| 0022 | ntdll: comctl32 を実行ファイルの隣から読ませる | あり |
| 0023 | wow64: XP のシェルに WOW64 で動いていることを知らせない | あり（XP の explorer だけ） |
| 0024 | user32: ログオフ・終了の要求をセッションに知らせる | `WIN4WINE_SESSION_REQUEST` |

### bridge（WM と proxy）との連携、X11 の表示、日本語入力（0025〜0043）

| 番号 | 内容 | opt-in |
|---|---|---|
| 0025 | winex11: X の窓に Win32 のクラスと HWND を付ける（WM が読む） | なし |
| 0026 | user32: shell hook の登録を proxy のために記録する | なし |
| 0027 | win32u: 別のプロセスの標準のシステムメニューをタスクバーに返す | あり |
| 0028 | server, win32u: 別のプロセスのウィンドウのアイコンをタスクバーが読めるようにする | あり |
| 0029 | win32u: Ctrl+Esc と Windows キーでスタートメニューを開く。Windows キーだけか、ほかのキーと一緒かは、サーバーのキーの反転ビットで見分ける（Win+R の R の離しを別のスレッドが後で処理すると、開いたダイアログが有効にならなかった） | あり |
| 0030 | winex11, win32u: 画面モードの変更なしに作業領域を更新する。作業領域が変わったら、最大化した窓をその大きさに合わせ直す（Windows と同じ。Windows 7 のタスクバーを小さいアイコンと大きいアイコンで切り替えたとき、最大化した窓の下がタスクバーに隠れていた） | あり |
| 0031 | winex11: 最大化の大きさを窓の持ち主が決める | あり |
| 0032 | winex11: 自分で描かないポップアップの下の画面を残す | あり |
| 0033 | winex11: CS_DROPSHADOW の窓の下に XP の影を描く（画面を読めない Xwayland では、透明度つきの黒い窓で描く） | あり |
| 0034 | shell32: 通知領域のアイコンを XP の形式で送る | あり |
| 0035 | winex11: XIC を作る前に指定された変換位置を覚え、on-the-spot の入力でもキャレットの行の下端を入力メソッドに渡す（候補の窓を入力欄の下に出す）。Xlib は on-the-spot の XIC の位置を作るときには受け取らないので、作った直後に設定し直す（以前はメモ帳などの最初の候補の窓が窓の左下に出ていた） | あり |
| 0036 | imm32: 消えた IME の UI の窓を作り直す（XP の「ファイル名を指定して実行」の 2 回目から、変換中の文字が出なかった） | あり |
| 0037 | win32u: X が見えるようにした窓の部分を、すぐ画面に出す（ドラッグした窓の下の窓が、次のメッセージまで黒いままだった） | あり |
| 0038 | win32u: 窓のドラッグを EVENT_SYSTEM_MOVESIZESTART/END と `Win4WineSizeMove` で知らせ、寄せた窓を引き剥がすと元の大きさに戻す。`WIN4WINE_WINDOW_SNAP=1` では最大化した窓もドラッグで元の大きさに戻す（proxy の窓の寄せ。`window_snap` のときだけ使われます） | あり |
| 0039 | winex11: メモリー DC を作るたびに X に送り出さない（GC を作る要求は、それを使う要求と一緒に出ます。テーマの描画はメモリー DC をいくつも作るので、そのたびに X サーバーを起こしていた） | あり |
| 0040 | winex11: X のフォーカスを失ったとき、マウスのキャプチャを持つ窓に、ポインターの位置での外側のクリックを渡す（Windows は前面のアプリの外のクリックをキャプチャの窓に渡し、コンボ ボックスの一覧が閉じる）。アプリ自身のタスクバーのボタンを押すと、開いた一覧が閉じなかった | あり |
| 0041 | riched20: IME の変換中の文字を、選択の色ではなく Windows と同じ下線で表示する（未変換は波線、変換中の文節は太線、ほかの文節は細線。カーソルは変換中の文節の後ろ。Windows 7 の検索欄と画素で同じ） | あり |
| 0042 | winex11: 外部シェルのデスクトップの窓（シェルの窓）は、フォーカスを受けても X で一番上にしない。窓を閉じたときに XP のタスクバーが隠れて、デスクトップが閉じて開き直したように見えていた（AshesTom） | あり |
| 0043 | win32u: XP のセッションの入力言語を HKCU\Keyboard Layout\Preload（と Substitutes）から読む（GetKeyboardLayoutList、既定の配列、ほかの言語への ActivateKeyboardLayout）。XP の「テキスト サービスと入力言語」で入力言語を変えられ、セッションがそれを保つ（キーは session/keyboard.py が同じ値から XKB を設定）。Preload の最初の値は無いときだけ書く（Wine 全体） | あり（XP のセッション） |

### ウィンドウの配置、UI 状態、メニュー、WM_PRINT、壁紙（0044〜0052）

| 番号 | 内容 | opt-in |
|---|---|---|
| 0044 | win32u: 位置を指定しない窓を XP と同じく重ねて置く | あり |
| 0045 | win32u: キーボードの手がかり（下線やフォーカスの枠）の UI 状態を持つ | あり |
| 0046 | win32u: ポップアップメニューを XP と同じく並べて描く | あり |
| 0047 | user32: WM_PRINT の画像に子孫の窓も描く | あり |
| 0048 | user32: ReBar の既定の配置を明示する | あり |
| 0049 | user32: 拡大の壁紙を描く（ReactOS のシェルの「合わせる」「塗りつぶす」も） | あり |
| 0050 | win32u: 「クリック後にメニュー項目をフェードアウトする」を無効と答える（窓の不透明度を出せないので、選んだ項目がログオフの灰色の画面に残った） | あり |
| 0051 | win32u: ほかのプロセスの窓の SetWindowPlacement（窓のスレッドに送って設定させる）。XP と Windows 7 の「デスクトップの表示」（タスクバー、右端のボタン、クイック起動、Win+D）が、最小化した窓を 2 回目に元に戻す。呼んだ側のプロセスが前面なら、戻した窓を前面にする（Windows では呼んだ側が前面の権利で戻す。Wayland のセッションでスタート ボタンが前面に残っていた）（実機で確認） | あり |
| 0052 | user32, win32u: XP の最小化・最大化・元に戻すときのタイトルバーのアニメーション（DrawAnimatedRects の IDANI_CAPTION、タスク バンドとの間を 200 ms で動く）。SPI_GETANIMATION と SPI_SETANIMATION は WindowMetrics\MinAnimate を読み書きする（Windows と同じく既定はオン。Wine 全体）（AshesTom） | あり（XP のセッション） |

### 文字と GDI の画素（0053〜0064）

| 番号 | 内容 | opt-in |
|---|---|---|
| 0053 | win32u: 白黒の文字の送り幅を測った値にする | あり |
| 0054 | user32: DrawText の中央揃え、折り返し、下線を XP に合わせる | あり |
| 0055 | win32u: クリップ中の HALFTONE の座標の対応を保つ | あり |
| 0056 | win32u: TransparentBlt の拡大縮小を XP に合わせる | あり |
| 0057 | user32: クラシックの caption の記号の大きさと位置を XP に合わせる | あり |
| 0058 | user32: アイコンのアルファの乗算を XP に合わせる | あり |
| 0059 | conhost: 2 バイトの文字に 2 升を使う | あり |
| 0060 | win32u: まだ描かれていない最上位の窓から下の画面を見せる | あり |
| 0061 | win32u: system DPI で描き、アイコンの大きさを XP に合わせる | あり |
| 0062 | win32u: XP の ClearType（`FontSmoothingType` が 2）を、XP と同じく描いて測る。fontconfig と X の設定より prefix の設定を優先する、埋め込みビットマップのある大きさ（MS UI Gothic の 22 ピクセルまで）は標準と同じに描く、ほかは横を 6 倍にして白黒で描き、サブピクセルごとに 6 つのサンプルを数える（7 段階。ガンマ 2.2）、字幅は標準と同じ白黒の字幅（ClearType にしても行の長さが変わらない） | あり |
| 0063 | win32u: XP のセッションで、埋め込みビットマップのある大きさ（MS UI Gothic 9pt など）の文字の黒い部分（ABC 幅）をビットマップの点から求める（送り幅はアウトラインのまま）。XP と同じ ABC 幅になり、エディットの余白も XP と同じになる | あり（XP のセッション） |
| 0064 | win32u: XP のセッションの擬似太字（太字の無いフォント）を XP と同じく右に 1 画素太くする（コントロール パネルの「作業する分野を選びます」、スタートメニューの利用者名、ようこそ画面）（AshesTom） | あり（XP のセッション） |

### コントロール（0065〜0068）

| 番号 | 内容 | opt-in |
|---|---|---|
| 0065 | user32: クラシックの押しボタンの理想の大きさを測る | あり |
| 0066 | user32, comctl32: スタートボタンを XP と同じく描き、大きさを決める | あり |
| 0067 | user32, comctl32: XP のシェルのコントロールを Wine のテーマ付きの実装で作る | あり |
| 0068 | comctl32: テーマ付きのチェックボックスとグループボックスの文字の位置を XP に合わせる | あり |

### uxtheme（0069〜0087）

| 番号 | 内容 | opt-in |
|---|---|---|
| 0069 | uxtheme, user32: テーマ付きのウィンドウの枠を描く | あり |
| 0070 | uxtheme: caption の形で窓の形を決める | あり |
| 0071 | uxtheme, user32: Luna の枠を必要な部分だけ描き直す | あり |
| 0072 | user32, uxtheme: caption のヘルプボタンを出して追う | あり |
| 0073 | uxtheme: テーマ画像の拡大縮小、配置、選び方を XP に合わせる（拡大縮小は部品を 32 bpp に 1 回写し、画素を拾う） | あり |
| 0074 | uxtheme: テーマ画像のアルファの乗算を XP に合わせる | あり |
| 0075 | uxtheme: SetWindowTheme で窓ごとのテーマの変更番号を送る | あり |
| 0076 | uxtheme: 日本語の XP の Luna の字体の設定（prefix にあるもの）を使う | あり |
| 0077 | uxtheme: 地域版の msstyles の文字列表にある値を使う | あり |
| 0078 | uxtheme: スタートメニューの利用者名の連続した影を描く | あり |
| 0079 | uxtheme: タスクバーの子のテーマ付きの背景を描く | あり |
| 0080 | uxtheme: 通知領域の時計をテーマで描く | あり |
| 0081 | uxtheme: タスクバーの ReBar のつまみと末尾の余白を描く | あり |
| 0082 | uxtheme: テーマを当てたときのメニューバーの高さを XP と同じ 19（96 DPI）から始める（Luna はクラシックより 1 高い。英語版の Tahoma では 18 のままだった） | あり |
| 0083 | uxtheme, user32: Luna の枠とテーマの部品を、少ない転送で描く。8・24 bpp のテーマ画像を 32 bpp で持つ、0073 で拡大縮小した色キー付きの部品を窓の DC には AlphaBlend 1 回で描く、大きさだけ変わったときに枠を二度描かない、Luna の caption の下にクラシックの caption を描かない（窓の大きさを変えるときに、枠を描く回数がおよそ 2 倍に。画素は変わりません） | あり |
| 0084 | uxtheme: DrawThemeParentBackground で、親の背景を子の窓の位置に描く（範囲は切り抜きにだけ使う。XP と同じ。フォルダの窓のツールバーで、状態の変わったボタンだけを描き直すと、無効になった「移動」「コピー」の背景が黒くなった） | なし |
| 0085 | uxtheme: ClassicGetSystemMetrics、ClassicSystemParametersInfoA/W、ClassicAdjustWindowRectEx、GetThemeSysSize96、GetThemeSysFont96（XP の画面のプロパティの themeui.dll が序数で使う）（AshesTom） | なし |
| 0086 | uxtheme: OpenThemeDataFromFile（動いていないテーマのファイルのクラス）、SetSystemVisualStyle、DrawNCPreview（画面のプロパティの見本。文字は呼んだ themeui.dll の言語で、タイトルはスタイルのタイトルの文字色）、GetThemeParseErrorInfo。XP の画面のプロパティでスタイルを選んで見て、適用できる。XP のセッションでは Wine 自身の Light のスタイルを一覧に出さない（AshesTom） | なし |
| 0087 | uxtheme, user32: 外部シェルで、テーマを変えたときにほかのプロセスもテーマを読み直す（ThemeManager のレジストリの変更を見て、WM_THEMECHANGED で枠を描き直す）。XP の画面のプロパティで適用したスタイルが、タスクバーやフォルダの窓にもすぐ反映される。新しいスタイルを読んだのが WM_THEMECHANGED の後なら、そのプロセスの窓にもう一度送る（クラシックから戻したときのスタートボタンの幅）（AshesTom） | あり |

### Wayland のセッション（0088〜0089）

| 番号 | 内容 | opt-in |
|---|---|---|
| 0088 | winex11: rootless の X サーバー（Xwayland）では、画面の読み取りを各窓の中身から作る（ログオフの灰色の画面） | あり |
| 0089 | win32u: 別のスレッドが前面にした窓を、受け取ったスレッドがその後に自分の窓を前面にしていたら活性化しない（送った時刻を付ける）。Wayland のセッションで、タスクバーのクリックに続けて出したジャンプリストや XP のスタートメニューが、遅れて届いたタスクバーの活性化ですぐ非活性になっていた | あり |

labwc と wlroots のパッチは `wayland/patches/` にあります（[wayland.md](wayland.md)）。書式は Wine のパッチと同じです。

### ReactOS のシェル（0090〜0093）

| 番号 | 内容 | opt-in |
|---|---|---|
| 0090 | explorer: `explorer.exe` で開くフォルダの窓を、外部のシェルの explorer に渡す（`WIN4WINE_FOLDER_SHELL` があるときだけ） | あり |
| 0091 | uxtheme: テーマの余白（MARGINS）の負の値を正しく読む（ReactOS のテーマのスタートボタン。XP の Luna に負の余白は無い） | なし |
| 0092 | user32: SwitchToThisWindow で窓を前面にもする（ReactOS のタスクバー。Wayland のセッションで戻した窓が有効にならなかった） | あり |
| 0093 | user32: ダイアログの部品のリソースの番号を、ReactOS と同じ「#番号」の名前で渡す（ReactOS の Static がバナーとアイコンを読めるように。`WIN4WINE_SHELL=reactos` のときだけ） | あり |

### Windows 7 のシェルが呼ぶ API と Wine の修正（0094〜0112）

Windows 7 の explorer と shell32 などが使う、Wine に無かった関数や Windows と違った挙動の修正です。ほとんどは opt-in なしで効きます。

| 番号 | 内容 | opt-in |
|---|---|---|
| 0094 | dlls: Windows 7 の explorer と shell32 などが import する関数を足す（ntdll の WinSqm*・ShipAssert・RtlSetEnvironmentVar、user32 の CalculatePopupWindowPosition など、kernel32 の CheckElevation など、kernelbase の LoadStringByReference、winsta の WinStationIsSessionRemoteable、64 ビットの oleaut32 の NDR64 の名前、rpcrt4 の NdrStubCall3、gdi32 の CreateBitmapFromDxSurface）。足すだけで、Wine にあった関数の挙動は変わらない（NdrStubCall2 は本体を NdrStubCall3 と共有する）。NdrStubCall3 は DCE の構文で呼び出す（NDR64 は未対応。stub だと、デスクトップのごみ箱をダブルクリックしたときにシェルが落ちた）。PaintMonitor はそのモニターに合わせた壁紙を描く（モニターが 2 つのとき、2 つ目が黒かった）。CreateBitmapFromDxSurface は失敗を返す（DirectX の共有の surface は無い。スタブだと、フォルダの窓をクリックした後でスタートボタンを押すと explorerframe が呼んでシェルが落ちた） | なし |
| 0095 | user32, samlib: Windows 7 のスタートメニューが開くようにする。user32 に RegisterMessagePumpHook・UnregisterMessagePumpHook を足す（フックに user32 の関数の表を渡し、フックが返す関数を使う。ReactOS と同じくスレッドごとに数え、登録したスレッドの GetMessage・PeekMessage・WaitMessage・GetQueueStatus・MsgWaitForMultipleObjectsEx だけがフックを通る。DirectUser はその中で後回しの配置や描画をする。無いと検索欄の部分の作成が失敗してスタートメニュー全体が壊され、フックを通さないとフォルダの窓のアイコンが入力が来るまで出なかった）。samlib の SamConnect は失敗を返し（SAM は無い）、SamCloseHandle と SamFreeMemory は成功を返す | なし |
| 0096 | apphelp: AllowPermLayer（互換モードの層を使ってよいか。ネットワークのパスとリモートのドライブでは FALSE。ReactOS と同じ）。Windows 7 のスタートメニューからプログラムを起動すると呼ばれ、stub ではシェルが落ちた | なし |
| 0097 | ieframe, dsrole, samcli, ntshrui: Windows 7 のフォルダの窓のために。ieframe に ordinal 158・159（SHRestricted2A/W。Windows 7 の shdocvw が転送する）。新しい組み込みの dsrole.dll と samcli.dll（netapi32 への転送）と ntshrui.dll（共有しているフォルダは無い、と答える）。Windows 7 の shell32 と linkinfo が遅延読み込みする | なし |
| 0098 | advapi32: SaferiIsExecutableFileType を足す（Windows 7 の ShellExecute が呼ぶ。無くてファイルを開くとプロセスが終わった） | なし |
| 0099 | xmllite: 16 KB を超える UTF-16 の入力を読む。UTF-16 のときだけ、変換した生のバッファを空けておらず、3 回目の読み込みで同じ 8 KB をもう一度写していた（Windows 7 の DirectUI が UTF-16 で渡すフォルダの窓の UIFILE が途中で壊れ、Win+E の窓が出る前に閉じた）。Wine の xmllite の reader のテスト（2145 件）は通る | なし |
| 0100 | xmllite: XmlReaderProperty_RandomAccess を受け付ける。Windows 7 の shell32 がライブラリ（*.library-ms）を読めず、アイコンが一般のものになり、フォルダーも空だった | なし |
| 0101 | combase: DLL の代理プロセス（dllhost）を、クラスが登録されている側のビット数で起動する。64bit のプログラムは、64bit 側に登録されたクラスでも常に SysWOW64 の 32bit の dllhost を起動していた（Windows 7 のサムネイルのキャッシュのサーバーが読み込めなかった） | なし |
| 0102 | ntdll: MUI ファイルからリソースを探す。RT_MUI を持つ（言語に依存しない）モジュールで見つからないリソースを、`<フォルダ>\<UI の言語>\<ファイル名>.mui`（無ければ en-US）から探す。データファイルとして読み込んだものも同じ（32bit のプロセスが sysnative から読んだ 64bit の DLL も、その横の MUI ファイルを使う）。Windows 7 のシェルの DLL を、リソースを書き込まずにメディアのまま使うため | なし |
| 0103 | server: HKCU\Software を 32bit と 64bit で共有する（Windows と同じ。Classes の下だけが分かれる）。64bit のソフト（Windows 7 の explorer）が HKCU\Software\Wow6432Node を作ると、32bit のプログラムから利用者の設定（Wine の X11 の設定、テーマ）が見えなくなっていた | なし |
| 0104 | comdlg32: ファイルを開く・保存するダイアログ（XP の形）で、ファイルの一覧に Wine のダイアログの字体を設定したあと描き直す。一覧が先に別の字体（アイコンの名前の字体）の行の高さで描かれ、高さの違う prefix（Windows 7 のメイリオ）では、クリックした行の下のファイルが選ばれていた | なし |
| 0105 | comdlg32: Vista の形のダイアログ（IFileDialog）で、既定の操作（ダブルクリック・Enter）が来たフォルダを開き、結果を絶対の ID リストから作る（SHCreateShellItemArrayFromIDLists）。Windows 7 の shell32 の中では（Windows 7 のシェルの「ファイル名を指定して実行」の「参照」）、フォルダに入れず、選んだファイルがデスクトップのものとして返っていた。入力した名前の環境変数を展開し（`%APPDATA%\...`）、ある項目の ID リストはパスから解析して作る（Windows 7 の shell32 は単純な ID リストをファイルのものにするので、フォルダの選択（タスクバーの「新規ツール バー」）が入力したフォルダを断っていた） | なし |
| 0106 | comdlg32: ファイルのダイアログ（古い形）で、作ったビューを UIActivate して表示する（Windows の shell32 のビューは隠れた状態で作られる。Windows 7 の shell32 で一覧が空だった） | なし |
| 0107 | shell32: ほかのシェルの登録だけが名指すものを省く。デスクトップの名前空間の拡張は、サーバーの DLL があり、shell32 の（またはサーバーの無い）ものはこの shell32 が作れるクラスのときだけ並べる（Windows 7 のライブラリやコントロール パネルが、開けない英語の名前で並んでいた）。デスクトップ、コンピューター、ドキュメント、ごみ箱は、LocalizedString が読めなければ shell32 自身の訳した名前にする | なし |
| 0108 | comctl32: ほかの comctl32 のイメージ リストを IImageList で描く（HIMAGELIST はリストの IUnknown。Windows 7 の shell32 のシステムのイメージ リストのアイコンが、Wine の部品に出なかった） | なし |
| 0109 | kernelbase: GetNumberFormat で、先頭の 0 なし（LeadingZero 0）・小数なしの 0 を「0」に、0 に見える負の数を符号なしに（Windows と同じ）。空のフォルダーの詳細ペインが「 個の項目」になっていた | なし |
| 0110 | windowscodecs: 拡大縮小の Fant（覆う範囲の面積で平均）。Windows 7 のシェルがアイコンを元の大きさ以外（詳細ペインなど）に縮めるときに使い、最近傍になっていた | なし |
| 0111 | win32u: SendNotifyMessage で HWND_BROADCAST に送る WM_SETTINGCHANGE と WM_DEVMODECHANGE は、文字列ごと受け取る側のスレッドへ写して送る（Windows 7 と同じ。1 つの窓あてや、SendMessageCallback・PostMessage のブロードキャストは今までどおり ERROR_MESSAGE_SYNC_ONLY）。Windows 7 のタスクバーのプロパティは、設定を書いたあと「TraySettings」をこれで知らせ、タスクバーが読み直す。拒まれていたので、小さいアイコンやボタンの結合がシェルを起動し直すまで変わらなかった | なし |
| 0112 | user32: DefDlgProc の DM_REPOSITION。トップレベルのダイアログを、そのモニターの作業領域に収める（右端は作業領域の右、下端は作業領域の下から 4 px 上まで、そのあと左端と上端は作業領域の内側。Windows 7 の実機で測定。ReactOS も同じ）。Windows 7 のタスクバーのプロパティのボタンがタスクバーの下に隠れていた | なし |

### Windows Vista と 7 のテーマ（版 4 のスタイル）（0113〜0119）

msstyles の形式 4 を読み、版 4 のスタイルの部品を描きます。XP と ReactOS のテーマ（形式 3）では挙動は変わりません。

| 番号 | 内容 | opt-in |
|---|---|---|
| 0113 | uxtheme: Windows Vista と 7 のテーマ（msstyles の形式 4。VMAP、CMAP、VARIANT のバイナリのプロパティ、MUI の文字列表、PNG の画像）を読む。値は形式 3 の ini と同じテキストにして、今のクラス・パーツ・ステートに入れる（Windows 7 Basic の aero.msstyles）。クラスは BCMAP の基底のクラスから足りない値を取る（Tooltip は TooltipStyle から。無いと DirectUI がフォルダの窓を作るのを止めた）。画像（PNG）の色はアルファを掛けた後の値なので、もう一度は掛けない。形式 3（XP、ReactOS）の読み方は変わらない | なし |
| 0114 | uxtheme: SetWindowThemeAttribute（WTA_NONCLIENT）の WTNCA_NODRAWCAPTION と WTNCA_NODRAWICON を覚え、外部のシェルのテーマの枠（0069）がタイトルの文字とアイコンを省く（Windows 7 のフォルダの窓はタイトルバーに何も出さない）。今までは stub だった | なし |
| 0115 | uxtheme: DrawThemeParentBackgroundEx を足す（Windows 7 の comctl32 が呼ぶ） | なし |
| 0116 | win32u, uxtheme: パッド枠（PaddedBorderWidth）を SM_CXFRAME に足し、版 4 のスタイルのキャプション幅とボタンを閉じるボタンの縦横比にする（Windows 7 の枠 8 px、ボタン 31x17） | Windows 7 のスタイル（PaddedBorderWidth があるとき） |
| 0117 | win32u, user32, uxtheme: Windows 7 のテーマ付きメニュー。版 4 のスタイルの Menu クラスで、メニュー バーの背景、押された項目とマウスの下の項目（有効な窓だけ。無効な窓の文字は灰色）、ポップアップの枠・背景・ガター・選んだ項目・チェック・サブメニューの矢印・区切り線を描く（uxtheme の Win4WineMenuTheme を user32 のコールバックで呼ぶ）。項目の高さや文字・ショートカットの位置は Windows 7 SP1 の実機で測った規則。キーボードの手掛かりが切なら、アクセス キーの下線はキーボードでメニューを使う間だけ出す（DrawText の DT_HIDEPREFIX も実装） | Windows 7 のスタイル（ポップアップ メニューの部品があるとき） |
| 0118 | uxtheme: DrawThemeTextEx の DTT_CALLBACK（呼び出し側の関数で描く）と DTT_COMPOSITED（アルファのある面に不透明に描く）。Windows 7 のスタートメニューの検索欄の「プログラムとファイルの検索」が出ていなかった | なし |
| 0119 | uxtheme: Windows 7 の最小パーツサイズ（TS_MIN = 内容余白の合計）。フォルダーウィンドウのアドレスバーと検索欄が 47 px と高すぎた | v4 のスタイル（Windows 7）のときだけ |

### Windows 7 のシェルのセッション（0120〜0128）

| 番号 | 内容 | opt-in |
|---|---|---|
| 0120 | server: ファイルとフォルダに付けた DACL を拡張属性 `user.wine.dacl` に残し、セキュリティを読むときにそれを返す（所有者とグループは今までどおり Unix の所有者から）。Windows 7 の shell32 はごみ箱のフォルダの DACL を自分の付けたものと比べ、違うと「ごみ箱が壊れています」と出す | あり（`WIN4WINE_SHELL=win7`） |
| 0121 | ntdll: ディレクトリの読み取り専用の属性を、Unix のモードは変えずに拡張属性 `user.DOSATTRIB` に残す（Samba と同じ形）。Windows 7 は Links・Favorites・Desktop を読み取り専用にし（known folder の Attributes。最初のセッションで KF_FLAG_INIT のときに付ける）、シェルは読み取り専用か system のフォルダでだけ desktop.ini を読む。Wine はこの属性を捨て、prefix が付けた system の属性まで消えて、お気に入りの「最近表示した場所」が「RecentPlaces」になっていた | あり（`WIN4WINE_SHELL=win7`） |
| 0122 | uxtheme: Windows 7 のタスクバーが自分で通知領域と時計を描く。`WIN4WINE_SHELL=win7` では 0079（DrawThemeParentBackground で通知領域の背景だけを描く）と 0080（時計の差し替え）をしない（Windows 7 の通知領域の背景は半透明で、黒くなり、時刻が二重になった）。BeginBufferedPaint の BP_PAINTPARAMS（BPPF_ERASE、prcExclude、pBlendFunction での AlphaBlend）、BufferedPaintClear、BufferedPaintSetAlpha を文書どおりに | 一部あり（`WIN4WINE_SHELL=win7`） |
| 0123 | win32u, winex11, comctl32: Windows 7 のスタートボタン（タスクバーが持ち主のレイヤードウィンドウ）とスタートメニューのユーザーの写真を描く。半透明の画素を持ち主の窓が出している画素（その surface の写し）と合成し、持ち主の外やまだ描かれていない所ではアルファが 128 未満の画素を抜いてほかは乗算を戻す（元の画像を覚えておき、持ち主が新しく描いたら合成し直す）（合成のマネージャーが無いと縁が黒いギザギザになった）。ホバーで窓が伸びるときは、新しい画像を描いてから大きさを変え、その後で送り出す。窓は WM の管理にせず、大きさを変えたら画像の前に X と同期する（伸びた所が一瞬黒くなった）。0066 のスタートボタンのクラスは、レイヤードの窓には描かない。Wayland のセッション（`WIN4WINE_COMPOSITED`）では合成せず、compositor に任せる | あり（`WIN4WINE_SHELL=win7`） |
| 0124 | shell32: 通知領域のアイコンを Windows 7 のタスクバーの形式で送る（1484 バイト: 0034 の XP の形、32bit のバルーンのアイコン、呼び出したプロセスのモジュールのパス。Windows 7 の shell32 とおとりのタスクバーの窓で測った）。XP の形は拒まれていた | あり（`WIN4WINE_SHELL=win7`） |
| 0125 | dwmapi, combase, ole32: Windows キーとフォルダの窓のために。x64 で DwmpActivateLivePreview（ordinal 113）を S_OK に（合成が無いのでプレビューは無い。stub ではシェルが Windows キーで落ちた）。DwmpRegisterThumbnail（124）は E_NOTIMPL（タスクバーのボタンのクリックで落ちていた）。`WIN4WINE_SHELL=win7` で、フリースレッドのマーシャラーが同じプロセス内では QueryInterface で得られないインターフェースもそのまま渡し、取り出すときもそのまま返す（「ファイル システムのエラー」になっていた）。x64 の ole32 に HWND などの _User*64（NDR64 の名前）を通常の関数として。Windows 7 のシェルのプロセス（w7-explorer.exe）では DwmIsCompositionEnabled を FALSE に（Windows 7 ベーシックと同じ。タスクバーのボタンを指したときの窓の一覧が BasicMenuMode の見た目になる。TRUE だと Aero のガラスの画像で黒かった） | 一部あり（`WIN4WINE_SHELL=win7`） |
| 0126 | ntdll: Windows 7 のシェルのセッションで、Windows 7 の DLL に Windows 7 の comctl32 を渡す。シェル（`w7-explorer.exe`）は横の `C:\w7\comctl32.dll`、ほかのプログラムでは、Wine のものでない DLL が自分のマニフェストの文脈で求めたときに `C:\w7\comctl32.dll`（32bit は `C:\w7\wow64\comctl32.dll`）。プログラム自身は Wine の Common Controls 6 のまま | あり（`WIN4WINE_SHELL=win7`） |
| 0127 | user32: DrawText の DT_PREFIXONLY（下線だけを描く）。Windows 7 の comctl32 のリストビューは項目名を描いたあと下線のためにこれで呼ぶので、スタートメニューの「コントロール パネル」などが二度描きで太く見えていた | あり |
| 0128 | combase・explorer・shell32: `explorer C:\パス` や `start C:\パス` など Wine 側のプログラムから開いたフォルダーを Windows 7 の explorer で開く（LocalServer32 の REG_EXPAND_SZ 展開、/factory サーバーの待機、DelegateExecute の動詞にファイルを渡す）。ライブラリが開いていた | 一部あり（REG_EXPAND_SZ の展開は常に。Windows と同じ） |

### Windows 7 の見た目（0129〜0137）

Windows 7 SP1 の実機（参照用の VM）と画素で比べて合わせたものです。

| 番号 | 内容 | opt-in |
|---|---|---|
| 0129 | winex11: Windows 7 のシェルでは、ドロップ シャドウの色を切り捨てでなく四捨五入する（実機の影と画素ごとに同じ） | `WIN4WINE_SHELL=win7` |
| 0130 | comctl32, user32: Windows 7 の comctl32 6 の細部。エディットの枠（EP_EDITBORDER_*、ホバーとフォーカス）、ドロップダウン リスト（CBS_DROPDOWNLIST）はボタンの形（CP_READONLY）と矢印だけ、ステータス バーの高さは既定のフォントから（24 px）、タブ（文字の位置、最後のタブの幅、クリックでフォーカスを取らない）、プログレス バー（半透明のバーの上に塗り）、トラック バー（つまみ 19 px と幅、チャンネル、目盛り）、グループ ボックス・チェック・ラジオ・リスト ボックス・ステータスの文字の位置、DrawFocusRect の市松模様の位相（いずれも Windows 7 SP1 の実機で測定） | `WIN4WINE_SHELL=win7`（タブのフォーカスは外部シェル全体） |
| 0131 | comctl32: Windows 7 の詳細表示のリスト ビューとヘッダー。行の高さ（フォント + 4）、アイコンと文字の位置、ヘッダーの最小の高さ（テーマの項目の高さ）、最後の項目より右（HP_HEADERITEMRIGHT）、Explorer テーマの選択行とマウスの下の行（LVP_LISTITEM）と列の線（LVP_COLUMNDETAIL）（Windows 7 SP1 の実機で測定） | `WIN4WINE_SHELL=win7` |
| 0132 | user32: Windows 7 のシステム アイコン（IDI_APPLICATION〜IDI_SHIELD）を、prefix がデータとして置く Windows 7 の user32.dll（`C:\w7\res\user32-w7.dll`）から読む。アイコンの縮小は Windows 7 と同じ間引き | `WIN4WINE_SHELL=win7` |
| 0133 | user32, comctl32: Windows 7 のメッセージ ボックス（白地と下のボタン帯、アイコン・文字・右寄せのボタンの配置）、既定のボタンの脈動とプログレス バーの光（どちらも 2 秒周期、Windows 7 SP1 の実機で測定） | `WIN4WINE_SHELL=win7` |
| 0134 | win32u: Windows 7 の ClearType。XP と同じ 7 段階の標本化で、ガンマをかけずに混ぜる（白地の黒文字が 0, 43, 85, 128, 170, 212, 255 だけになる。実機で確認） | `WIN4WINE_SHELL=win7` |
| 0135 | win32u: Windows 7 のリンク先フォント（Tahoma の中の日本語など）の大きさと字形。基のフォントの em から決め、em 11・13 は 12・15（実機で測定）。埋め込みビットマップのある大きさはそのビットマップで描く | `WIN4WINE_SHELL=win7` |
| 0136 | riched20: Windows 7 の検索欄（スタートメニュー、フォルダーウィンドウ。windowless の RichEdit）の文字。ホストが後から知らせる既定の書式（メイリオ 9pt）を使い（外部シェル全体）、複雑な文字（アラビア文字など）の無い段落を GDI で測って描き、フォントを DEFAULT_CHARSET で作る（英字はそのフォント、日本語はフォントのリンク。実機と同じ字形と位置）。日本語が四角や重なりになっていた | 一部あり（`WIN4WINE_SHELL=win7`） |
| 0137 | comdlg32: Windows 7 のシェルのセッションの項目ダイアログ（IFileDialog）を Windows 7 の形に。上の段（戻る・進む、パンくずのアドレス、更新、検索）を新しい部品（navbar7.c）がテーマの部品と explorerframe.dll の画像・文字列で描く。640x478、メッセージ用のフォント、詳細・プレビュー ペインなし、サイズ グリップ、フォルダーの選択では「フォルダー:」「フォルダーの選択」。検索はフォルダー内の名前での絞り込み（Windows 7 は索引を検索する） | あり（`WIN4WINE_SHELL=win7`） |

### XP と ReactOS のシェルの細部（0138〜0151）

XP と ReactOS のシェルのための変更のうち、Windows 7 のシェルのために加えた仕組みを使うものです（0117 のテーマ付きのメニュー、0119 の TS_MIN、
0126 の comctl32 の切り替え、0130 と 0131 のコントロールの判定、0132 のシステム アイコンの読み込み、0133 のメッセージ ボックスの配置）。
0144〜0150 は AshesTom さんのフォーク（XP の画面のプロパティ、Internet Explorer 6 など）から入れたもので、Windows 7 のための
パッチが変えた所（apphelp の関数の表、uxtheme の関数の表とタイトルバー、comctl32 の切り替え）に触れるので、ここに置いています。

| 番号 | 内容 | opt-in |
|---|---|---|
| 0138 | win32u: XP のメニュー バー。項目はバーの上端から（19 px）、最後の行は COLOR_MENU（Luna では白）。無効になった窓（メッセージ ボックスの持ち主など）のメニュー バーは灰色 | あり（XP のセッション） |
| 0139 | comctl32: XP の Common Controls 6（xpcmp.exe で実機と比較）。プログレス バーのブロック、ステータス バーの高さ（24 px）と文字位置、ヘッダーの高さ（作成時の値を保つ）と残りの部分（部品 0）、リスト ビュー・リスト ボックスの文字位置、グループ ボックス、チェック・ラジオの見出し、ドロップダウンのボタン、トラック バーの溝、タブ | あり（XP のセッション） |
| 0140 | uxtheme: XP のテーマでも TS_MIN を内容の余白から、アイコンの無いキャプションの文字を 2 px 内側に | あり（XP のセッション） |
| 0141 | user32: XP のシステム アイコン（IDI_APPLICATION など）を XP の user32.dll（prefix がデータとして `C:\xp\res\user32-xp.dll` に置く）から読み、縮小は画素を拾う | あり（XP のセッション） |
| 0142 | user32: XP のメッセージ ボックスの配置（画素で決めてダイアログ単位に丸める。実機の 30 通りと一致）と、DrawFocusRect の市松模様（DC の文字色と背景色との XOR） | あり（XP のセッション） |
| 0143 | ntdll: ReactOS のシェル（ros-explorer.exe）が横の `C:\ros\comctl32.dll`（ReactOS の Common Controls 6）を使う（0126 と同じ仕組み）。ほかのプログラムは Wine のアセンブリのまま（以前は置き換えていて、32bit のアプリのボタンなどが作られなかった） | あり（`WIN4WINE_SHELL=reactos`） |
| 0144 | apphelp, advapi32: ApphelpCheckExe（どのプログラムも許す）、SaferGetLevelInformation（どのレベルも完全に信頼）、SaferRecordEventLogEntry。XP の shell32 がプログラムやコントロール パネルの項目を起動する前に呼ぶ（AshesTom） | なし |
| 0145 | uxtheme: XP と同じ序数で名前付きの関数を公開する（GetCurrentThemeName が 42、DrawThemeBackground が 6 など。XP の画面のプロパティの「デザイン」のページが序数で探す）（AshesTom） | なし |
| 0146 | uxtheme: IsThemeActiveByPolicy（序数 73。グループ ポリシーの SetVisualStyle があるか）。XP の画面のプロパティで「ウィンドウとボタン」を選べる（AshesTom） | なし |
| 0147 | uxtheme, win32u: タイトルバーのアイコンは小さいアイコンを先に使う（XP と同じく、そのプログラムの 16x16 の絵。大きいアイコンを縮めない）。大きいアイコンから作る小さいアイコンはリソースの 16x16 から（LR_COPYFROMRESOURCE。Wine 全体）（AshesTom） | 一部あり |
| 0148 | user32: 画面のプロパティ（rundll32 の desk.cpl と themeui.dll）のように、XP の comctl32 を実行ファイルの横から読んだプロセスでも、外部シェルのテーマ付きのボタンなどを使う（AshesTom） | あり |
| 0149 | ntdll: XP のセッションで、実行ファイルの横に XP の comctl32.dll（native。システムのディレクトリは除く）があるときは comctl32 の SxS のリダイレクトを使わず、その XP の Common Controls 6 だけを使う（画面のプロパティのボタンがクラシックになっていた。ReactOS のシェルは 0143）（AshesTom） | あり（XP のセッション） |
| 0150 | user32: XP のセッションで、XP の comctl32 を横に置いたプロセスは、コモン コントロールのクラス名を版つきにしない（Internet Explorer 6 のメニュー バー、ツール バー、アドレス バー、ステータス バーが作られなかった）（AshesTom） | あり（XP のセッション） |
| 0151 | user32: PrivateExtractIconsW で 2 つの大きさ（32 と 16、48 と 16）を一度に取るとき、それぞれの大きさのアイコンをその大きさに選んだ画像から作る（16x16 が 32x32・48x48 の縮小になり、縁のアルファが無かった。XP のクイック起動とシステムのイメージ リストのアイコン。実機と 0 画素差。Wine 全体） | なし |

## 並び順の考え方

まとまりは「opt-in の要らない修正 → XP の部品が呼ぶ API → 外部シェルの基盤 → bridge との連携 → ウィンドウ → 文字と画素 →
コントロール → uxtheme → Wayland のセッション → ReactOS のシェル → Windows 7 のシェル（API と Wine の修正 → 版 4 のテーマ →
セッション → 見た目）→ Windows 7 のための仕組みを使う XP と ReactOS の細部」の順です。同じまとまりの中では、後のパッチが前のパッチのコードを使う順にしてあります
（例: 0070〜0072 は 0069 の枠の描画を前提にしています）。新しいパッチもまとまりに合う位置に入れ、末尾に溜めません。

## 書式

- ファイル名は `NNNN-<DLL>-[external-][win7-]<内容>.patch` です。`external` は opt-in のときだけ効くもの、`win7` は Windows 7 の
  シェルのためのもの（`external-win7` は `WIN4WINE_SHELL=win7` のときだけ効くもの）に付けます。いくつもの DLL にまたがるものは `dlls` にします。
- 先頭は `From:` と `Subject: [PATCH] <DLL>: <内容>` です。本文は英語で、次の項目のうち必要なものを書きます。
  - `Purpose:` 目的
  - `XP behavior:` / `Windows behavior:` 実際の XP や Windows 7（参照用の VM で、公開 API と画面）で測った挙動
  - `Wine before:` 変更前の Wine の挙動と、その原因
  - `Change:` 変更の内容
  - `Evidence:` 根拠になる試験（`tests/`）や測定
  - `Scope:` 効く範囲（opt-in の有無、対象のウィンドウやクラス）
  - `Old patches:` 最初の整理（2026-10-10）より前の番号
- 本文の後に `---` と diffstat、`git diff` の形の差分を置きます。

## パッチを足すとき

- まとまりに合う位置に入れ、番号を振り直します。既存のパッチを直す変更は、そのパッチに含めます。
- XP のシェルのための挙動は `win4wine_external_shell()` で限ります。文書化された Win32 の挙動の修正で、普通の Wine の
  アプリにも正しいものは、opt-in にしません（0001〜0015 と同じ扱い）。
- 未改変の Wine 11.0 に、`python3 wine/patch-state.py <ソース> wine/patches --apply` で全部当たることを確かめます。
- WoW64 のビルドでは PE のモジュールが i386 と x86_64 の両方になります。プロセスの間で受け渡す構造体は、handle の幅と
  大きさを固定してください（0034）。Unix 側の浮動小数点の結果は、32bit と 64bit で同じ丸めになるようにしてください（0033）。
- 新しいファイルを加えたときや、並びを整理した後は、新しいソースとビルドディレクトリで configure からビルドして確かめます。
  使い回したビルドディレクトリでは、Makefile の一覧の漏れや古いオブジェクトに気づけません。
