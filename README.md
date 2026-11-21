# BT HID KVM

讓一台 Linux 電腦假裝成藍牙鍵盤滑鼠。按住左 Win，就能用這台的鍵盤滑鼠操作另一台電腦。

它就像 KVM 切換器的按鈕：按住時，鍵盤滑鼠接到另一台；放開就回到自己這台。

```text
按住左 Win：鍵盤滑鼠 ──► 本機（App）──送到──► host
放開左 Win：鍵盤滑鼠 ──► 本機（App）──留在──► 本機
```

本機是執行 App 的 Linux 電腦，host 是被控制的電腦，Linux 或 Windows 都可以。host 不用安裝任何程式，它只會看到一組藍牙鍵盤滑鼠。

> 注意：App 執行期間會獨占並轉送所有實體鍵盤；連線中，左 Win 不會傳到本機。

## 系統需求

- 執行 App 的電腦（本機）
  - Linux + BlueZ，支援 Classic 藍牙（BR/EDR）
  - 實測環境：Ubuntu 26.04、KDE Plasma 6.6.6（Wayland）、BlueZ 5.85
  - [uv](https://docs.astral.sh/uv/)（實測 0.12.18）和系統 Python `/usr/bin/python3.14`，下方的系統套件也要裝好
  - 你的帳號在 `input` 群組，`/dev/uinput` 也屬於 `input` 群組（見[權限設定](docs/guide.md#權限設定)）
  - 要控制 Windows host 的話，bluetoothd 要停用 input 外掛（見[讓 Windows host 連得進來](docs/guide.md#讓-windows-host-連得進來)）
- 被控制的電腦（host）
  - 支援 Classic 藍牙 HID 的系統。實測過 Linux + BlueZ 和 Windows 11

## 安裝與啟動

```bash
sudo apt install build-essential pkgconf python3-dev python3-tk libdbus-1-dev libglib2.0-dev libgirepository-2.0-dev libcairo2-dev libffi-dev gir1.2-glib-2.0
sudo usermod -aG input "$USER"   # 重新登入後生效
uv sync && uv run bt-hid-kvm     # 在 repo 根目錄執行
```

`evdev`、`dbus-python`、`PyGObject` 在 PyPI 沒有 Linux 的預編譯版本，`uv sync` 會在 `.venv` 裡從原始碼編譯，所以要先裝這些系統套件：

| 系統套件 | 用途 |
|---|---|
| `build-essential`、`pkgconf`、`python3-dev` | 編譯 Python 套件的工具和 Python 標頭檔 |
| `libdbus-1-dev`、`libglib2.0-dev` | 編譯 `dbus-python` |
| `libgirepository-2.0-dev`、`libffi-dev` | 編譯 `PyGObject` |
| `libcairo2-dev` | 編譯 `pycairo`（`PyGObject` 需要它） |
| `python3-tk` | 視窗用的 tkinter，PyPI 裝不到 |
| `gir1.2-glib-2.0` | 執行時 `from gi.repository import GLib` 要讀的 typelib |

`.python-version` 把專案鎖在系統的 `/usr/bin/python3.14`，因為 uv 自己下載的 Python 沒有藍牙 socket（`socket.AF_BLUETOOTH`）。

**一定要透過這個 App 配對，才能正常使用。** 用系統的藍牙設定配對的話，host 只會把本機當成一般電腦，不會出現鍵盤滑鼠。

第一次使用前，在 App 按「配對」，兩台核對配對碼後各按一次確認，host 不用開啟可被搜尋。步驟見[第一次配對](docs/guide.md#第一次配對)。

想要單一執行檔的話，在 repo 根目錄執行 `make`，會產生 `dist/BT_HID_KVM-x86_64.AppImage`，細節見[打包成 AppImage](docs/guide.md#打包成-appimage)。

## 先試試看

配對好之後，在 repo 根目錄執行。`<host 的 MAC>` 就是 App「目標」清單裡括號中的那串：

```bash
uv run bt-hid-kvm --selftest --mac <host 的 MAC>
```

host 的游標會畫一個約 200px 的正方形（右 → 下 → 左 → 上），再按一下 Shift，然後程式自己結束。

## 要按哪顆鍵

觸發鍵是 `KEY_LEFTMETA`（左 Win）。同一顆實體鍵送出的代碼，會隨鍵盤模式改變：

| 鍵盤模式 | 要按的鍵 |
|---|---|
| Windows／PC 模式 | 左下角第 2 顆（Win） |
| Mac 模式（例如 Keychron 切到 Mac） | 左下角第 3 顆（Command） |

不確定是哪顆的話，照[按觸發鍵沒反應](docs/guide.md#按觸發鍵沒反應)查一下。

## 日常使用

1. 啟動 App，「目標」會自動選第一台已配對的電腦。按「連線」，狀態會變成「已連線」；Windows host 剛配對完會自己連上
2. 按住觸發鍵：色塊變成綠色並顯示 host 的名稱，鍵盤滑鼠都送到 host
3. 放開觸發鍵：色塊變回灰色「本機」

不想一直按住的話，勾選「切換模式」：按一下觸發鍵切到 host，再按一下切回本機。App 下次開啟時會記住這個設定。

三件事一定要記得：

- 一定要用 `uv run bt-hid-kvm` 啟動。直接用 asdf、pyenv 的 Python 執行，可能沒有藍牙 socket
- host 重開機或藍牙斷線後，要在 App 再按一次「連線」
- App 開著時才插上的鍵盤滑鼠，要重開 App 才會被攔截

## 安全性

- 連線要求加密（`BT_SECURITY_MEDIUM`），host 連進來的連線也一樣；Linux host 的 BlueZ 預設也只接受已配對裝置的 HID 連線（`ClassicBondedOnly=true`）
- App 會讀取所有實體鍵盤輸入，但不記錄按鍵；log 只寫連線和模式訊息
- host 會把本機當成鍵盤滑鼠，所以能操作本機的人，連線時也能操作 host

## 了解更多

[docs/guide.md](docs/guide.md) 包含：

- 名詞解釋
- 權限設定、讓 Windows host 連得進來、第一次配對
- 同一台 host 裝了 Linux 和 Windows（雙系統）時怎麼共用配對
- 視窗畫面，以及切換模式時發生什麼事
- 所有指令參數與設定值；`constants` 裡的 UUID 是 App 的名字，不是寫死的硬體值（[UUID 是寫死的嗎](docs/guide.md#uuid-是寫死的嗎)）
- 運作方式：HID 連線與按鍵攔截
- 疑難排解與已知限制
- 開發與測試
- 打包成 AppImage

## 授權

尚未指定授權。
