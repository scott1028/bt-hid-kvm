# BT HID KVM

讓一台 Linux 電腦假裝成藍牙鍵盤滑鼠。按住左 Win，就能用這台的鍵盤滑鼠操作另一台電腦。

它就像 KVM 切換器的按鈕：按住時，鍵盤滑鼠接到另一台；放開就回到自己這台。

```text
按住左 Win：鍵盤滑鼠 ──► 265K（App）──送到──► 288V
放開左 Win：鍵盤滑鼠 ──► 265K（App）──留在──► 265K
```

265K 是執行 App 的電腦，288V 是被控制的電腦。288V 不用安裝任何程式，它只會看到一組藍牙鍵盤滑鼠。

> 注意：App 執行期間會獨占並轉送所有實體鍵盤；連線中，左 Win 不會傳到本機。

## 系統需求

- 執行 App 的電腦（265K）
  - Linux + BlueZ，支援 Classic 藍牙（BR/EDR）
  - 實測環境：Ubuntu 26.04、KDE Plasma 6.6.6（Wayland）、BlueZ 5.85
  - 系統 Python `/usr/bin/python3`（實測 3.14），而且要支援 `socket.AF_BLUETOOTH`
  - 套件：`python3-evdev`、`python3-dbus`、`python3-gi`、`python3-tk`
  - 你的帳號在 `input` 群組，`/dev/uinput` 也屬於 `input` 群組（見[權限設定](docs/guide.md#權限設定)）
- 被控制的電腦（288V）
  - 支援 Classic 藍牙 HID 的系統。目前只實測過 Linux + BlueZ

## 安裝與啟動

```bash
sudo apt install python3-evdev python3-dbus python3-gi python3-tk
sudo usermod -aG input "$USER"   # 重新登入後生效
PYTHONPATH=.. /usr/bin/python3 -m bt_hid_kvm   # 在 repo 根目錄執行
```

程式是以 `bt_hid_kvm` 套件執行的，所以 repo 資料夾名稱要是 `bt_hid_kvm`。`PYTHONPATH=..` 讓 Python 從上一層目錄找到這個套件。

第一次使用前，兩台要在 App 執行時重新配對一次，步驟見[第一次配對](docs/guide.md#第一次配對)。

## 先試試看

配對好之後，在 repo 根目錄執行：

```bash
PYTHONPATH=.. /usr/bin/python3 -m bt_hid_kvm --selftest
```

288V 的游標會畫一個約 200px 的正方形（右 → 下 → 左 → 上），再按一下 Shift，然後程式自己結束。

## 要按哪顆鍵

觸發鍵是 `KEY_LEFTMETA`（左 Win）。同一顆實體鍵送出的代碼，會隨鍵盤模式改變：

| 鍵盤模式 | 要按的鍵 |
|---|---|
| Windows／PC 模式 | 左下角第 2 顆（Win） |
| Mac 模式（例如 Keychron 切到 Mac） | 左下角第 3 顆（Command） |

不確定是哪顆的話，照[按觸發鍵沒反應](docs/guide.md#按觸發鍵沒反應)查一下。

## 日常使用

1. 啟動 App，按「連線」，狀態會變成「已連線」
2. 按住觸發鍵：色塊變成綠色「288V」，鍵盤滑鼠都送到 288V
3. 放開觸發鍵：色塊變回灰色「本機」

三件事一定要記得：

- 一定要用 `/usr/bin/python3`。asdf、pyenv 這類自行編譯的 Python 可能沒有藍牙 socket
- 288V 重開機或藍牙斷線後，要在 App 再按一次「連線」
- App 開著時才插上的鍵盤滑鼠，要重開 App 才會被攔截

## 安全性

- 連線要求加密（`BT_SECURITY_MEDIUM`）；288V 的 BlueZ 預設也只接受已配對裝置的 HID 連線（`ClassicBondedOnly=true`）
- App 會讀取所有實體鍵盤輸入，但不記錄按鍵；log 只寫連線和模式訊息
- 288V 會把 265K 當成鍵盤滑鼠，所以能操作 265K 的人，連線時也能操作 288V

## 了解更多

[docs/guide.md](docs/guide.md) 包含：

- 名詞解釋
- 權限設定與第一次配對
- 視窗畫面，以及切換模式時發生什麼事
- 所有指令參數與設定值
- 運作方式：HID 連線與按鍵攔截
- 疑難排解與已知限制
- 開發與測試

## 授權

尚未指定授權。
