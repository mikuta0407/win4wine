# 調査と判断の記録

開発の途中で行った調査と、その時点の判断を、行った順に書いた記録です。書いた時点の内容と文体のままにしてあり、
後の変更で事情が変わった項目もあります。今の設計の要点は [../design.md](../design.md) に、
仕組みは [../architecture.md](../architecture.md) にまとめています。

- 「段階 N」は開発の作業の区切りです（2026-10 の段階 1〜10）。
- 「調査 1」〜「調査 21」と「22」〜「40」の節のパッチ番号は、2026-10-10 に整理する前の旧番号です。
  それ以降の節は、書いた時点の番号です。今の番号への読み替えは [patch-history.md](patch-history.md) にあります。
- 文中の `.local/` のログや画像は開発者の手元にだけあり、リポジトリには入っていません。

| DLL / EXE | 初期選択 | 理由 |
|---|---|---|
| explorer.exe | native XP | 目的のタスクバー・スタート・デスクトップの実体 |
| browseui | native XP | builtin の ordinal 107 が起動直後に未実装中断。単純な成功応答ではフォルダ構築を代替できない |
| shdocvw | native XP | browseui と同世代のフォルダホスト・内部インターフェースを使う |
| shell32 | native XP | browseui/shdocvw と同じ XP の名前空間と内部 ordinal の組を保つ |
| browselc, shdoclc | native XP の資源 | 同じ ISO の日本語メニュー・文字・アイコン。コードの追加取得や IE renderer 導入はしない |
| shlwapi | native XP | shell32/browseui の XP 固有 ordinal 依存を同世代で解決する |
| comctl32 | XP shell のみ native v6 | SP3 の 6.0.2600.5512 を C:\xp に配置。Start の Button は自作 Wine controls の別名モジュールで分離。通常アプリは builtin |
| uxtheme | builtin | ローカル Luna の msstyles を読む。Wine 側の描画・フォント処理を修正し、native のテーマサービスは導入しない |
| kernel32, ntdll, user32, gdi32, ole32, advapi32 など | builtin | Linux/Wine の基盤。XP のカーネルやサービスを取り込まない |
| mshtml, mscoree | disabled | IE/CLR は対象外。Mono/Gecko の自動取得を止める |

## 調査 1: builtin shell family

Debian 13 chroot、パッケージ Wine 10.0、XP 日本語 SP3 x86、Xvfb 1280×800。
`WINEDEBUG=+seh,+loaddll` で BROWSEUI.dll ordinal 107 の `EXCEPTION_WINE_STUB` を確認。
**判断: native に差し替える。** 同じ ISO の shell family を使用する。
生ログ: `.local/explorer-builtin.log`（ローカルのみ）。

## 調査 2: native shell family の無表示終了

`+relay,+seh` で native explorer 起動中の `GetShellWindow` が既に非 NULL であることを確認。
Wine の `programs/explorer/desktop.c` が desktop manager に SetShellWindow する実装と照合。
**判断: Wine に opt-in shim を足す。** builtin desktop manager 自体は保持し、
`WIN4WINE_EXTERNAL_SHELL=1` の場合だけ shell HWND 登録を譲る。
この観測だけで native explorer の終了原因が完全に解消したとは判断しない。パッチ後の再試験が必要。
生ログ: `.local/explorer-relay.log`。パッチ: `0003-explorer-external-shell.patch`。

## 調査 3: shell hook

upstream Wine 10.0 の RegisterShellHookWindow / DeregisterShellHookWindow は stub。
**判断: Wine に限定的な登録 shim、独立 bridge に配信を足す。** 実装制約は architecture.md に記載。

未試験の DLL 選択は動作保証ではない。Luna/native uxtheme、COM 登録、フォルダ内部インターフェースは実測で追記する。

## 調査 4: Debian 13 toolchain と Wine 10.0

ソース版の初回 wineboot が `LdrResolveDelayLoadedAPI` の IAT 書き込みで access violation。
Wine 自身の PE のセクションヘッダを確認し、binutils 2.44 が `.idata` を read-only にする変更と照合した。
**判断: Wine に既知のビルド修正をバックポート。** 遅延 import の書換領域を writable data に配置する。
[Debian Wine 修正](https://sources.debian.org/patches/wine/10.0~repack-12/fixes/binutils2.44.patch/) と
[binutils の説明](https://sourceware.org/pipermail/binutils/2025-April/140559.html) を参照。
MS バイナリではなく Wine 自身のソースと PE ヘッダのみを調査した。
パッチは `0004-winebuild-binutils244-delay-imports.patch`。生ログは `.local/source-boot-debug.log`。
この問題があるため、パッケージ Wine に自作 explorer モジュールだけを混ぜた途中試験は到達判定に使用しない。

## Override の隔離

XP explorer をローカルで `xp-explorer.exe` として配置し、AppDefaults でそのプロセスにだけ native shell family を適用する。
Wine 自身の explorer/desktop manager は builtin のまま。セッション全体へ native shell32 を指定すると、
管理プロセスや復旧経路まで XP の DLL に依存するため。元ファイルの内容は変更しない。

## 調査 5: サービス初期化待ちとドッキング API

ソース版で `+relay,+seh` を取得。XP explorer が `Global\ScmCreatedEvent` を
待つが Wine の services はイベントを作らず、起動が約 60 秒止まる。
**判断: Wine に shim を足す。** RPC/サービス DB 初期化後にサービス管理プロセスが
イベントを作成・通知し、終了まで保持する（0005）。
その先で `CM_Is_Dock_Station_Present` の stub exception を確認。
**判断: Wine に shim を足す。** Windows ドックを公開しない環境なので FALSE と成功を返す（0006）。
生ログ: `.local/xp-controls-relay.log`、`.local/wine-dock-build.log`。

## 調査 6: COM 登録の不足

BandSite / ShellBrowser 等の生成が `REGDB_E_CLASSNOTREG` で失敗。
**判断: native を使い、公開 CLSID の最小登録を生成する。**
`prefix/registry.py` に公開 manifest のクラスと、起動ログに現れたクラスを登録。
後者の提供 DLL は利用者の DLL に対する公開 API `DllGetClassObject` で確認した。
診断用 `prefix/class-probe.c` はクラスファクトリを取得・解放するだけで、コードを解析しない。
Wine 10.0 の HKCR 読み出しでは HKCU\Software\Classes に追加した登録が見えなかったため、
専用 prefix 内の HKCR に生成する。任意の実環境ハイブの丸ごと移植はしない。
生ログ: `.local/class-providers.log`、`.local/xp-menu-classes.log`。

## 調査 7: コントロールと実行ファイル名

builtin comctl32 には XP 内部 toolbar メッセージの不足があり、native shell と組み合わせた試験で例外が出た。
native v5 では例外が減ったが表示寸法は崩れた。native v6 を SxS manifest で
Button にも割り当てる試験は native v6 内の access violation で失敗した。
**暫定判断: native v6 を実行ファイル隣に置き、Button は Wine 標準のままクラシック表示する。**
SP3 の 6.0.2600.5512 を優先し、正確な SxS Button 選択用の実験 manifest は自動導入しない。
表の comctl32 の初期選択から変更した。全アプリへの native 指定は行わない。

名前を分離した shell に対する `GetModuleHandleW("EXPLORER.EXE")` の失敗も観測したため、
外部シェル opt-in かつ当該プロセスにだけ元名を主モジュールに解決するパッチ 0007 を追加。
これだけでは寸法不良は直らなかった。

追加の relay で Start の `BCM_GETIDEALSIZE` が FALSE を返し SIZE がゼロのままになることを確認。
**判断: Wine に限定 shim を足す。** 0008 は標準 pushbutton の文字寸法と DPI に応じた余白を返す。
image-list 描画や Windows と同一の寸法を保証する実装ではない。
生ログ: `.local/xp-sizing-relay.log`、`.local/xp-button-size.log`。

## 調査 8: ショートカットと子ウィンドウの購読

Classic メニューを `NoSimpleStartMenu=1` で選択し、必要な MenuBand / MenuDeskBar / MenuBandSite
のクラスファクトリ提供元を公開 API で確認して登録した。
[ポリシーの公開資料](https://learn.microsoft.com/en-us/windows/client-management/mdm/policy-csp-admx-startmenu) を参照。
ショートカットの列挙で `LINKINFO.dll.IsValidLinkInfo` の未実装中断が発生。
**判断: native に差し替える。** ローカル ISO の linkinfo.dll を抽出対象に追加した。
生ログ `.local/xp-classic-menu.log`、`.local/xp-linkinfo.log`。

XP は子ウィンドウ MSTaskSwWClass で RegisterShellHookWindow する。
bridge の EnumWindows のみの配信では届かないため、子孫も購読検索の対象にした。
子ウィンドウ購読に変更した統合試験と、実 XP のメモ帳 / xterm のタスクボタン表示を確認。
生ログ `.local/bridge-child-integration.log`。

## 調査 9: フォルダの shell endpoint と実行関連付け

native フォルダ生成は COM 登録追加だけではハングした。Wine の desktop manager が
ShellDDE、ShellWindows、隠し Shell_TrayWnd を同時に所有していたため、外部シェル時だけ
これらを作らないパッチ 0009 を追加した。**判断: Wine に opt-in shim を足す。**
native XP が名前空間・フォルダの endpoint を所有し、Wine は X11/clipboard を維持する。
新規 prefix で H: とサブフォルダの閲覧を確認した。

native ShellExecuteEx は `.exe` の関連付けがないと ERROR_NO_ASSOCIATION (1155) を返した。
**判断: 最小レジストリを自前生成する。** `.exe/.com` と exefile/open を専用 HKCR に登録。
メモ帳のメニュー起動で確認した。

## 調査 10: Linux の起動とフォーカス

`start /unix /usr/bin/xterm` では Windows 形式の argv[0] が渡され、起動した xterm が
WM_DELETE_WINDOW で終了しないケースを実測した。**判断: Linux 側の起動を仲介する。**
ショートカットを `start /unix /usr/bin/env xterm` とし、終了要求への応答を確認した。
Wine や Microsoft バイナリのコード解析は行わず、Wine と xterm の公開ソースを照合した。
ログ `.local/xterm-wine-close-check.py`、`.local/final-m3-native-operations.log`。

proxy が X11 の active 属性だけでフォーカスを取り返すと XP のメニュー操作を妨げた。
WM は実際の X input focus の所有元も確認し、proxy は遷移時だけ Win32 foreground を更新する。
PROGMAN のクラス名は大小文字を区別せず処理する。

## 調査 11: 復旧の隔離

XP 用 HKCR を持つ prefix では builtin explorer も表示前に停止した。一方、同じ Wine の
クリーン prefix では Linux ホームのフォルダを表示できた。
**判断: 復旧のレジストリも分離する。** 専用 prefix 内の `recovery/` を builtin のみで作成する。
XP のファイルや COM 登録に依存せず、ネイティブ xterm も同時に開く。

## 調査 12: Luna と HiDPI

Wine builtin uxtheme は利用者の Luna msstyles を読み、IsThemeActive / IsAppThemed が TRUE、
GetCurrentThemeName が該当パス、Taskbar のテーマ part size が成功することを確認した。
`+uxtheme` ログにも Blue_TaskbarBackground 等の読込を記録。
ただし native XP comctl と Wine 標準 Button の組では、背景・Start ボタンの描画が揃わない。
**初回の判断: クラシック表示を基準とし、Luna の描画修正を後続調査へ回す。**
後続の描画・フォント調査は調査17以降を参照。
native uxtheme や XP の Themes サービスを追加して動作保証した扱いにはしない。
クラシックの 144/192 DPI では Start / Programs の文字と配置、200% の Linux 起動を実測。
DPI 非対応 XP アプリの拡大なので画質の改善は別の課題とする。

## 調査 13: Wine 更新後の native profile

Wine の prefix 自動更新は DLL と COM 登録を入れ替えるため、先に native DLL を配置するだけでは
次の Wine ビルドで壊れる。**判断: 更新と native profile の再配置を順序付ける。**
wine.inf と `.update-timestamp` を照合し、不一致時のみ builtin wineboot を完了させ、
自前 COM 登録を再適用し、専用 wineserver を終了してから native DLL を atomic 配置する。
VM で timestamp 不一致を作り、同じセッションから XP Shell / Start が再度動くことを確認した。

## 調査 14: フォルダの資源と ReBar 配置

公開 API trace の LoadMenuW / LoadStringW が資源用 module NULL のまま失敗していた。
同じ ISO の `browselc.dll` / `shdoclc.dll` を無改変で加えると、日本語メニュー・
ツールバーの文字・初期ウィンドウ名・アイコンが表示された。
**判断: ローカル資源 DLL を抽出・専用 prefix へ配置する。**
既存 prefix にも AppDefaults の native 選択と全体の builtin 選択を適用する。
IE/CLR の disabled 方針は変えない。

アドレス欄は別問題で、親 WorkerW の上端から ReBar が32pxずれていた。
自作の公開 CreateWindowExW / GetWindowRect / MapWindowPoints probe では、
native SP3 v6 の配置 bits=0 で初期高さ36px分移動し、明示 CCS_TOP では y=0 となる。
その後の native browseui の SWP_NOMOVE がずれを保持する。
**判断: 外部シェルの名前付き子 ReBar にだけ、未指定時の CCS_TOP を明示する（0011）。**
明示した CCS_NOMOVEY 等は変えない。実フォルダと native バンドの試験で確認した。
[公開 common-control styles](https://learn.microsoft.com/en-us/windows/win32/controls/common-control-styles) と
Wine の ReBar ソースを参照。Microsoft の実装コードは解析していない。

## 調査 15: タスクボタンの左クリック

実 XP の WM_COMMAND 処理が、別プロセスへの GetSystemMenu の未対応で止まっていた。
**判断: 外部シェル opt-in の標準システムメニュー snapshot（0010）。**
Wine のメニューはプロセス内のデータなので、本物の他プロセスメニューを共有した扱いにはしない。
最大2048個をロック付きで保持し、消失した HWND を回収する。
WS_MINIMIZEBOX / WS_MAXIMIZEBOX を反映し、revert は呼出側のコピーだけを破棄する。
アプリ独自の項目・無効化は未対応。通常の Wine には適用しない。
VM のメモ帳と xterm の実ボタンで左クリック最小化・復元を実測した。

## 調査 16: 通常 Start と再描画

通常の XP Start のため、shell32 が公開 factory を提供する
`{D912F8CF-0396-4915-884E-FB425D32943B}` を追加登録した。
profile version を Wine の timestamp と別に保存し、既存 prefix の登録も更新する。
`NoSimpleStartMenu=0` だけでは選択されず、公開
[SSF_STARTPANELON](https://learn.microsoft.com/ja-jp/windows/win32/shell/ssf-constants) の設定・読戻しが必要だった。
`prefix/menu-settings.c` が専用 helper の native shell32 だけを使って設定する。
この時点では右側の一覧を表示するが、ユーザー欄・左側・下部が黒かった。
後続調査17で保存画像の WM_PRINT 不足を特定した。
SxS native Button は例外が再発し、v5 controls はアイコン等を欠くため採用しない。

xterm の描画用子ウィンドウに Expose を配信することで、文字バッファを保った画面消失から
入力なしで復帰することを Xvfb / VM で確認した。WM のフォーカス・サイズ変更に限定し、
Wine の HWND があるウィンドウには適用しない。定期的な画面消去やキー入力で隠さない。
VGA/Xorg の元のイベント不足の原因は未特定で、全 Linux アプリの描画保証ではない。


## 調査 17: 通常 Start の保存画像と子ウィンドウ

通常 Start を開く公開 API trace では、XP が `DV2ControlHost` に
`WM_PRINT` / `PRF_CHILDREN | PRF_OWNED | PRF_NONCLIENT | PRF_CLIENT | PRF_ERASEBKGND`
を送り、得た bitmap をメニュー全体へ転送していた。
Wine 10.0 の `dlls/win32u/defwnd.c` は子・所有・非クライアントの flags を未対応として無視する。
実際の trace も親への `WM_ERASEBKGND` / `WM_PRINTCLIENT` だけで、子への配信がなかった。
この保存画像が既に描いた子を覆い、一覧の一部だけが後から再描画されていた。
**判断: 外部シェル opt-in の Wine 側で WM_PRINT の子・所有ウィンドウと枠を描く（0012）。**
子は背面から描き、座標と親の clip を反映し、呼出元 DC の状態を保存・復元する。
Microsoft の window procedure や機械語を解析・変更した結果ではない。
[公開 WM_PRINT 契約](https://learn.microsoft.com/en-us/windows/win32/gdi/wm-print) と
Wine の公開ソースを照合した。

自作 `tests/print-window.c` は MS DLL を使わず、子・孫・所有ウィンドウ、
隠れたウィンドウ、境界からはみ出す子、重なり、枠、DC の viewport / clip の維持を検査する。
修正前の失敗 `.local/start-print-before-test.log`、修正後の成功
`.local/start-print-after-test.log` を記録した。

## 調査 18: Luna のフォントと owner-draw の clip

Luna のユーザー名が途中で切れ、テーマの LOGFONT の高さが0になっていた。
公開 `GetThemeFont` は NULL DC を許すが、Wine の `MSSTYLES_GetPropertyFont` に
そのまま NULL を渡すと `GetDeviceCaps(NULL, LOGPIXELSY)` が0になり、ポイント数も0へ変換される。
**判断: builtin uxtheme の GetThemeFont に画面 DC の既定値を補う（0015）。**
既存 GetThemeSysFont と同じ方法で一時 DC を取得・解放し、明示 DC の挙動は変えない。
[公開 GetThemeFont 契約](https://learn.microsoft.com/en-us/windows/win32/api/uxtheme/nf-uxtheme-getthemefont) を参照。
`tests/theme-font.c` はローカル Luna の StartPanel の2種類のフォントについて、
明示 DC と NULL DC の高さ・名前・weight / italic が一致することを確認する。
修正前は高さ -19 / -11 に対し NULL だけ0、修正後は成功。
ログ `.local/theme-font-before-test.log` / `theme-font-after-test.log`。
実画面でもユーザー名全体の表示を確認した（`.local/luna-font-fixed.png`）。

「すべてのプログラム」は owner-draw の WM_DRAWITEM も DrawTextW も呼ばれていたが、
描画時の clip が空だった。親の保存画像用 DC は viewport が (7,377) / (8,408) に移動している。
Wine の `set_control_clipping` が論理 client rectangle を再度 DPtoLP し、
無関係な負の位置へずらした rectangle と交差させていた。
**判断: 外部シェル opt-in かつ MM_TEXT では論理 rectangle を直接 clip に使う（0017）。**
通常 Wine と別の mapping mode の既存変換は維持する。
自作試験は builtin owner-draw Button / Static の保存画像も検査する。
修正後の実 DrawText trace では clip が (0,0)-(192,30) / (0,0)-(174,24) となり、
文字・font・rectangle が有効なまま描画できる。
診断のための Wine text.c の追加 trace は取り除き、クリーンな再ビルドでも
`.local/start-clean-public-tests.log` の公開 API 試験が成功した。

## 調査 19: All Programs の COM 登録とローカルフォント

通常 Start の All Programs が要求する
`{3F6953F0-5359-47FC-BD99-9F2CB95A62FD}` の factory を、同じローカル ISO の
shell32.dll に対する公開 `DllGetClassObject` で確認した。
**判断: 最小 HKCR 登録を追加し、registry profile を version 3 に更新する。**
既存 prefix の移行は Wine の更新 timestamp と独立して行う。
独立した試験 prefix で該当 CLSID を消し version 2 に戻してから stage すると、
登録と version 3 が復元された。2回目は registry の hash / mtime を変えず、更新処理も行わない。
`.local/registry-v3-migration-test.log` / `registry-v3-check-result.log`。
生ログ `.local/programs-class-providers.log`。内部 COM 実装の解析や実機ハイブの移植は行わない。

Luna で使う Trebuchet の regular / bold / italic / bold italic を同じ ISO から追加抽出した。
`trebuc.ttf` / `trebucbd.ttf` / `trebucit.ttf` / `trebucbi.ttf` を無改変で専用 prefix の Fonts へ配置する。
資源は `.local/assets-luna` の27ファイルに限定し、フォントも Microsoft の原本と同様に Git へ含めない。
ダウンロード、代替元からの取得、フォントや msstyles の編集はしていない。
既存の抽出 integration 試験をこの利用者ローカル fixture でも実行した
（`.local/extraction-luna-test.log`）。


## 調査 20: テーマ適用時の実際の system font

GetThemeSysFont が正しい値を返すことだけでは、適用されたシステム寸法は保証できなかった。
Wine の `parse_handle_nonclient_font` は msstyles のポイント数（10 / 8）を、
LOGFONT の正のピクセル高さとしてそのまま SPI_SETNONCLIENTMETRICS / SPI_SETICONTITLELOGFONT に渡していた。
自作の同一プロセス内の適用・読戻し試験では、実際の system font は +10 / +8、
テーマ API は -13 / -11 となり、6種類すべてが一致しなかった。
**判断: テーマ適用用のフォントを、DPI-unaware で適用する前に96 DPI の負の文字高さへ変換する（0018）。**
caption / small caption / menu / status / message / icon title の全てを扱う。
その後の DPI 拡大は既存の SystemParametersInfo に任せる。

`tests/theme-metrics.c` は builtin Wine のテーマ適用後に実際の SPI の font を読み、
classic → Luna の往復を2回、96 / 144 / 192 DPI で検査する。
caption は96 / 144 DPI で GetThemeSysFont の値と一致する。
高 DPI では96 DPIで丸めた SPI の高さを拡大するため、ポイント数から直接換算する
テーマ API と1px異なる場合があることも確認する。
修正前 `.local/theme-applied-font-before-test.log`、修正後
`.local/theme-applied-font-after-test.log`。Microsoft の font やテーマの内容は変更していない。

## 調査 21: 重なる Wine パッチの再適用判定

0014 は0012で加えた関数の内部も変更するため、完成したソース上で0012だけを
reverse --check すると失敗する。これはパッチ未適用の証拠にはならない。
**判断: touched source のコピーだけで逆順に戻し、順に再構成してから不足分を適用する。**
`wine/patch-state.py` は利用者のソースを reset せず、変更内容を破棄しない。
再構成で本当の衝突があれば、実ソースへ書く前に停止する。
固定 upstream から18本を順次適用した内容が実際のビルド用ソースと一致することを検査した。
未適用、11本適用、18本適用、17→18本の更新、hunk 外の独自変更を持つソースで、
不足分の適用・再実行時の no-op・独自変更の維持を確認した。
`.local/luna-patch-series-check.log` / `patch-state-unit-tests.log`。

## 22. My Computer のアイコン参照と registry profile version 4

新規 prefix の My Computer CLSID には `DefaultIcon` がなく、Wine builtin は
自分の既定アイコンを補う。native XP の公開 `IExtractIconW::GetIconLocation` は
`explorer.exe,0` を返したが、`Extract` は S_FALSE、大小アイコンとも NULL だった。
XP Explorer は Wine の desktop manager を残すため `C:\xp\xp-explorer.exe` に配置している。
同じ公開 API が返した index 0 をこの実ファイルへ明示すると、大小とも S_OK で取得できた。

**判断: version 4 は My Computer の `DefaultIcon` だけを
`C:\xp\xp-explorer.exe,0` に登録する。** Wine 生成の `InprocServer32` は変更しない。
これは Microsoft 公開の [namespace root icon 登録](https://learn.microsoft.com/en-us/windows/win32/shell/nse-implement)
に従う設定変更で、利用者の Explorer を変更・再配布しない。コード解析はしていない。
公開 API の比較ログは `.local/namespace-icon-test.log` と
`.local/namespace-icon-registered-test.log` に保存した。

version 4 は Microsoft 公開の [Pin to Start Menu handler CLSID](https://learn.microsoft.com/en-us/windows/win32/shell/reg-shell-exts)
を `exefile` と `lnkfile` の `shellex\ContextMenuHandlers\StartMenuPin` にも関連付ける。
factory だけの登録では All Programs の shortcut menu に Pin が出なかった。
利用者の操作で Windows Notepad を pin すると左列に実際のアイコンと名前が描かれ、
そこから起動できた。専用 session 再起動後の pin 保持と、Unpin 後の削除も確認した。
既定 pin や MRU を捏造する処理は追加しない。画面は
`.local/start-fidelity-icons-open.png`、`.local/start-fidelity-pinned.png`、
`.local/start-fidelity-pin-persisted.png`、`.local/start-fidelity-pin-removed.png`。
version 3 から4への移行で icon/handler 登録が復元され、2回目の staging は registry の
hash と mtime を変えなかった。My Computer factory も元の Wine 登録を保持した。

## 調査 23: テーマ付きスクロールバーの片側無効化

Wine 自身の `uxtheme/scrollbar.c` はウィンドウ全体の無効化だけを描画に反映し、
公開 `EnableScrollBar` の片側無効化 flags を無視していた。
自作 `tests/scrollbar-theme.c` は上下・左右の実際の非クライアント矢印を取得し、
同じローカルテーマの公開 `DrawThemeBackground` の結果と比較する。
修正前は無効な上・左矢印が各217 pixels異なり、有効な下・右は一致した。
**判断: Wine のテーマ描画で各矢印の disable flags を反映する（0020）。**
修正後は有効・片側無効2種類・両側無効・ウィンドウ全体無効の20比較すべて一致した。
`.local/scrollbar-theme-after-test.log`。テーマ画像や Microsoft コードは変更していない。

## 調査 24: native 時計の Luna 描画と時刻更新

公開 API trace では native TrayClockWClass が通常の Clock theme を開いた後、
TrayNotify app theme を設定して初期 handle を閉じ、以後テーマを開き直さなかった。
親 TrayNotifyWnd の WM_PRINTCLIENT は正しい Luna 背景を返すが、時計自身が白背景と黒文字を重ねる。
**判断: 外部シェル opt-in の当該時計だけ、Wine 側でテーマ描画を補う（0019）。**
元の WM_PAINT は時刻の整形・更新も行うため、先に元の処理を呼び、その WM_GETTEXT を使う。
WM_TIMER・クリック・tooltip・時刻形式は元の処理を維持する。
親の実背景と TrayNotify::Clock の実フォント・文字色を公開テーマ API で描く。
classic / テーマ無効時は元の処理に戻し、独自 theme handle と subclass は破棄時に回収する。
自作 clock-theme 試験は native 相当の WM_PAINT による時刻更新、translated print、
DC 状態・clip、timer / click の委譲、theme 切替を確認する。

## 調査 25: native タスクバー ReBar のグリップ

RB_GETBANDINFOW / RB_GETRECT で取得した9pxの header が classic 表示と一致した。
native ReBar は Taskbar app theme 設定時に初期 theme を閉じ、テーマ part を描かない。
公開 OpenThemeData の Taskbar::Rebar は正しいグリップを返す。
**判断: 外部シェルのタスクバー直下 ReBar の非表示 title header だけを補描する（0021）。**
元のバンド配置・入力・drag 処理を維持し、親のテーマ背景と実 part 寸法を使う。
translated DC・native paint/input 戻り値・無効化・描画中の破棄を自作 rebar-theme 試験で確認。
Start と通知領域の脇にある ReBar 外の細い区切りは残件で、全境界の一致とはしない。

## 26. Wine のフォント属性 tokenizer と実フォントの再適用

Wine の `MSSTYLES_GetNextToken` は末尾空白を除く際に token の直後を参照していた。
length-delimited な値の終端を越えて読む可能性があり、末尾に空白のある名前・属性も残った。
さらに font parser は comma で区切った属性欄全体を `bold` / `italic` 等と比較するため、
複数の属性を空白で並べた欄を処理できなかった。

**判断: 0024 は有効範囲の内側で末尾を trim し、font 属性だけは comma と空白の両方で区切る。**
フォント名内の空白は保持し、テーマが指定する名前と point size は変更しない。
`tests/font_parser.py` は Wine の実 parser 関数を一時 translation unit に取り込み、
自作の `PTHEME_PROPERTY` 文字列 fixture を検査する。Microsoft の theme 資源やコードは読まない。
comma-separated 属性は修正前も成功したが、combined attributes と末尾空白は4件失敗し、
修正後は7件とも成功した。NUL 終端を持たない bounded token と、その直後のアクセス禁止 page
も追加して範囲外参照がないことを確認した。
`.local/msstyles-font-fixture-before.log` / `msstyles-font-fixture-after.log`、
`.local/font-parser-regression.log` に結果がある。

実 Luna の公開 API では caption の weight が400から700、Start::Button の italic が0から1になった。
既存 prefix の保存済み SPI metrics は自動的には変わらないため、Luna の再適用後にも検査した。
再適用後の SPI caption は `Trebuchet MS / -13 / weight 700` で `GetThemeSysFont` と一致し、
menu / message / status は `Tahoma / -11 / weight 400` を維持する（96 DPI）。
Start::Button の font は公開 `GetThemeFont` で `Franklin Gothic Medium / -19 / italic 1` を返す。
`.local/shell-font-probe-after0024.log`、`start-font-parser-fixed.png`、
`caption-font-parser-themed.png` に API と実表示を記録した。
6種の system font の classic/Luna 往復と optional NULL DC の公開試験も成功した。
これは Wine の解釈と実描画の改善であり、実 XP OS との一致は別の reference 試験で確認する。

## 27. 別プロセスの公開 WM_GETICON と borrowed HICON

Wine 10 の自身の `win32u/message.c` は別プロセスの `WM_GETICON` を拒否し、
`cursoricon.c` は foreign USER handle を拒否していた。proxy が正しい icon を所有しても、
native XP タスクバーが公開 API でその画素を取得できないため、既定 icon へ戻っていた。
Microsoft バイナリの内部コードは調べていない。

**判断: 0025 は外部シェル opt-in 時に限り、公開 API の読み取り経路を実装する。**
[WM_GETICON](https://learn.microsoft.com/en-us/windows/win32/winmsg/wm-geticon) の戻り値は元の borrowed HICON のままにし、
server に登録した不変画素 snapshot を必要な読み手だけに materialize する。
[GetIconInfo](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-geticoninfo) が返す bitmap と
`CopyIcon` の結果は読み手が所有する。元の foreign icon の mutation / destruction は許可しない。
共有 `LoadImage` icon を破棄しないという
[DestroyIcon](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-destroyicon) の規則も維持する。
`WM_SETICON` や他の GDI handle message のプロセス間制限は解除しない。

server は owner、USER handle の generation、生存、画像寸法、payload 長を検証する。
static icon の上限は256×256、resource metadata は各2048 bytes、snapshot は16 MiB/owner と64 MiB/server。
owner の破棄・終了時に server の画素を解放する。読み手の cache は最大64個で、利用中の bitmap を pin し、
次の読み取りごとに生存を再確認する。animated icon と上限を超える icon は共有対象外で、所有プロセス内の API は維持する。
opt-in がない通常 Wine では従来どおり foreign message / icon 読み取りを拒否する。

`tests/foreign-icons.c` は自作画素だけで2プロセスを起動し、元の HICON identity、`GetIconInfo`、
半透明色・monochrome AND/XOR の `DrawIconEx`、独立した `CopyIcon`、foreign 破棄拒否、
80個の cache pressure、100回の handle 再利用、owner 破棄・明示破棄なしのプロセス終了を検査する。
257px icon は owner 内で使え、foreign snapshot だけ拒否された。
256px alpha icon 40個のうち31個だけが共有され、owner 内では全て利用できた。
`.local/foreign-icons-enabled.log` と `foreign-icons-disabled.log` はいずれも PASS。
同一 wineserver を維持して owner の起動・大量共有・強制終了を5回繰り返しても毎回31個を共有でき、
終了済み owner の snapshot が server の64 MiB上限を消費し続けないことも確認した
（`.local/foreign-icons-owner-cleanup.log`）。
実行は専用 X display と専用 `WINEPREFIX` を指定し、`foreign-icons-test.exe` を
`WIN4WINE_EXTERNAL_SHELL=1` の有無それぞれで起動する。

0025 は Wine server protocol を変更する。wineserver、ntdll、win32u が混在しない完全 build を使い、
利用中の prefix server を停止してから切り替える。検証では独立した source / build / install を使用し、
元の共有 Wine install を上書きしていない。これにより Microsoft DLL の修正・再配布は発生しない。

追加の callback-first fixture は、読み手が GDI を使う前に `GetIconInfo` を呼んだときの
Wine の初回 display driver 初期化を検査する。既存 `copy_bitmap` が USER lock 中に最初の
compatible DC を作って assertion になる経路を確認したため、cache miss 時の初回 DC 作成と
bitmap import を lock 外で行い、その後 owner / generation と cache の競合登録を再確認する。
`SendMessageTimeout` / `SendMessageCallback`、同時2 thread の cache 読み取り・退避も成功した。
専用 XP prefix ではローカルの元の native `comctl32.dll` を明示して公開 `ImageList_ReplaceIcon` /
`ImageList_GetIcon` を実行し、foreign と local の描画一致を確認した
（`.local/foreign-icons-native-comctl.log`）。Microsoft DLL の内部解析はしていない。
実 XP タスクバーは非同期 callback 後に固有 icon を表示した。settled screenshot の task button 内に
16×16の赤色256画素があり、property 更新後は16×16の緑色256画素に変わった
（`.local/native-icons-taskbar-0025-settled.png` / `native-icons-taskbar-update-0025.png`）。
callback 前の瞬間的な既定画像と混同しないよう、`XP_FRAME_TASKBAR_ICONS=1` の native frame 試験は
公開画面の taskbar 内に初期 icon と更新 icon の画素が現れるまで bounded wait で検査する。

## 28. 公開 API で実測した日本語 XP 字体の prefix profile

ユーザーの実 XP と同一 SHA256 のローカル Luna を公開 API で比較したところ、Wine の
一般的な言語 resource 選択試験、UI language、SPI 変更時の挙動を合わせても字体差が残った。
Microsoft 実装の解析やテーマ資産の改変で原因を推定せず、実 XP の公開 `GetThemeSysFont` /
`GetThemeFont` / SPI 測定値を、自作の明示的な prefix 設定として保存する。
Luna は MS UI Gothic、96 DPI で caption -13 bold、small caption -12 bold、
menu/status/message/icon -12 regular、Start の themed font -16 bold italic だった。
`reference-metrics.c` の Shell_TrayWnd 子 Button の `WM_GETFONT` は Start ボタンの可能性があり、
これをアプリケーション task button の字体と断定しない。

registry profile version 5 は `HKCU\Software\Win4Wine\ThemeProfiles\JapaneseXPLuna` に
Enabled/Version、ThemePath/ColorName/SizeName と7個の自作 LOGFONTW データを、値がない場合だけ追加する。
既存の Enabled=0、独自字体、不正値も上書きしない。0026 の Wine builtin uxtheme が
`WIN4WINE_EXTERNAL_SHELL=1`、active theme と path/color/size の一致、正常な既存 API query、
有効な profile データを満たす場合だけ使う。DLL に固定字体は埋め込まない。
NULL theme の `GetThemeSysFont` は従来の SPI のままで、ユーザーが変更した SPI も維持する。
通常アプリ、別テーマ、Classic、無効化した profile は対象外である。
`create.py` / `display.py` は自作 theme-settings helper の呼び出しにだけ opt-in を追加する。

実 XP Classic の公開 SPI は6字体とも MS UI Gothic -12、caption/small のみ bold だった。
新規 prefix 作成時だけ別の `JapaneseXPClassic` key に6字体を生成し、helper の
`classic-initialize` が Apply(NULL) → 公開 SPI で字体設定 → Luna apply → Apply(NULL) を
同一プロセスで実行する。Wine 自身に新しい Classic baseline を保存・復元させ、非公開の
ThemeManager 保存値は直接編集しない。通常の `classic` / `luna` 切替は従来の Apply(NULL) を維持し、
既存 prefix の migration は Classic 字体を初期化しない。新規作成前に必要なローカル
msgothic.ttc と Luna msstyles の存在を検証する。これらの資産は従来どおり `.local/` 内だけに置く。

`tests/font-profile.c` は96/144/192 DPI、opt-in 有無、profile 無効化・独自字体・欠落・不正型・
不正 LOGFONT、path/color/size/version 不一致、普通の Button、NULL/無効 theme handle、
一時的な SPI 上書きを検査し、すべて成功した（`.local/font-profile-final-public-tests.log`）。
実 migration は独自設定を保持し、繰り返し stage は registry の hash/mtime も変更しなかった。
新規 prefix はサーバー停止後の別プロセスでも Classic6字体と caption18×18 を読み取り、
Luna 往復後も維持した（`.local/fresh-japanese-classic-public-test.log`）。
既存の独自 Classic6字体も別プロセス、Luna 往復、v4→v5 migration を通して維持した
（`.local/existing-classic-custom-preservation-test.log`）。`tests/theme-metrics.c` は
テーマ適用字体に加えて Classic6字体の往復前後の意味的な一致も検査する。

この実画素検査と全 frame gesture 試験は Luna / classic の両方で成功した
（`.local/native-icons-taskbar-0025-pixels.log` / `native-icons-taskbar-0025-classic.log`）。
classic の taskbar 外枠は root の外へはみ出すため、画面に見える範囲へ clip して取得する。


## 29. 実 XP の公開キャプション入力・描画位置

自作ウィンドウの公開 `WM_NCHITTEST` と `GetWindowDC`、公開 `DrawThemeBackground` の
出力だけを比較した。Microsoft のテーマ内部や実装は調べていない。
実 XP の画像は Wine より1px左・1px下で、クリック領域は画像より上下に広く、
最大化と閉じるのクリック領域は接していた。固定サイズ枠でも同じ余白関係だった。
**判断: 0027 は外部シェルの標準テーマ枠に限り、描画画像と入力余白を独立に扱う。**
画像寸法・状態画像は引き続き利用者のテーマを公開 API で読む。
子・tool window・Classic・非opt-in は従来の経路を維持する。
96 DPI は実 XP の独立fixtureと一致し、144/192は選んだ拡大規則で回帰検査した。
高 DPI の実 XP 一致や文字のラスタライズの完全一致とはしない。


## 30. task ReBar の子の後方余白

実 XP と Wine の公開 ReBar band/child 矩形を比較し、両方に4pxの未使用末尾があるが、
Wine だけ元の灰色背景が残ることを実画面の数値で確認した。
**判断: 0029 は既存外部シェル ReBar hook で、公開 child/band 矩形の末尾だけをテーマ描画する。**
Taskbar直下でHIDETITLEのMSTaskSwWClass childだけを扱い、hidden/chevron/child-edgeは除外。
childの画素・header・バンド配置・native入力・lock設定は維持する。
背景は0016の公開 DrawThemeParentBackground経路を使い、色・幅・Microsoft資源は埋め込まない。


## 31. 公開 GDI 測定による caption と Start の寸法修正

実 XP の自作ウィンドウと公開 DrawText/DrawThemeText/GetThemeTextExtent を比較した。
SPI smoothing=TRUEのまま、Wine の小サイズ synthetic bold/italic 方針を専用 prefix の明示設定で選ぶ。
Microsoft のフォント・テーマの内容は変更しない。新規 prefix の未設定時に限り初期化し、
既存設定は `display.py --font-rendering` の明示指定時だけ変更する。

**判断: Wine の外部 shell opt-in に monochrome advance と垂直中央揃えの修正を追加（0030/0031）。**
公開 metrics と実 glyph の位置が異なったため、bitmap advance の代わりに既存 metrics 計算経路を使う。
通常 Wine、明示 dx/PDY、antialias 経路を維持する。
**判断: 0032 は公開 single shadow の属性を DrawThemeText に反映し、caption から利用する。**
active の offset/color/type を問い合わせ、inactive の影がない状態も尊重する。
文字と影の幾何は自作 public API fixture と実 XP で比較し、実画面の764画素も一致した。
DrawThemeText の TEXTCOLOR 取得失敗時の一般的 fallback 色は今回の対象に含めず、
caption は公開 system caption text color を指定する。

**判断: 0033 は Start alias のテーマ文字と標準余白・画像寸法から理想寸法を計算する。**
伸縮背景画像の元寸法を最小 window 寸法として扱わない。既存の画像 alignment/margin 処理は保持。
実 XP の公開理想寸法112×26に一致するが、実 window 高さ30pxへの配置は別の残件。
調査は公開 control message と Wine の自作ソースだけで行い、Microsoft 内部コードは解析しない。


## 32. Luna caption の未指定アイコン

WineのClassic描画はsmall/big/class small/class bigの順で読み、未指定かつ非modalなら
Wine自身の共有stock IDI_WINLOGOを使う。外部shellのLuna描画だけ後半が欠けていた。
**判断: 0034は既存Classicと同じ公開APIの取得・補完順を使用する。**
アイコンの所有権は変えず、LR_SHAREDのstock iconも破棄しない。modal no-iconは補完しない。
自作ウィンドウ6パターンを公開DrawIconExの結果と比較し、独立環境とVMで成功した。

## 33. 作業領域とタスク文字の追加修正

**判断: 0039はWine自身の公開X11 property通知とmonitor cacheを修正する。**
EWMH/GTKの有効な作業領域だけをdesktop所有threadで観測し、同一値を除外して
WM_SETTINGCHANGEを通知する。明示SPI上書きと非opt-inの挙動を維持する。
Microsoft資産なしの自作公開API試験で動的変更・最大化・通知回数を確認する。

**判断: 0040は実XPの公開TaskBand::Toolbar測定値を既存の明示字体profileへ追加する。**
TaskFontは未設定時だけ生成し、有効な日本語Luna profileのpart/stateに限り適用する。
実タスクの公開Toolbar messageは自作bufferを相手processに確保して利用し、そのbuffer
だけを読み戻す。Microsoft実装のメモリ・コード・非公開データは調べない。
実時計の字体適用も、公開GetWindowTextとGetDCによる画面を自作DrawThemeTextと比較する。
DLL・テーマ・フォントの改変や再配布は行わない。

## 34. 所有threadの最大化と描画しないpopup表示

**判断: 0041は外部shellに限りWineのmanaged最大化サイズ抑制を解除する。**
WMによる非同期補正ではWineのpending矩形と実Xサイズがずれ、復元位置を壊した。
Wine自身のtraceと公開API fixtureで確認し、所有threadが計算した幾何を反映する。
アプリ独自のWM_GETMINMAXINFOを尊重し、Linux代理も公開ShowWindowで最大化する。

**判断: 0042は明示SWP_SHOWWINDOW|SWP_NOREDRAWの非layered popupに限り、元の画面を保持する。**
実XPの自作公開API試験は描画せずに表示した領域の下地を維持したが、Wineは黒い初期bufferを
転送していた。X11のbackgroundをNoneに保ち、新規bufferをclip済みのroot画素で初期化する。
取得できない条件は既存fallbackを使い、通常表示・layered・opt-outを維持する。
Startが安定した後の画像は修正前と同じで、描画方式を直接X描画へ置き換えない。
観測は公開API・画面・Wine自身の実装のみで、Microsoft内部実装を解析しない。

## 35. Start パネル下部の文字色と Start 画像の縮小

**判断: 0043は SetWindowTheme の空文字列を受け付ける。**
XP explorer はログオフ用 toolbar に `SetWindowTheme(hwnd, L"", L"")` を使い、
custom draw で白い文字色を与える。Wine は空文字列の atom 作成に失敗して呼び出し全体を
失敗させ、WM_THEMECHANGED も送らなかった。native toolbar はテーマ付きのまま黒字で描いた。
どのテーマ class にも一致しない名前を保存し、その window の OpenThemeData だけを失敗させる。
文書化された Win32 の挙動の修正で、opt-in に限定しない。

**判断: 0044は外部 shell の Win4WineStartButton に限り WM_CTLCOLORBTN の再塗りを省く。**
後の Windows の試験に基づく Wine の再塗りが、XP タスクバーの BTNFACE を Start 画像の
透過した丸角に出していた。通常の Button は変更しない。

**判断: 0045は TransparentBlt の作業 DC に COLORONCOLOR を設定する。**
Wine は元画像側の DC の伸縮 mode を変えていたが、StretchBlt は転送先の mode を使う。
新規 DC の BLACKONWHITE で縮小時に複数行が AND 合成され、Start 画像の中段に存在しない色が出た。
実XPは同じ寸法で元画像の13/15/17行目をそのまま使う。自作画素の公開API試験で確認する。
観測は公開API・画面・Wine自身の実装のみで、Microsoft内部実装やテーマ資源は解析・出力しない。

**判断: 0046は外部 shell の size 選択 glyph を ContentMargins 内で選び、中央に置く。**
Luna の caption button は 9/13/19/23px の glyph を持つ。Wine は21×21の外形で選んで19px を使い、
記号が大きく見えた。実XPは同寸法で13px を使い、2px の内容余白を除いた17×17での選択と一致する。
144/192 DPI の32/42px button は従来どおり23px glyph。公開APIと画面の比較だけで判断した。

**判断: 0047は caption の右クリックを離した位置を WM_NCHITTEST で判定する。**
固定解除した XP タスクバーは WS_CAPTION を持たず、自身の WM_NCHITTEST で帯の間を HTCAPTION とする。
Wine の DefWindowProc は押下時はその値で capture loop に入るが、離した位置は内部の既定判定で調べ、
HTCLIENT となって WM_CONTEXTMENU を送らなかった。押下時と同じく window に問い合わせる。

**判断: 0048は外部 shell の DrawFrameControl(DFC_CAPTION) の Marlett 字体と位置を実XPに合わせる。**
Wine は em=正方形の辺−2 を text extent で中央寄せし、16×14の最大化記号が1px左・1px幅広く、
左のボタンに接して見えた。自作の公開API probe を実XPで実行し、高さ10〜30pxで em=辺−4、
正方形の内側2px（押下時3px）から描くことを確認した。実XP・修正後Wineで `--verify` が成功し、
修正前Wineで失敗する。XP の字形画素はリポジトリへ保存しない。

**判断: 0049は外部 shell の CW_USEDEFAULT を XP の重ね配置にする。**
実XPの自作公開API probe で、96 DPI の Luna/Classic とも右へ22px、下へ SM_CYSIZE+SM_CYFRAME、
作業領域の1/4を超えると先頭へ戻り、既定寸法は幅3/4×(高さ3/4−23px) と測った。番号は desktop window の
property で全 process 共有する。STARTF_USEPOSITION/USESIZE を優先する。WM も位置指定のない Linux
ウィンドウを同じ規則で重ねる（枠の上端−1を縦の間隔に使う）。Win32 と Linux の番号は別々に進む。

**判断: 0050は外部 shell の DefWindowProc に WM_QUERYUISTATE/CHANGEUISTATE/UPDATEUISTATE を実装する。**
Wine は3つとも未処理で、XP の native control は常に全手がかりを描いた。実XPで自作公開API試験を
手がかりオン/オフで実行し、初期状態0、最上位で変化時だけ子へ伝播、オン時は隠す要求を無視することを
確認した。既定はオン（実XP参照機と同じ）なので通常の見た目は変わらず、オフにした利用者で効く。

**判断: registry profile 10/11 は XP の名前空間名の参照と日本語 XP のアイコン間隔を入れる。**
My Computer などの LocalizedString/InfoTip を、実XPで読んだ値（XP shell32 のリソース番号）にする。
文字列そのものは利用者の XP DLL に残し、リポジトリには番号だけを置く。デスクトップの横間隔は実XPの
SPI 値78px（Wine 既定75px では74px幅の「マイ コンピュータ」が折り返す）を一度だけ設定する。

**判断: 0051は外部 shell の caption 領域が広がったとき、新たに見える非クライアント部分を再描画させる。**
最大化・拡大の直後は古い丸角領域が枠の描画を切り取り、その後の SetWindowRgn(..., FALSE) は再描画しない。
caption は後で描き直されるが、メニューバーの右端が黒く残った。広がった差分だけを RDW_FRAME で無効化する。

## 36. XP の終了ダイアログとセッション終了

Start の「ログオフ」「シャットダウン」は XP Explorer が msgina の序数16（ShellShutdownDialog）を
遅延読み込みし、Wine に msgina が無いため Explorer が異常終了していた。
**判断: 利用者の XP メディアの msgina.dll を無改変で抽出し、xp-explorer にだけ native で使う。**
XP 本来の「Windows のシャットダウン」ダイアログと暗転画面がそのまま使える。必要な Wine 側の補完は
0052（wuaueng の WUCheckForUpdatesAtShutdown、引数1個、更新なし）と 0053（DestroyReasons）。
0055 は背景ブラシのない popup の新規 buffer を root 画素で初期化し、灰色の暗転を表示する。
WM は EWMH の ABOVE を公開し、Win32 の topmost window（暗転画面）とその transient をタスクバーより上に置く。

**判断: 0054 と supervisor でログオフ等をセッション終了として扱う。**
ExitWindowsEx は外部 shell の要求ファイル（WIN4WINE_SESSION_REQUEST）に logoff/shutdown/reboot を書き、
supervisor は shell の終了を異常終了として再起動せず、セッションを終える。shutdown/reboot では
session.json の `shutdown_command`/`reboot_command`（既定 `systemctl poweroff`/`reboot`）を実行する。
ダイアログのログオフ項目の利用者名は registry profile 13 の `Logon User Name`。

## 37. 壁紙・ユーザー画像・ようこそ画面の設定

**判断: 利用者メディアの Bliss.jpg と beach.bmp を抽出し、XP と同じ場所へ無改変で置く。**
XP は JPEG の壁紙を自分で Wallpaper1.bmp に変換して表示し、変換がないと HTML の Active Desktop に切り替わる
（mshtml を無効にしているため白画面になった）。自作の `prefix/wallpaper-convert.c` が Wine の WIC で同じ変換を
行い、0056 が XP Explorer の process での読み込みと WallpaperStyle 2（拡大）を描く。元の画像は変更しない。
registry profile 15/16 は壁紙設定と `LogonType=1`（ようこそ画面）を一度だけ入れる。実XP参照機と同じく
Start のユーザー画像と「終了オプション」、XP の「コンピュータの電源を切る」ダイアログになる。

**判断: 0057は日本語 Luna profile に Start のユーザー名と「すべてのプログラム」の字体を加え、連続影を描く。**
実XPの公開 GetThemeFont は StartPanel の user pane を MS UI Gothic -19 太字、More Programs を -12 太字で返し、
Wine はテーマの Franklin Gothic Medium / Tahoma のままだった。profile 17 で値を追加する。
user pane の TST_CONTINUOUS の影は、実XP画素への当てはめ（5×5三角形ぼかし、オフセット−1、不透明度94%）で描く。
縦線左側の影は実XPよりわずかに薄い。

**判断: 0058は localized msstyles の文字列テーブルにある値（`NormalBlue@[Section]Name=Value`）を ini に重ねる。**
日本語 Luna はここに MS UI Gothic の字体を持ち、XP はそれを ini より優先する。Wine は ini だけを読み、
Tahoma / Franklin Gothic Medium のままで、Start パネルも20px狭かった。選択中の配色・サイズの値を
実行時に利用者のテーマファイルから読み、26 class・117件の TMT_FONT が実XPと一致した。
0026/0057 の明示 profile は同じ値になり、profile を無効にした利用者にも XP と同じ字体が適用される。

## 38. フォルダウィンドウのツールバー領域とアドレスバー

**判断: 0059 は外部 shell の SetWindowTheme で WM_THEMECHANGED の wParam に -1 を送る。**
XP の comctl32 v6 は変更番号が前回と同じ（初期値0）ならテーマを開き直さない。0 を送っていたため、
`SetWindowTheme(ReBar, "ExplorerToolbar")` 後の ReBar はテーマを閉じたままクラシック描画になった。
送る値の根拠は、同じ ReBar に 0 と -1 を送った公開メッセージ試験で -1 だけが開き直したこと。

**判断: 0060 は ComboBoxEx32 の子の ComboBox を別名モジュール（win4wine-controls）のテーマ付き実装にする。**
native comctl32 は SxS の活性化コンテキストなしで読み込むため、XP の v6 ComboBox が使われず user32 になる。
Start ボタン（0013）と同じ方式で、名前を分けたクラス（Win4WineComboBox / Win4WineComboLBox）を登録する。
native comctl32 とその manifest は変更しない。全 ComboBox への適用はしない。

**判断: 0061/0062 は実XPの画面に合わせて、テーマ画像の拡大を画素の繰り返し、glyph 中央寄せを（外形−glyph）/2、
caption の背景を SM_CYCAPTION の全高にする。** いずれも外部 shell の opt-in 時だけ。

**判断: 0063/0064 はテーマ画像と TransparentBlt の拡大縮小で、実XPで測った元画素の選び方を使う。**
XP の uxtheme は画像を自前で拡大縮小し、GDI の StretchBlt・TransparentBlt とも結果が異なる。
規則は自作の1行画像と公開テーマ part の描画結果から求めた数式だけで、XP の画素やコードは持ち込まない。

**判断: 0065 は WM_SETICON の後にも外部 shell の Luna 枠を描き直す。** WM_SETTEXT と同じ扱い。

**判断: 0066 は日本語 ANSI コードページの外部 shell で、DrawText の折り返しを実XPで測った規則にする。**
禁則文字の一覧と戻し方は自作文字列の折り返し位置の測定値から決めた。usp10 の UAX#14 とは結果が異なる。

**判断: 0068 は native comctl32 を読み込んだプロセスだけ、標準コントロールを Wine のテーマ付き実装で作る。**
調査7の「Button は Wine 標準のままクラシック表示」を改める。native v6 の Button は使わず（access violation のため）、
Start ボタンと同じ別名モジュールの Wine 実装を使う。Wine の comctl32 を使う通常のアプリには影響しない。

**判断: 0072 は合成マネージャーのない X で、XP の影を表示時の画面の写しから作る。**
XP は層状ウィンドウで背景と合成する。ここでは表示時点の背景を暗くした静止画のため、影の下が後から変わると古い
内容が残る。メニューのように短時間で閉じるウィンドウを想定し、移動したら影を消す。対象は caption も
サイズ変更枠もない最上位のポップアップに限る（スタートメニューは activate されて管理対象になるが、これに含める）。


## 39. 特殊フォルダの名前とアイコン

Start パネルの「マイ ピクチャ」「マイ ミュージック」が Wine のフォルダ名（Pictures/Music）と普通のフォルダの
アイコンで、「マイ ドキュメント」「最近使ったファイル」もアイコンが違った。実XPでは `tests/folder-icons.c` で、
各フォルダの desktop.ini が `[DeleteOnCopy]` の Personalized（CSIDL）と PersonalizedName（作成時の名前）で
名前を、`[.ShellClassInfo]` でアイコンと説明を与え、マイ ドキュメントは CLSID の DefaultIcon が mydocs.dll,0 だった。
**判断: stage が prefix 内の実フォルダにだけ、実XPと同じ項目の desktop.ini を書き、システム属性を付ける。**
「スタート メニュー」「プログラム」「スタートアップ」（利用者と All Users）も同じく LocalizedResourceName で名付ける。
利用者のホーム（H:\ のマイ ドキュメントや XDG へのリンク）には書かず、ほかの desktop.ini は残す。
値は設定項目と番号だけで、XP のファイルは複製しない。
**判断: 利用者の XP メディアの mydocs.dll を無改変で抽出し、アイコンの読み出し元にだけ使う。**
COM の登録は Wine のままで、mydocs.dll のコードは読み込まない。無い既存 prefix ではマイ ピクチャの desktop.ini と
マイ ドキュメントのアイコンを入れない。

## 40. WM と proxy のイベント駆動化

WM（Python）と proxy は 0.1 秒・0.2 秒ごとに起きてファイルと X を調べ、待機中も毎秒数百回起きていた。
枠の追従やタスクバーへの反映はその周期だけ遅れた。
**判断: WM は Python のまま、X のイベントと inotify で起きる形にする。** 言語を変えても、遅れの主因
（定期確認と、混んだ X サーバーへの多数の問い合わせ）は残る。イベントで状態を記憶して問い合わせを減らせば
十分速く（Debian VM で枠の追従 11 ms）、既存の統合試験をそのまま使える。
**判断: proxy は IPC ディレクトリの変更通知と out-of-context の WinEvent で起きる。** Win32 のシェルが知るべき変化
（最上位ウィンドウの生成・破棄・表示・非表示、前面化、最小化、題名）は WinEvent で届く。Wine の WinEvent は
wineserver が hook の所有スレッドへ投函するので、XP のプロセスに何も読み込ませない。
**判断: 生存確認は wineserver が POSIX lock にする LockFile を使う。** proxy は Windows のプロセスで、Linux の pid も
socket も公開 API では持てない。ファイルの更新時刻による確認は、変化がないと書かない方式と両立しない。

**判断: 0073 は外部シェルの opt-in 時だけ、DefWindowProc の WM_SETTEXT で EVENT_OBJECT_NAMECHANGE を出す。**
Windows は題名の変更をこの WinEvent で知らせる（公開文書）。Wine 10 は出さないため、proxy は題名だけのために
巡回する必要があった。通常の Wine アプリでは出さない。

**判断: 0074 / 0075 で、外部シェルの Luna 枠を必要な部分だけ描き直す。** XP は移動だけでは非クライアント領域を
描き直さず、WM_NCPAINT では渡された更新領域を描く。0023 は位置が変わるたびに、0014 のフックは WM_NCPAINT のたびに
枠全体を描いていた。0075 は更新領域がタイトルバーの帯にかからないとき、その領域に切り抜いた DC を渡し、
0074 はタイトルバーが切り抜きの外なら枠の辺だけを描く。タイトルバーの領域（角の形）の作り直しを省くキャッシュも
試したが、0076 の競合を見えやすくしただけで、遅れへの効果は 0075 の後ではほぼなかったので入れない。

**判断: 0076 は外部シェルの opt-in 時だけ、テーマ画像の選択と転送を critical section で1つずつにする。**
uxtheme はテーマ画像の bitmap をプロセスで共有するが、bitmap は同時に1つの DC にしか選択できない。XP Explorer は
フォルダウィンドウごとのスレッドで描くので、同時に描くと片方が既定の空の bitmap から描き、タイトルバーが黒くなる。
Wine 本来の競合で、通常の Wine アプリにも起こり得るが、opt-in の方針どおり外部シェルに限る。転送は数 ms で、
待つのは同じプロセスで同時に描くスレッドだけ。

## パッチの整理（段階 2、2026-10-10）

以下の番号は整理後のもの（旧番号は括弧内）。

**判断: 76 本を機能ごとの 55 本にまとめ、opt-in の要らない修正、XP の部品が呼ぶ API、外部シェルの基盤、bridge との連携、
ウィンドウと GDI、コントロール、uxtheme の順に並べる。** 後のパッチが前のパッチの変更を書き換えるもの（旧 0060 を
置き換えた 0068、旧 0061 の COLORONCOLOR を消した 0063、0014 の枠に後から加えた位置や状態の修正など）は1本にまとめた。
並べ替えの前後で、未改変の Wine 10.0 に当てたソースツリーは完全に一致する（下の判断の変更を除く）。
64bit（WoW64）対応のときに PE と Unix の両方でまとめてビルドし直すため、DLL ごとの境界より、一緒に試す機能の境界を優先した。

**判断: opt-in 判定を `include/wine/win4wine.h` の `win4wine_external_shell()` に1つにまとめる（0015、新規）。**
約70か所で `GetEnvironmentVariableW(L"WIN4WINE_EXTERNAL_SHELL", NULL, 0)` と `getenv("WIN4WINE_EXTERNAL_SHELL")` を
書き分けていた。Unix ライブラリでは Unix の環境、PE ではプロセスの環境を読むのは同じで、DLL ごとの静的な inline 関数に
なるので、モジュールの境界も呼び出し方も変わらない。字体 profile（0050、旧 0026）だけが値が `1` であることを
確かめていたが、session と補助ツールはどれも `1` を設定するので、ほかと同じく「変数があること」にそろえた。
`user32/desktop.c` の同じ判定だけの関数は削除した。

**判断: 共有テーマ画像の排他（0008、旧 0076）は opt-in をやめ、Wine 一般の修正にする。読み込みの一覧にも排他を加える。**
- 競合は Wine の uxtheme 自身のもの。テーマ画像の bitmap をプロセスで共有するが、bitmap は同時に1つの DC にしか
  選択できない。複数のスレッドが描くアプリなら、XP の explorer でなくても描画が空の bitmap からになる。Windows の
  テーマ描画はスレッドから安全に呼べるので、直すのは文書化された挙動の修正で、0007（SetWindowTheme の空文字列）や
  0009（TransparentBlt）と同じ扱いになる（`守ること` の「通常の Wine アプリの挙動を変えない」は XP に合わせる変更が対象）。
- upstream の Wine（2026-10 の master）も同じ構造で、排他はない。
- 費用は競合のないとき critical section の出入りだけ。保持するのは選択と転送の間だけで、その間にアプリへ戻る
  呼び出しはないので、ロックの順序による停止は起きない。
- `MSSTYLES_LoadBitmap` の一覧も排他なしに追加されていた。2つのスレッドが同じ画像を同時に初めて描くと、
  2回読み込み、一覧の更新を1つ失う（その bitmap はテーマを閉じても解放されない）。検索と追加を別の critical section で
  囲んだ。読み込み済みの画像の検索は従来どおり速い。
- 2026-10-10 に利用者が opt-in なしで確定した。

**判断: 0019（旧 0001）と 0020（旧 0002）は opt-in にしないままにする。** 0019 は X のウィンドウに私用の属性を
2つ付けるだけで、bridge 以外の WM は読まない。0020 は stub で失敗していた RegisterShellHookWindow を、
ウィンドウの属性の記録にする。どちらも通常のアプリの見た目と動作を変えない。段階 2 では挙動を変えない方針で、
この2つは対象にしなかった。

## 41. デスクトップの右クリックメニューの区切り線（段階 3、2026-10-10）

デスクトップの右クリックメニューで「ショートカットの貼り付け」と「新規作成」の間の区切り線が欠けていた。
メニューを組み立てるのは XP の shell32 で、変更できない。`tests/desktop-menu.c` で実XPと Wine の組み立てを比べ、
user32 の呼び出しと戻り値は同じで、shell32 の分岐だけが違うことを確かめた（段階 3 の検証）。
**判断: New ハンドラーの CLSID キーに、XP と同じ `flags`（REG_DWORD 0）を registry profile 23 で入れる。**
- 実XPの登録にある値で、Wine の登録に無かった。加えるとプローブの結果も実際のメニューも実XPと一致する。
- 値の意味は公開文書で確かめられないため、XP と同じ値を置くことだけを根拠にする。値を読む shell32 の処理は調べていない
  （逆アセンブルしない）。
- Wine のパッチで user32 を変える必要はない。Wine の builtin shell32 はこの値を読まないので、通常の Wine アプリには影響しない。
**判断: 調査で、プローブのプロセスの中でだけ shell32・shlwapi の user32 の import を記録用の関数に差し替えた（`--trace`）。**
PE の import 表は公開された形式で、XP のコードを読んだり、ファイルを書き換えたりはしない。呼び出しの順と引数・戻り値だけを比べた。
**判断: アクセスキーの下線は、0035 で外部シェルの opt-in 時だけ XP と同じ長さ（文字の送り幅いっぱい）にする。**
実XPで `tests/text-underline.c` により測った。メニューも user32 の DrawText で下線を描くので、1か所で全メニューがそろう。
XP に合わせる変更なので、ほかの 0035 の変更と同じく通常の Wine アプリには適用しない。
**判断: 「新規作成」のサブメニューは「フォルダ」と「ショートカット」だけにする（2026-10-10、利用者の判断）。**
XP のファイルの種類は、それぞれのアプリの ShellNew の登録で出る。Wine の prefix に対応するアプリの登録を XP と同じ形で
入れる必要があり、見合わない。
**判断: MENUEX の区切りの状態、DrawText の末尾の `&` とタブの後の下線は直さない。** いずれも変更前からあり、
デスクトップの右クリックメニューの見た目には出ない。後回しの候補として残す。

## パッチの再整理（段階 4、2026-10-10）

**判断: 段階 3 の下線の変更は新しいパッチにせず、0035 に含める。** 0035 は DrawText を XP に合わせるパッチで、
変える関数も同じ `dlls/user32/text.c`。`docs/history/patch-history.md` の「既存のパッチを直す変更は、そのパッチに含める」に従う。
**判断: 0015 は新しいヘッダーを `include/Makefile.in` の一覧にも加える。** Wine の makedep は一覧にある `include/` の
ヘッダーだけを解決するので、無いと未改変のソースからの configure が失敗する。一覧に加えると `make install` で
`include/wine/` にも入るが、Wine の公開ヘッダーと同じ扱いで、挙動は変わらない。
**判断: 整理の検証は、新しいソースとビルドディレクトリで configure からビルドしたもので行う。** 段階 2 は使い回した
ビルドディレクトリで差分ビルドしたため、0015 の一覧の漏れに気づかなかった。

## Wine 11 への移行（段階 5、2026-10-10）

**判断: 基にする Wine は 11.0（`wine-11.0`、db11d0fe）にする。** 11.0 の保守版（11.0.x）はまだ出ていない（gitlab の
`stable` ブランチの先頭が 11.0 のリリース）。保守版が出たら、パッチが当たることと同じ試験を確かめて移る。
**判断: upstream に同じ修正が入った 10.0 版の 0001（binutils 2.44）、0009（TransparentBlt の縮小 mode）、0021（題名の変更の
WinEvent）は外す（利用者の判断）。** 0021 は 11.0 ですべてのアプリに入ったので、残すと opt-in 時に二重に通知される。
**判断: パッチは 0001〜0053 に振り直す（利用者の判断）。** 番号の対応は `docs/history/patch-history.md`。
**判断: 外部シェルのプロセスでは comctl32.dll を `\KnownDlls` から取らない（新 0016、利用者の判断）。** 11.0 の wineboot は
KnownDLLs とその import 先を `\KnownDlls` に登録し、comctl32 も既知 DLL になった。XP Explorer は SxS の activation context
なしで動き、exe と同じ `C:\xp` の XP の v6 に頼っているため、11.0 のままでは system32 の XP の v5 を読んで崩れた。
- 実XPでは explorer の manifest による SxS のリダイレクトが KnownDlls より先に効く。exe の隣の v6 はその代わりなので、
  例外は comctl32.dll だけに限る。ほかの既知 DLL と、opt-in の無いプロセスは 11.0 のまま。
- prefix の KnownDLLs の値を消す方法は取らない。comctl32 は値ではなく import の連鎖で登録され、wineboot の更新のたびに戻る。
- explorer に manifest を与える方法は、クラス名の版や 0039 のテーマ付きコントロールの仕組みが変わるため、段階 5 では取らない。
**判断: Win32 の判定は ntdll でも 0013 の `win4wine_external_shell()` を使う。** ntdll は kernel32 を呼べないので、
`_NTSYSTEM_` のときは `RtlQueryEnvironmentVariable_U` でプロセスの環境を読む（意味は PE モジュールと同じ）。
**判断: win4wine-controls.dll は 11.0 の comctl32_v6.dll から作る。** 11.0 は comctl32 を v5 と v6 に分け、テーマ付きの
Button などは v6 だけにある。0038〜0040 の変更も `dlls/comctl32_v6/` に移した。
**判断: すべての窓を閉じた後にデスクトップのアイコンにフォーカスの点線が出るのは、11.0 の挙動のまま受け入れる。**
10.0 版では閉じた後の前面ウィンドウが Wine のデスクトップ（#32769）だったが、11.0 では Progman になり、アイコン一覧に
フォーカスが移る。実XPで同じ操作の後に `tests/foreground-focus.c` を実行すると、
前面は Progman、フォーカスはアイコン一覧、フォーカス項目は 0 で、画面にも点線が出た。11.0 の方が実XPに近い。

## 日本語入力（段階 6、2026-10-10）

**判断: 入力メソッドは fcitx5 と fcitx5-mozc にする。** ロードマップの指定。Wine は XIM、GTK のアプリは fcitx5 の IM モジュールで
つながる。Qt のフロントエンドは入れていない（Qt アプリで入力するときは fcitx5-frontend-qt5 / qt6 を足す。段階 8 で確かめた）。
**判断: 試験で使う Linux のブラウザは Debian の Chromium にする（利用者の判断）。** Google Chrome と IME の経路（X11 で GTK の
IM モジュール）は同じで、第三者のバイナリを取得・実行せずに済む。
**判断: 入力メソッドの起動と環境変数は supervisor が管理し、im-config は入れない（利用者の判断）。** LightDM（Debian）は
`/etc/X11/Xsession` を通すので im-config でも動くが、その場合はその利用者のすべての X セッションに効き、Xsession を通さない
ディスプレイマネージャでは効かない。supervisor は、ログイン側が先に変数を設定していればそれに従い、XIM サーバー
`@server=fcitx` がすでにあれば起動しないので、im-config と並べても二重には起動しない。
**判断: 入力モードは StatusNotifierItem を XP の通知領域に出して示す（利用者の判断）。** fcitx5 には常に出ている浮動パネルが
無く（切り替えのときにカーソルの近くに一瞬出るだけ）、XEmbed は X の窓の画素を写す必要がある。SNI の host は fcitx5 以外の
Linux のトレイアプリにも効く。XP の言語バーを模した窓は作っていない（後回しの候補）。
**判断: XP の通知領域へは Wine の Shell_NotifyIconW を opt-in 時に XP の形式で送って届ける（0026、利用者の判断）。** proxy だけ
XP の shell32 を使う方法も試して動いたが、Wine の Win32 アプリのアイコンは出ないままになる。形式は公開されていないので、実XPで
自作のおとりの窓に XP の shell32 が送ったデータを受け取らせて測った（逆アセンブルはしていない）。アイコンは呼び出し側の handle の
まま渡し、XP の Explorer は 0021 で他プロセスのアイコンとして読む。64bit のアプリ（段階 7）では handle の幅に注意が要る。
**判断: 通知領域の黒い背景の修正は 0053（段階 5 の 0051）に含める（利用者の判断）。** どちらもタスクバーの子の背景の話で、
変える関数も同じ `dlls/uxtheme/draw.c`。BgType が None のパーツを部分的に透明と答えるのは実XPの公開 API の結果と同じで、
opt-in のプロセスだけに効かせる。
**判断: XIC を作る前の変換位置を覚える修正（0027）を opt-in で入れる（利用者の判断）。** upstream（11.0 と master）の挙動で、
53 本の影響ではない。
**判断: 新しいパッチは「まとまりに合う位置に入れる」に従い 0018–0027 の末尾に入れ、後ろを振り直す（利用者の判断）。**
**判断: Linux アプリの字体は session.json の `linux_font` で選べるようにし、既定を prefix の MS UI Gothic にする（利用者の判断）。**
fontconfig の設定は状態ディレクトリに作って `FONTCONFIG_FILE` で渡し、システムと利用者の設定は include で残す。MS の字体の
ファイルは prefix の中のものを参照するだけで、リポジトリには入れない。代わりの日本語の字体として fonts-ipafont-gothic も入れた。

## 64bit（WoW64）対応（段階 7、2026-10-10）

**判断: Wine は新しい WoW64 方式（`--enable-archs=i386,x86_64`）でビルドする。** Unix 側は 64-bit だけになり、実機に i386 の
ライブラリが要らない。32-bit だけのビルドの手順は残さない（git の履歴にある）。configure の結果（見つからない開発ファイル）は
32-bit のビルドと同じ。
**判断: prefix は 64-bit にし、XP の DLL は `syswow64` に置く。** `system32` は 64-bit の Wine の DLL のまま残し、64-bit のアプリは
Wine の shell32 などを使う。XP の DLL の override は今までどおり XP Explorer の AppDefaults だけ native で、32-bit のプロセスが
`system32` を開くと `syswow64` に振り向けられるので、XP の参照（`%SystemRoot%\system32\SHELL32.dll,...` など）は書き換えない。
**判断: XP シェルのための登録は 32-bit の view にだけ書く。** Wine は Windows と同じく `HKCR\CLSID` と `HKLM\Software` を
`Wow6432Node` に分け（`HKCR` の `Folder` や `.exe` などと HKCU は共通）、`wine reg` は 64-bit の reg.exe なので `/reg:32` を付ける。
XP の DLL を指す COM の登録や XP の shell32 の文字列の参照を 64-bit の view に書くと、64-bit のプロセスが読めない DLL や
Wine の shell32 にない番号を指すことになる。
**判断: 既存の 32-bit prefix は新しい 64-bit の prefix へ移す（`prefix/migrate.py`）。** WoW64 の Wine は 32-bit の prefix を
動かせず、prefix の架構は Wine で変えられない。HKCU は両方の view で共通なので `user.reg` をそのまま写し（ファイルの架構の行だけ
変える）、利用者のファイルは `drive_c/users` と `drive_c/ProgramData` を写す。入れたアプリは HKLM の登録と `Program Files`
の置き場所（32-bit は `Program Files (x86)`）が変わるので移さない。古い prefix は変えずに残す。
**判断: XP Explorer のプロセスにだけ WOW64 を知らせない（0017、利用者の判断）。** XP の shlwapi は
`NtQueryInformationProcess(ProcessWow64Information)`（`IsOS(OS_WOW6432)` と同じ問い合わせ）で WOW64 かを調べ、XP の shell32 は
WOW64 では別の処理に入る。スタートメニューの「プリンタと FAX」のアイコンの場所が `shell32.dll,-138` ではなく
`C:\windows\system32\SHELL32.dll,3`（一般のフォルダ）になった。公開 API の呼び出しの記録（`+relay`）と `tests/folder-icons.c` で
調べ、XP の DLL の中は見ていない。XP のシェルは 32-bit の Windows のために作られたので、その上の挙動に合わせる。範囲は opt-in で、
かつ実行ファイルが `xp-explorer.exe` のプロセスだけ（XP の DLL を native で読むのはこのプロセスだけ）。ファイルシステムと
レジストリの振り向けは変えない。セッションのほかのプロセスや、そこから起動する 32-bit のインストーラーなどは WOW64 を正しく知る。
**判断: 0026（XP の影）は double で計算する。** 32-bit のビルドの Unix 側は x87 の拡張精度、64-bit は SSE の float で、影の濃さを
掛けて切り捨てるときに壁紙の画素が1段階ずれた。double にすると、すべての濃さと 0〜255 の組み合わせで拡張精度と同じ値になる
（段階 3 で実XPと0画素差だった値のまま）。ほかの Unix 側のパッチの浮動小数点（0037 の HALFTONE）は画面に差が出なかった。
**判断: 0027（通知アイコン）の XP の形式の大きさは構造体から求める。** `NOTIFYICONDATAW_V3_SIZE` は 64-bit では 976 で、XP の
Explorer が受け取る 952 と違う。handle はもともと 32-bit に詰めている（user の handle は 32-bit に収まる）。
**判断: `create.py` は最初の wineboot の後で wineserver の終了を待ち、`stage.py` は XP の comctl32（v5）も入れ直す。** 新しい
prefix では Wine の起動処理が自分の wineboot も走らせ、試験 VM では create.py が XP の comctl32 を写した後でそれが Wine の
comctl32 を書いた。
**判断: XP の DLL を環境変数で native にするときは `n,b` にする。** WoW64 では 32-bit のプログラムが 64-bit の `start.exe` を経て
起動し直され、`=n` だけだと `start.exe` が 64-bit の native の shell32 を探して起動に失敗する（`prefix/display.py`、文書の試験の例）。

## Linux アプリのスタートメニューと 64-bit のアプリのアイコン（2026-10-11）

**判断: Linux のアプリは desktop entry から、XP のスタートメニューの通常のショートカットにする（`session/linux_apps.py`）。**
XP の Explorer が読むのはファイルシステムの Programs フォルダの .lnk なので、そこに置けば XP の並べ替え、「最近使ったプログラム」、
ドラッグなどがそのまま効く。置き場所は共通の Programs（Linux のアプリはシステム全体のもの）。分類のフォルダを XP の名前で作って
Windows のアプリと混ぜ、名前に ` (Linux)` を付ける（利用者の判断。ほかの候補は「Linux」フォルダの下に分類、「Linux」フォルダに平らに）。
**判断: 起動は GUI のサブシステムの自作の仲介（`linux-launch.exe`）にする。** ショートカットの先を `start.exe /unix` にすると、
コンソールのプログラムなのでコンソールの窓が開く。仲介は `CreateProcessW` で `/usr/bin/env` を起動する（調査 10 の argv[0] の
理由で env を挟む）。`WINEDEBUG` だけは外す。`WINEPREFIX`、`WIN4WINE_EXTERNAL_SHELL`、入力メソッドの変数は残し、Linux の
端末から起動した Windows のアプリも XP シェルから起動したものと同じ環境になる。
**判断: ショートカットは Wine の shell32 の `IShellLinkW` で作り、`winemenubuilder` を止めて保存する。** .lnk を自前で書くより、
Windows の公開 API で作ったものを XP の shell32 が読む形にする。Wine の shell32 は Start Menu の .lnk を保存すると
winemenubuilder で Linux の desktop entry を作るので、そのままでは自分の作った項目を読み返す。`applications/wine` も読まない
（Windows のアプリのインストーラーが作るショートカットの分。試験 VM の Notepad++ で確かめた）。
**判断: 作ったものだけを記録して片付ける。** 同じ名前の利用者のショートカットや、Windows のアプリのフォルダの中身は消さない。
**判断: セッションの `PATH` の先頭にセッションの Wine を置く。** 試験 VM では Wine を `/work/.local/...` に置き、`wine` が
`PATH` に無かった。別の Wine（ディストリビューションのもの）が `PATH` にあると、それが XP の prefix を自分の版に更新してしまう。
**判断: 外部シェルのとき、別のプロセスのウィンドウのクラスのアイコンを `GetClassLongPtr` で返す（0022 に追加）。** XP のタスクバーは
ボタンのアイコンを、相手のプロセスの PEB をたどって得た実行ファイルの名前から `PrivateExtractIconsW` で取り出し、なければ
`WM_GETICON`（ICON_SMALL2、ICON_SMALL、ICON_BIG、SendMessageCallback）と `GetClassLongW(GCL_HICONSM、GCL_HICON)` を使う
（XP Explorer の公開 API の呼び出しの記録、`+relay` の RelayInclude で確かめた。XP の DLL の中は見ていない）。WoW64 の 32-bit の
XP Explorer は 64-bit のプロセスの PEB を読めず（`NtReadVirtualMemory` が `STATUS_ACCESS_DENIED`）、Wine は別のプロセスのクラスの
アイコンを返さないので、64-bit のアプリ（Wine の notepad、Notepad++ の x64 版など）のボタンは既定のアイコンになった（段階 7 からの
後退。段階 6 までは 64-bit のアプリが動かなかった）。Windows と同じくクラスのアイコンを返せば、PEB を読めない場合も正しいアイコンになる。
owner は自分のクラスのアイコンを、ウィンドウを作るときと `SetClassLongPtr` で変えるときに server に渡し（既存の `set_class_info`
の要求。プロトコルは変えない）、server は共有メモリではない側に持つ。アイコンの画素は 0022 の仕組みで読む。opt-in なしでは
渡さないので、server も今までどおり `ERROR_INVALID_HANDLE` を返す。conhost（cmd の窓）はクラスのアイコンに Wine のロゴ
（`IDI_WINLOGO`）を使うので、cmd のボタンは Wine のロゴのまま（Wine の conhost の仕様。conhost.exe にはアイコンの資源も無い）。

## Windows キー、デスクトップのフォーカス、fcitx5 の表示、日本語のコンソール（2026-10-11）

**判断: Windows キーと Ctrl+Esc は XP と同じく `HSHELL_TASKMAN` にする（0023）。** XP の Explorer は RegisterShellHookWindow で
登録したタスク切り替えのウィンドウで `HSHELL_TASKMAN` を受けてスタートメニューを開く（試験 VM でプローブから SHELLHOOK の
メッセージを送って確かめた）。Wine は Windows キー単独も Ctrl+Esc も何もせず、`SC_TASKLIST` も `taskman.exe` を起動するだけ。
XP の Explorer は開くときに `SetForegroundWindow` を呼び、Wine の server は、入力を受けたのが前面のプロセスなら別のプロセスの
前面化を拒む（`+relay` で戻り値 0 を確かめた）。Windows ではシェルがこのキーで前面の権利を得るので、キーを受けたプロセスが先に
タスクバーへ前面を渡す。Windows キーの「単独」は、押下から離しまでにほかのキーのメッセージが無く、離した時点でほかのキーが
押されていないこと。Win+R の R の押下は server がホットキーとして取るが、離しは届く。WM が再送した押下は、Wine の状態ではすでに
押されているので `KF_REPEAT` が付く。そのため繰り返しは自前の状態と時刻で見分ける。
**判断: Linux のアプリにフォーカスがあるときの Windows キーと Ctrl+Esc は、WM が受け取り、proxy が `SendInput` で Wine に入れる。**
X のフォーカスを XP のデスクトップへ移してから再送する方法では、Wine がそのウィンドウを有効にする前にキーが届くと、server が
届け先を見つけられずに捨てた（試験 VM で `+key` と `+relay` で確かめた）。proxy の枠へ移す方法では、Ctrl の押下が Wine に
届いておらず Ctrl+Esc にならず、前面化も、proxy が入力を受けていないときに拒まれた。`SendInput` の入力は前面のスレッドが
新しい入力として受けるので、どちらの問題もない。キーの名前の対応は WM が持つ（文字・数字・F1〜F24 と、XP のホットキーが
使う数個）。
**判断: デスクトップとタスクバーのクリックでフォーカスを渡す。** XP ではデスクトップをクリックするとデスクトップがキーボードを
受ける。WM は desktop と dock の種類にフォーカスを渡していなかった。タスクボタンのクリックは XP 自身が前面を見て最小化か
有効化かを決めるので、クリックでタスクバーにフォーカスが移っても、Linux のアプリのボタンで最小化と復元ができることを確かめた。
**判断: fcitx5 の「入力メソッドの情報」の表示を切る（supervisor が fcitx5 の設定に足す）。** fcitx5 は入力メソッドが変わったときと
フォーカスが移ったときに、カーソルの横へその名前を出す。XIM のクライアント（Wine）では、その窓が中身を描かれないまま黒く
残った（24-bit の窓で、合成は無い）。XP の IME はこのような表示を出さず、入力モードは通知領域のアイコンで分かる。利用者が
fcitx5 の設定でこの2つの値を決めていれば、それに従う。
**判断: 日本語のコンソールは XP と同じく半角の升目にし、2バイトの文字に2升を使う（0041）。** Wine の conhost は DBCS の
コードページでは升目を最も広い文字の幅にしていた（FIXME）。conhost は Wine のプログラムで、Windows 由来のバイナリではない。
升目の扱いを変えると画面の書き込み・描画・編集行・コピーにかかわるので、外部シェルの opt-in で、コンソールの窓のときだけにする
（Unix の端末に出すときは今までどおり）。アプリが `WriteConsoleOutput` で直接書く升目は、アプリが付けた
`COMMON_LVB_LEADING_BYTE` / `TRAILING_BYTE` に従って描く。conhost が IME の確定した文字（キーの無い文字）を捨てていたのも同じ
パッチで直した（opt-in）。

## cmd の字体とセッションのログ（2026-10-11）

**判断: 日本語のコンソールは、実XPの既定と同じ 8×18 の升目に 16px の ＭＳ ゴシック を描く（registry profile 24、0041）。**
実XPの既定は、半角を OEM のラスター字体（`vga932.fon`）、全角を ＭＳ ゴシック から描き、どちらも 16px の ＭＳ ゴシック と同じ画素
になる。ラスター字体は半角の字しか持たず、Wine で全角を別の字体で補うと升目の中の位置が合わないので、字体は ＭＳ ゴシック だけに
し、升目の中の位置を実XPに合わせた。升目の幅を登録で決め、字の大きさを「高さと幅の2倍の小さいほう」にする規則は、実XPの既定
（8×18）と、プロパティで選ぶ大きさ（高さの半分の幅）の両方に合う。`FontSize` の幅は Wine の conhost では使われていなかった。
**判断: 登録の字体の名前は英語名（MS Gothic）にする。** reg.exe のコマンドラインに日本語を渡すと、セッションの外の C ロケールで
動いたときに文字化けするおそれがある。Wine は同じ字体として扱う。
**判断: セッションのログは起動のたびに1世代だけ残す。** ログはセッションの間は追記だけで、Wine のデバッグの出力で増え続ける。
クラッシュのあとの復旧（同じセッションの中）では続けて書くので、直前の失敗のログは残る。

## Linux のトレイアイコン（XEmbed）と Qt の日本語入力（2026-10-11、段階 8）

**判断: XEmbed のトレイは、ほかに X のトレイが無いときだけ tray.py が持つ。** デスクトップ環境のトレイ（stalonetray なども）が
先にあればそちらに任せる。後から別のトレイが選択を取ったら、アイコンをルートへ返して譲る（XEmbed の慣習どおり、アプリは
`MANAGER` を見て入り直す）。SNI の watcher と同じ扱い。
**判断: アイコンの窓は画面に出さず、Composite で画像を読む。** 枠を手動の redirect にすると、どこに置いても画面に描かれず、
DAMAGE で描かれたときだけ起きられる（周期の確認は無い）。画面の外に置くだけでは GetImage の中身が保証されず、隠れた窓の
画素も読めない。
**判断: クリックは XTest で本物の押下を入れる。** GTK 3 は XInput 2 でポインタを受けるので、XSendEvent で送った ButtonPress は
届かなかった（試験 VM で GTK の `button-press-event` が呼ばれなかった）。クリックのあいだだけ、枠をポインタの下に置いて入力の
範囲を戻す。押した直後なのでポインタは XP のアイコンの上にあり、アプリのメニューもアイコンの位置（ポインタの位置）に出る。
押下と離しと範囲の戻しは同じ接続で続けて送るので、利用者の次の入力が枠に入ることは無い。
**判断: 24-bit のアイコンの窓は、Luna の通知領域の色の画素を透明にする。** アルファを持たない窓の背景は tray.py の枠の色に
なる。その色の画素だけを透明にし、縁のなじませは Luna の通知領域の色に寄る（クラシックの灰色の上では縁が少し青い）。GTK 3 と
Qt 5 以降は、知らせた ARGB の visual で透明に描くので当てはまらない。
**判断: ツールチップは窓の名前（無ければクラス）にする。** XEmbed にはツールチップを渡す仕組みが無く、アプリの `set_tooltip` は
アイコンの窓の上にアプリ自身が出すもので、窓を画面に出さないので見えない。
**判断: ルートのカーソルを矢印にする（WM）。** XEmbed のアプリのメニューを開いている間、ポインタが X サーバーの既定の × に
なった。GTK のメニューは自分のカーソルを持たない窓でポインタをつかみ、その窓はルートのカーソルを継ぐ。ふつうの WM と同じく
ルートに矢印を付ける。Linux の窓の上では各アプリのカーソル、Wine の窓の上では XP のカーソルのまま。
**判断: Qt のフロントエンドが無いときは supervisor がログに書くだけにする。** Qt は `QT_IM_MODULE=fcitx` のプラグインが無いと
何も言わずに直接入力だけになる（試験 VM の JuffEd で Ctrl+Space が効かず、ローマ字がそのまま入った）。入っている Qt の版
（`libQt5Core.so.5`、`libQt6Core.so.6`）ごとにプラグインを探し、無ければ fcitx5.log に書く。変数は変えない（fcitx5 の
ibus 互換で代わりに入れる方法もあるが、fcitx5-frontend を入れるのが正しい）。
**判断: 後回しの候補の user32 / win32u の差（DrawText の末尾の `&` とタブの後の下線、区切りの MFS_GRAYED、アイコンの乗算済み
アルファの丸め）は opt-in で XP に合わせる（0037、0032、0041）。** どれも実XPの自作プローブで規則を測った。タブの後の下線は
upstream のコードの数え違いだが、新しい Windows での結果は確かめていないので、ほかの XP に合わせる変更と同じく外部シェルに限る。
アイコンの丸めは uxtheme のテーマ画像（0052）と同じ規則で、user32 のパッチとして文字と画素のまとまりに加えた（番号を振り直した）。
**判断: 待機中の wineserver の 16ms ごとの起床は変えない。** upstream が KUSER_SHARED_DATA の時刻を進めるためのもので、
共有ページから時刻を読むアプリのために必要。CPU は約 0.3%。
**判断: supervisor は周期的に起きず、X のイベント・子プロセスの pidfd・シグナルで待つ。** 段階 1 の WM と同じ方針。起動中の
タスクバーを待つ間だけは、クラスや大きさの変化がこのクライアントに届かない場合に備えて1秒ごとに確かめる。
**判断: registry profile は、当てたときの Wine の更新の印（`.update-timestamp`）と一緒に記録する。** Wine はどのプログラムの起動でも
古い prefix を更新し、シェルの登録を書き戻す。stage.py がその更新を自分で行ったかどうかに頼らず、更新の印が変われば当て直す。
**判断: 非クライアント領域の試験の既知の失敗と TB_GETBUTTONSIZE の差は直さない。** 前者は試験の期待値が XP の描き方ではなく
（実XPでも失敗する）、後者は XP の comctl32 の中の値で、ボタンの配置はすべて実XPと同じ。
## ログイン画面（2026-10-11、段階 9）

**判断: greeter は Python と GTK 3 の自作にし、画面は cairo と Pango で描く。** web-greeter（nody-greeter など）は Debian に
パッケージが無く、WebKit を入れることになる。lightdm-gtk-greeter のテーマ（CSS）では DirectUI の配置や GDI の文字の置き方を
画素単位で合わせられない。LightDM の GObject バインディング（gir1.2-lightdm-1）で認証を進め、GTK は全画面の窓と入力だけに使う。
**判断: XP の logonui.exe と msgina.dll は動かさず、資源だけを読む。** 方針どおり、パスワードを扱う場所で MS のコードを動かさない。
logonui.exe のビットマップと文字列、msgina.dll のダイアログのテンプレートと画像、winlogon.exe の状態の文、luna.msstyles の押し
ボタンの画像を、PE の資源の表をたどって読む（`greeter/xpres.py`。コードは読まない）。文字列も媒体から読むので、リポジトリに
XP の文は入らず、媒体の言語の文になる。logonui.exe の UIFILE（DirectUI の配置の記述）は構造を理解する参考にしたが、数値は
実XPの画面で測ったものを使った（使う数値は `greeter/welcome.py` の定数と `tests/greeter_layout.py`）。
**判断: 文字は GDI の置き方をまねて描く。** Pango の行の高さとベースラインは FreeType の丸め（切り上げ）で、MS UI Gothic 12px では
XP より1px下になる。OS/2 の winAscent・winDescent を四捨五入した値で行を置く。字体に無い太字と斜体は、Pango（fontconfig の
合成）に任せると縦にも太り、傾きも違うので、GDI と同じく1px右に重ねて送りを1px広げ、1/3 傾ける。fontconfig は gasp 表に
合わせ、MS UI Gothic は 24px まで、Arial は 17px までなじませずに描く（XP の標準のスムージングと同じ）。
**判断: 文字列は全角と半角の連なりに分けて Pango に渡す。** MS UI Gothic は BASE 表を持ち、Pango は日本語の後の英字（「(S)」の S、
「Windows」）を別のベースラインに置いて2px上げる。GDI は1本のベースラインに並べるので、連なりごとに配置して同じベースラインに
並べる（字体の代わり（フォールバック）は連なりの中で効く）。
**判断: ログオン中とログオフ中の画面は supervisor が出す（`greeter/xp-splash.py`、python-xlib）。** XP はシェルの準備ができるまで
「ようこそ」を出し、ログオフでは「ログオフしています...」「設定を保存しています...」を出す。greeter はログインした時点で終わる
ので、greeter は最後の画面を root の背景に残し（Esetroot と同じく RetainPermanent のピクスマップ）、supervisor が起動の最初に
「個人設定を適用しています...」の画面を出して、タスクバーが出たら消す。ログオフ（と終了・再起動）の要求ではその画面を出して
文を変え、最後に root の背景に残す。画面は override-redirect の窓で、後から出た窓や上に上げられた窓の上に戻る（周期では
起きない）。設定や画像が無ければ何も出さずに終わり、セッションはそのまま進む。`session.json` の `welcome_screen: false` で止められる。
**判断: greeter と画像は /usr/local/share に写す。** LightDM は greeter を lightdm の利用者で動かすので、利用者のホーム（Debian 13 の
既定は 0700）にあるリポジトリや抽出物を読めない。`greeter/install.sh` がコードと必要なファイルだけを写し、LightDM の設定は
`/etc/lightdm/lightdm.conf.d/95-xp-greeter.conf` の1つだけにする（`--remove` で消せば前の greeter に戻る）。
**判断: 画像が無いときは通常の greeter に切り替える。** greeter は LightDM に接続する前に、設定・必要なファイル・GTK と LightDM の
バインディングを確かめ、足りなければ `fallback`（既定 lightdm-gtk-greeter）を exec する。LightDM の greeter の PATH には sbin が
無いので、/usr/sbin なども探す。
**判断: 利用者の画像は AccountsService（`~/.face`）のものを使い、無ければ beach.bmp。** XP は作ったときに無作為に選ぶが、XP の
prefix はスタートメニューに beach.bmp を出すので、ログイン画面もそれに合わせる（`greeter.json` の `picture` で変えられる）。
抽出で XP の既定の画像 23 枚も取り出す。
**判断: 終了オプションのボタンは LightDM の suspend・shutdown・restart を呼ぶ。** スタンバイは LightDM が可能と言うときだけ使える。
休止状態（Shift）は作らない。
**判断: 暗くなる背景は XP の最後の状態の一次式で近似し、約1秒後から 2.5 秒かけて重ねる。** XP の途中の状態は上から順に変わる
帯で、色の変化も一次式ではない（最大 11 の差）。
**判断: 参照用 XP の画面の大きさと利用者は、測るときだけ変えて戻した。** ようこそ画面にパスワードのある・ないアカウントを
並べるため、試験用の利用者を作った。測った後に消し、画面を 640×480 に戻した。
**判断（段階 9 の続き）: XP シェルの「Windows のログオフ」の背景は、win32u のパッチ（0043）で XP と同じにする。** XP の shell32 は
背景ブラシの無い全画面の窓を表示し、自分の DC から帯ごとに読んで灰色にする。実XPでは、そういう窓は描くまで下の画面が見え、
その DC からも読める（表示前の窓の DC も画面を読む）。Wine は新しい窓の面を白で始めていた。shell32（MS のバイナリ）は変えず、
外部シェルのときだけ、ブラシの無いトップレベルの窓を表示する時にその下の画面を面に写し、表示前の窓の DC は画面を読むようにした。
**判断（段階 10 の後で変更）: スタートメニューの選択項目のフェード（shell32 の SysFader）は灰色の背景に写さない（0043）。**
ログオフや終了オプションを選ぶと、shell32 が選んだ項目をレイヤード窓でフェードさせ、灰色の窓が出る時にもまだ表示されている。
Windows の画面の読み取りはレイヤード窓を含まないが、Wine は X の画面から読むので含み、左下に「ログオフ」「終了オプション」が
残っていた。X には下の窓の画素が無いので、背景を写すときに、表示中のレイヤード窓の部分を、その下にある同じプロセスの窓
（デスクトップ、タスクバーなど。explorer の窓）の surface から下から順に描き直す。その部分に別のプロセスの窓（Linux のアプリの
枠など）がある場合は描き直さず、これまでどおり写る。選択項目のフェード自体は XP と同じく残す。
**判断: カーソルは、利用者の XP の user32.dll から作った X のカーソルテーマにする。** winex11 は Windows の標準カーソルを X の
テーマのカーソル（left_ptr、xterm、hand2 など）で出すので、テーマを XP の画像にすれば Wine のパッチは要らず、Linux のアプリと
greeter も同じカーソルになる（XP の上ではすべての窓が同じカーソル）。user32.dll は資源（カーソル）だけを読み、prefix に写されない
`resources/` に抽出する。XP の影は実XPの矢印から当てはめた規則（右に3・下に1、[1,2,3,2,1] のぼかし、0.318）で画像に入れた。
画面を反転するカーソル（I ビーム、十字、大きさの変更）は X では反転できないので、白い背景で XP と同じ見た目になる黒に白い縁を
付けた（黒い端末の上でも見える）。テーマは `greeter/install.sh` が `/usr/share/icons/win4wine-xp` に入れ（libXcursor が探す場所）、
greeter と XP シェルのセッションが `XCURSOR_THEME` で使う。WM のルートのカーソルはカーソルの字体からなので、セッションの
最初に xsetroot でテーマの矢印にする。

## DPI の拡大（2026-10-12、段階 10）

**判断: DPI は XP と同じく LogPixels で決め、外部シェルのプロセスは system DPI aware にする（0044）。** XP には DPI 仮想化が無く、
どのアプリも LogPixels の DPI で自分で描く。Wine は DPI 対応を宣言しない（マニフェストの無い）アプリを 96 DPI で描いて画像のまま
拡大するので、XP のシェルとアプリがぼけていた。opt-in のプロセスは AppCompatFlags の指定が無ければ system aware になる
（XP にはマニフェストの dpiAware が無いので、マニフェストでは変えない）。レジストリの AppCompatFlags の既定値でも同じことが
できるが、prefix の中の opt-in でないプロセスにも効くので、win32u のパッチにした。
**判断: アイコンとカーソルの寸法は実XPで測った規則にする（0044）。** 参照用 XP を 96、108、120、132、144、168、192、216 DPI に
して GetSystemMetrics を測った（`tests/dpi-metrics.c`）。SM_CXICON はどの DPI でも 32（シェルの画像リストも 32 と 16）。
SM_CXSMICON は「メニューのボタン幅（iMenuWidth）−2 を偶数に切り下げた値」で、DPI を何度も変えるとメニュー幅とともに 1px ずつ
変わる（XP は DPI を変えるたびに WindowMetrics を新旧の DPI の比で掛け直して保存し、丸めがたまる）。SM_CXCURSOR は 144 DPI
まで 32、168 DPI から 64。Wine は DPI に比例させていた（120 DPI で SM_CXICON 40 など）。
**判断: Wine のメトリクスとフォントの拡大は Wine のまま（96 DPI の値を MulDiv で拡大）にする。** 実XPを 96 DPI でテーマを適用して
から画面のプロパティで 144 DPI にした状態（利用者が DPI を変える普通の手順）と、Wine の値は一致した（caption 38、メニュー幅 27、
スクロールバー 26、枠 2、フォント -20 など）。XP でその後にテーマを選び直すと枠は 1 に戻るが、それは選び直したときだけの状態として
扱う。DPI を何度も変えた XP の値（丸めがたまる）には合わせない。
**判断: 文字の送り幅は、ヒンティングで変わらないものを1回だけ丸める（0036）。** MS UI Gothic の 15px（120 DPI のメニューの字体）
の A・E・V・Z は設計値 9.49・8.50 で、XP は 9・8、Wine（FreeType）は 26.6 固定小数点に丸めてから画素に丸めて 10・9 にしていた。
メニューバーの「(E)」「(V)」などで項目が 1px ずつずれていった。ヒンティングで送り幅が変わる字体（hdmx を持つ Tahoma など）は
FreeType の値のまま。12〜24px の通常体と太字で XP と全て一致した（`tests/char-widths-dpi.c`）。
**判断: Start ボタンの画像は XP の Button と同じく DPI で拡大する（0046）。** XP の explorer は 25×20 のビットマップの画像リストを
そのまま渡し、XP の comctl32 の Button が ILD_DPISCALE で描く（120 DPI で 31×25、144 DPI で 37×30、切り捨て）。Wine の Start ボタンは
画像リストの大きさのまま描き、幅が XP より 6px 狭かった。描画は XP の comctl32 の ImageList_DrawIndirect（ILD_DPISCALE）に任せる。
**判断: caption のボタン、題名の字体と影は XP の規則にする（0049）。** XP の Luna の caption ボタンは SM_CYSIZE−4 の正方形（96 DPI の
21、120 DPI の 27、144 DPI の 34）で、間隔と枠からの余白は DPI によらず 2px。ボタンの記号は描く大きさで画像を選ぶ
（ImageSelectType=size、26px までは 13px の記号、27px からは 19px）ので、ボタンが 1px 小さいと記号が細くなる。題名はテーマの 10pt を
その場で換算すると 120 DPI で 17px になるが、XP は SPI の caption の字体（16px）で描く。影の矩形を左と上だけ動かしていたので、
上下中央揃えで影の縦のずれが半分になり、120 DPI の caption では影が真横に出ていた（96 DPI は高さの偶奇で偶然 1px だった）。
**判断: Linux のアプリには同じ DPI を `Xft.dpi` と fontconfig で渡し、GTK は 192 DPI 以上だけ整数倍にする（`session/dpi.py`）。**
XP は文字と寸法を拡大し、アイコンは 32 のままにする。GTK 3 と Qt 5 は `Xft.dpi` で文字だけを拡大するので、XP の拡大のしかたに近い。
GTK 3 の部品は整数倍しかできないので、2 倍以上のときだけ `GDK_SCALE` と `GDK_DPI_SCALE` で部品も拡大する。Qt 6 と Chromium は
`Xft.dpi` から自分で全体を拡大する（それぞれの仕様のまま）。カーソルの大きさ（`XCURSOR_SIZE`）は XP の SM_CXCURSOR と同じ規則。
**判断: 64 のカーソルは 32 の各画素を 2 倍にし、影は 32 と同じにする（`greeter/cursors.py`）。** 実XPの 192 DPI の矢印は 32 の画像の
最近傍の 2 倍で、影は 32 と同じ位置（3px 右、1px 下）とぼかし（[1, 2, 3, 2, 1]）、濃さ 0.318 で一致した（最大誤差 0.002）。
カーソルテーマに 32 と 64 の両方の画像を入れ、X が `XCURSOR_SIZE` で選ぶ。
**判断: ようこそ画面とログオン・ログオフの画面は DPI で拡大し、XP で拡大しない部品はそのままにする（`greeter/welcome.py`）。** 実XPの
144 DPI では、帯の高さ、パネルの幅、ユーザーの欄、画像（ユーザーの画像と枠、電源ボタン、左上の光）と文字が DPI で拡大され、
Windows のロゴ、案内文の折り返しの幅（344px）、吹き出し（文字と大きさ）は 96 DPI のまま。右のパネルの境目は「画面の幅の半分−2」
から、パネルが広がった分の半分だけ左にずれる。ユーザーの画像の枠の位置（7px）と文字の内側の余白（2px）も拡大しない。日本語の
折り返しは文字の種類（漢字・ひらがな・カタカナ）が変わる所だけで行う（XP は「...クリック」「してください。」で折り返す）。
ようこそ画面の DPI はマシン全体の設定として `/etc/win4wine/greeter.json` の `dpi` で決め、ログオン・ログオフの画面は supervisor が
prefix の DPI を渡す。
**判断: 次の差は残す。** いずれも 96 DPI から同じ差がある（DPI に固有ではない）か、XP の挙動が状態によって変わるもの。
- 合成の斜体（Start ボタンの「スタート」など）は、GDI の白黒の描画で 96 DPI から XP と字形が違う（`tests/text-bits-dpi.c`）。
- SM_CXSIZE（XP は Luna で caption の高さと同じ、Wine は 18 を拡大）、メニューの高さ（XP 19、Wine 18）、アイコンの間隔（XP 79、
  Wine 78）、SM_CYMAXIMIZED、DEFAULT_GUI_FONT の名前（XP は MS UI Gothic、Wine は MS Shell Dlg）。ボタンの配置は 0049 が
  決めるので見た目には出ない。
- XP は 120 DPI 以上でラスターフォント（SYSTEM_FONT など）を 8514 系に替えるが、XP の .fon は抽出していないので Wine の VGA 系の
  ままになる。システムフォントを使う古い形式のダイアログでだけ見える。
- ようこそ画面の 120・144 DPI で、名前と画像の枠の端、案内文が 1px、吹き出しのエラーのアイコン（XP は約 32px）。パスワード欄と
  矢印のボタンは XP と同じ位置と大きさ（欄の高さは 96 DPI の 29 の拡大より 1px 低い。120 DPI で 35、144 DPI で 43）。

## ARM64 の Box64 と FEX（2026-11、AYN Thor、外部からの報告）

AYN Thor（Snapdragon 8 Gen 2、Fedora 44 系の OS）で、x86-64 の Debian 13 でビルドした Wine 11.0（このリポジトリのパッチ、新しい
WoW64）を動かした。OS の FEX では `wine --version` は `wine-11.0` を返したが、作った prefix の `syswow64` に 32 ビットの DLL が
揃わず、32 ビットのプログラムを直接動かす試験も失敗した。`wineboot -u` でも揃わなかった。`msvcrt.dll` の「file probably
truncated」、import の不足、`InternetOpenW` の未実装などのエラーも出たが、DLL の SHA-256 はビルドしたものと一致したので、転送や
ビルドの破損ではない。x86-64 から 32 ビットへの WoW64 の切り替えが疑わしいが、FEX の不具合とまでは絞り込んでいない。FEX の版と
設定はその OS のもので、ARM64 の Wine と FEX の組み合わせ、Proton、従来の multilib の Wine は試していない。
同じ Wine を Box64 0.4.5 で動かすと `syswow64` が揃い、`prefix/reactos.py` で作った新しい prefix で ReactOS のシェルが動いた。
後に英語版の XP と英語版の Windows 7 のシェルも動いた。Box64 には `BOX64_LD_LIBRARY_PATH` で x86-64 の Debian の
`usr/lib/x86_64-linux-gnu` を渡す必要があった（無いと `libgcc_s.so.1` が見つからない）。
**判断: ARM64 では Box64 を使い、win4wine のコードは変えない（`scripts/box64-wine.sh`）。** session.json の `wine` は、Box64 を
通す `wine` と `wineserver` のスクリプトを置いたディレクトリの `bin/wine` を指す。セッションと prefix の道具は `wine` のパスを
たどって、同じディレクトリの wineserver と、その上の `lib/`・`share/` を使い、そのディレクトリを PATH の先頭に置くので、それで
足りる。スクリプトはリンクにしない（`resolve()` が x86-64 の Wine の本体にたどり着き、Box64 を通らない）。
