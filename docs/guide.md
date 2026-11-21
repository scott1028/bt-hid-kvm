# BT HID KVM 使用指南

這份指南依照你實際會走的順序寫：先設定，再日常使用，最後是參考資料。最短的上手路徑在 [README](../README.md)。

## 名詞解釋

| 名詞 | 白話解釋 |
|---|---|
| 本機 | 執行 App 的 Linux 電腦，它的鍵盤滑鼠會被送到 host |
| host | 被控制、接收 HID 輸入的電腦，Linux 或 Windows 都可以 |
| HID | Human Interface Device，鍵盤滑鼠這類輸入裝置用的協定。host 收到 HID 報告，就當成有人在按鍵、動滑鼠 |
| BlueZ | Linux 的藍牙協定堆疊，背景服務是 `bluetoothd` |
| input 外掛 | `bluetoothd` 內建的 Classic 藍牙 HID host 功能，讓本機能用藍牙鍵盤滑鼠和手把。它會占住 PSM 17 和 19 |
| SDP 記錄 | 藍牙裝置對外公布「我提供哪些服務」的名片。host 配對時會讀它，才知道本機是鍵盤滑鼠 |
| L2CAP PSM | 藍牙連線用的通道編號，類似 TCP 的 port。HID 用 PSM 17（control）和 PSM 19（interrupt） |
| 連結金鑰（link key） | 配對成功後，兩台各存一份的同一把密碼。之後每次連線都用它加密，對不上就連不進去 |
| evdev | Linux kernel 的輸入事件介面，也就是 `/dev/input/event*` |
| 獨占（grab） | `EVIOCGRAB`：只讓 App 收到某個裝置的事件，桌面收不到 |
| uinput | 讓程式建立虛擬輸入裝置的 kernel 介面，也就是 `/dev/uinput` |
| uv | Python 的專案管理工具。`uv sync` 依 `pyproject.toml` 和 `uv.lock` 建好 `.venv`，`uv run` 用這個環境執行指令 |
| agent | BlueZ 配對時負責問使用者的程式，例如跳出配對碼請你確認。App 有自己的 agent |
| 可被搜尋 / 可連線 | 可被搜尋（discoverable）：別人掃描時看得到你。可連線（connectable）：別人知道你的 MAC 就能直接連。藍牙開著時通常一直可連線 |

## 權限設定

App 不需要 root，但要能讀 `/dev/input/event*`、寫 `/dev/uinput`。先檢查兩件事：

```bash
id -nG | grep -w input   # 有印出 input 才算在群組裡
ls -l /dev/uinput        # 群組要是 input，權限要是 crw-rw----
```

不在 `input` 群組的話，執行 `sudo usermod -aG input "$USER"`，然後重新登入。

`/dev/uinput` 的群組不是 `input` 的話，加一條 udev 規則，重開機後生效：

```bash
echo 'KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"' | sudo tee /etc/udev/rules.d/80-uinput.rules
```

實測機器上的這條規則，來自 `ydotool` 套件的 `/usr/lib/udev/rules.d/80-uinput.rules`，不是系統內建。

## 讓 Windows host 連得進來

只控制 Linux host 的話可以跳過這節。Windows 配對完會自己連到本機的 PSM 17 和 19，但這兩個通道被本機的 input 外掛占著。input 外掛不認得 Windows，會拒絕連線，還順手送出「拔掉虛擬線」（`VIRTUAL_CABLE_UNPLUG`），Windows 收到就把鍵盤滑鼠移除了。

```text
停用前：Windows ──連 PSM 17/19──► input 外掛 ──拒絕並送 unplug──► Windows 移除鍵盤滑鼠
停用後：Windows ──連 PSM 17/19──► bluetoothd ──交給──► App
```

停用 input 外掛後，`bluetoothd` 就能替 App 監聽這兩個通道。在本機執行一次：

```bash
systemctl cat bluetooth | grep ExecStart   # 確認 bluetoothd 的路徑；Ubuntu 是 /usr/libexec/bluetooth/bluetoothd
sudo mkdir -p /etc/systemd/system/bluetooth.service.d
printf '[Service]\nExecStart=\nExecStart=/usr/libexec/bluetooth/bluetoothd -P input\n' | sudo tee /etc/systemd/system/bluetooth.service.d/bt-hid-kvm.conf
sudo systemctl daemon-reload && sudo systemctl restart bluetooth
```

路徑不一樣的話，把 `printf` 那行的路徑換成第一行查到的。重新啟動 `bluetoothd` 時，本機的藍牙裝置會短暫斷線。成功的話，`journalctl -u bluetooth -b` 會出現 `Excluding (cli) input`。

三件事一定要記得：

- 本機從此不能用 Classic 藍牙的鍵盤、滑鼠、手把（例如 Switch Pro Controller）。藍牙 LE 的裝置和耳機不受影響
- 要復原的話，刪掉 `/etc/systemd/system/bluetooth.service.d/bt-hid-kvm.conf`，再執行最後一行
- 沒停用時 App 照常啟動，Linux host 也照常能用，只是 Windows 連不進來。`bluetoothd` 的 log 會出現 `L2CAP server failed for bt_hid_kvm control: l2cap_bind: Address already in use (98)`

## 第一次配對

一定要透過這個程式配對（GUI 的「配對」，或下面的 `--selftest` 指令流程），才能正常使用。用系統的藍牙設定配對時，App 通常沒在跑，配對就不會帶到鍵盤滑鼠的資訊。

host 只在配對時讀本機的 SDP 記錄。如果配對時 App 沒在跑，host 記到的本機只是一台電腦，不會建立鍵盤滑鼠。所以要先讓 App 註冊好 SDP 記錄，再重新配對。

App 一啟動就會註冊 SDP 記錄，所以直接在 App 裡按「配對」最省事。它不用掃描：掃描像在人群裡喊「誰在？」，要等 host 舉手（開啟可被搜尋）；「配對」則像直接撥 host 的電話號碼，只要 host 的藍牙開著就接得到。

```text
Time ──────────────────────────────────────────────────────────────►

本機 | 啟動 App   | 按「配對」 | 核對數字，按「相同」 | 按「連線」（Windows 免按）
-----|------------|------------|----------------------|---------------------------
host | 移除舊配對 | 回應連線   | 核對數字，按確認     | 讀 SDP，建立 HID
```

兩邊會顯示同一組 6 位數字，一樣才按確認。host 不用開啟可被搜尋。

**1. 在 host 上**，移除舊的配對，準備好接受配對：

- Linux host：如果藍牙清單裡還有本機，先執行 `bluetoothctl remove <本機的 MAC>`。`<本機的 MAC>` 可以在本機上用 `bluetoothctl show` 查
- Linux host 要有 agent 負責跳出配對確認。KDE、GNOME 這類桌面通常內建；不確定的話，進 `bluetoothctl` 執行下面幾行，視窗保持開著：

```text
pairable on
agent KeyboardDisplay
default-agent
```

- Windows host：在「設定 → 藍牙與裝置 → 裝置」裡，如果有本機的名稱，先移除裝置。Windows 會自己跳出配對確認，不用另外準備

**2. 在本機上**，在 repo 根目錄啟動 App，在「目標」選 host，再按「配對」：

```bash
uv run bt-hid-kvm
```

還沒配對過的 host 不會在清單裡。直接輸入它的 MAC，或讓它開啟可被搜尋後按「掃描」。

**3. 核對配對碼**：App 視窗會出現「配對碼 123456：對方電腦顯示的數字一樣嗎？」，host 也會顯示一組數字。

- 數字一樣：在 App 按「相同」，host 那邊也按確認（在 `bluetoothctl` 裡就是輸入 `yes`）
- 數字不一樣：按「不同」，這次配對就會取消

完成後狀態會變成「已配對 <MAC>，可以連線」。

**4. 連線**：

- Windows host 配對完會自己連上，狀態直接變成「已連線 <MAC>」，不用按「連線」
- Linux host 要按「連線」。第一次可能出現 `Connection refused`，因為 host 還在讀 SDP 記錄，等幾秒再按一次

**5. 確認結果**：按住觸發鍵動一下滑鼠，host 的游標有動就成功了。Linux host 也可以執行 `bluetoothctl info <本機的 MAC>`，清單裡要有 `UUID: Human Interface Device...` 這一行。之後兩台都不用再配對。

三件事一定要記得：

- 按「配對」會先移除本機這邊的舊配對，已經能用的話不要按。雙系統的 host 尤其不要，見[同一台 host 裝了 Linux 和 Windows](#同一台-host-裝了-linux-和-windows)
- 已連線時「配對」會停用，要先按「中斷」
- 看到 `pair failed: [Errno 112] Host is down`，見[按「配對」出現 Host is down](#按配對出現-host-is-down)

### 用指令配對（不開 GUI，Linux host）

不開 GUI 時（例如只想用 `--selftest` 驗證），可以在終端機配對。這個方式靠本機掃描，所以 host 要開啟可被搜尋。

```text
Time ─────────────────────────────────────────────────────────────────►

本機 | 移除舊配對 | 啟動 --selftest（註冊 SDP） | 發起配對 | 連線並畫正方形
-----|------------|-----------------------------|----------|---------------
host | 移除舊配對 | 開啟可被搜尋                | 確認配對 | 游標畫出正方形
```

兩台的動作要照時間順序做。`--selftest` 會一直等到配對完成，才去連線。

**1. 在 host 上**，進 `bluetoothctl` 執行下面幾行。`<本機的 MAC>` 可以在本機上用 `bluetoothctl show` 查，就是 `Controller` 後面那串：

```text
remove <本機的 MAC>
pairable on
discoverable on
agent KeyboardDisplay
default-agent
```

這個 `bluetoothctl` 視窗要保持開著，等一下要在這裡輸入 `yes` 確認配對碼。`discoverable on` 預設 180 秒後會自動關掉。

**2. 在本機上**，在 repo 根目錄執行。`<host 的 MAC>` 可以在 host 上用 `bluetoothctl show` 查：

```bash
bluetoothctl remove <host 的 MAC>
uv run bt-hid-kvm --selftest --mac <host 的 MAC> &
bluetoothctl
```

最後一行會進入 `bluetoothctl`，再依序輸入：

```text
agent KeyboardDisplay
default-agent
scan on
pair <host 的 MAC>
trust <host 的 MAC>
```

- 輸入 `pair` 之前，要先等 `scan on` 列出 host
- 配對時兩邊都會問 `Confirm passkey ... (yes/no)`。確認兩邊數字一樣，再各輸入 `yes`
- 配對完成後，背景的 `--selftest` 會自動連線，讓 host 的游標畫出正方形

**3. 確認結果**：在 host 執行 `bluetoothctl info <本機的 MAC>`，清單裡要有這一行：

```text
UUID: Human Interface Device... (00001124-0000-1000-8000-00805f9b34fb)
```

最後在 host 的 `bluetoothctl` 執行 `discoverable off`。之後兩台都不用再配對。

## 同一台 host 裝了 Linux 和 Windows

雙系統的 host，兩個系統用同一個藍牙 MAC，本機對一個 MAC 只存一把連結金鑰。所以最後配對的那個系統能用，另一個系統的金鑰對不上，就連不進去。解法是讓兩個系統用同一把金鑰：在 Windows 配對，再把這把金鑰複製到 host 的 Linux。

```text
Windows 配對 ──產生金鑰──► 本機和 host 的 Windows 各存一份
本機的金鑰檔 ──複製 Key、Type──► host 的 Linux
```

1. host 開進 Linux，照[第一次配對](#第一次配對)配對一次，讓 Linux 記下本機是鍵盤滑鼠
2. host 開進 Windows，先移除本機，再透過 App 配對。這是最後一次配對
3. 在本機讀出金鑰，記下 `Key=` 和 `Type=` 兩行。`<本機的 MAC>` 用 `bluetoothctl show` 查，MAC 都用大寫：

```bash
sudo sed -n '/^\[LinkKey\]/,/^$/p' /var/lib/bluetooth/<本機的 MAC>/<host 的 MAC>/info
```

4. host 開進 Linux，換掉同一個檔案裡的兩行。`bluetoothd` 會改寫這個檔案，所以要先停掉它：

```bash
sudo systemctl stop bluetooth
sudo sed -i -e 's/^Key=.*/Key=<第 3 步的 Key>/' -e 's/^Type=.*/Type=<第 3 步的 Type>/' /var/lib/bluetooth/<host 的 MAC>/<本機的 MAC>/info
sudo systemctl start bluetooth
```

三件事一定要記得：

- 之後不要再按 App 的「配對」。按了會產生新金鑰，要重做第 2 到第 4 步
- 第 4 步找不到檔案，代表 host 的 Linux 沒有本機的配對，先做第 1 步
- 這些步驟依 BlueZ 的金鑰檔格式寫成，還沒在雙系統上實測

## 視窗畫面

在 repo 根目錄執行 `uv run bt-hid-kvm` 後，會出現標題為「BT HID KVM」的視窗：

```text
BT HID KVM
├─ 目標 [<host 名稱> (<MAC>) 已配對 v]  [掃描]  [配對]  [連線] 或 [中斷]
├─ 狀態：未連線 / 配對中… / 已配對 <MAC>，可以連線 / 配對失敗 / 連線中… / 已連線 <MAC> / 連線失敗 / 掃描中…（對方電腦要開啟可被搜尋） / 掃描結束，清單裡有 N 台電腦 / 目標裡找不到 MAC
├─ 配對碼：只在核對配對碼時出現，旁邊有 [不同] [相同]
├─ 模式色塊：灰色「本機」，或綠色並顯示 host 的名稱
├─ 觸發鍵（外框）
│  ├─ 切換模式：勾選後按一下左 Win 切換，不用按住
│  └─ 提示：連線後按住左 Win（Keychron Mac 模式為 Command 位置）控制對方電腦；勾選切換模式後改成「按一下切換」的說明
├─ 鍵盤：被攔截的鍵盤
├─ 滑鼠：被監看的滑鼠
└─ log 區
```

「目標」是下拉選單，也可以直接輸入 MAC。清單列出 BlueZ 已知、在 App 用的藍牙介面上的電腦，已配對的排前面，例如 `my-laptop (AA:BB:CC:DD:EE:FF) 已配對`。啟動時沒給 `--mac` 的話，會自動選第一台已配對的電腦。按「掃描」會只掃 Classic 藍牙 20 秒，每秒更新清單，這段時間對方要開啟可被搜尋。

「切換模式」不會記住，每次開 App 都從按住模式開始。

配對和連線都在背景 thread 進行，進行中「掃描」「配對」「連線」都會先停用；已連線時「掃描」和「配對」也會停用，host 自己連上時也一樣。掃描中按「配對」或「連線」，或 host 自己連上，都會先停止掃描。關閉視窗後，所有鍵盤滑鼠都會還給系統。

## 切換模式時發生什麼事

App 有兩種模式。觸發鍵決定現在是哪一種，每次切換都會先把「按住的鍵」處理乾淨，避免卡鍵。

```text
Time
 │
 ▼
[本機模式]
 ├─ 鍵盤：一直被 App 獨占，再經 uinput 轉送回本機
 └─ 滑鼠：不獨占，桌面照常收到
 │
 ▼
[按下觸發鍵] 進入 host 模式
 ├─ 本機目前按住的鍵，先送出放開
 ├─ 滑鼠：等所有滑鼠按鍵都放開才獨占，避免拖曳中卡住
 └─ 鍵盤滑鼠事件改成 HID 報告送到 host
 │
 ▼
[放開觸發鍵] 回到本機模式
 ├─ 送「全部放開」的鍵盤和滑鼠報告給 host
 └─ 解除滑鼠獨占
```

勾選「切換模式」時，進入和離開做的事一樣，只是改成「按一下觸發鍵」切換：這次按下進入 host 模式，下一次按下才回到本機模式。放開觸發鍵、按住時的自動重複，都不會切換。

幾種特殊情況：

- 沒連線時，觸發鍵就是一般的 Win 鍵，照常傳到本機
- 連線中 host 斷線，App 會自動回到本機模式，log 出現 `link lost, back to local`
- host 不會收到觸發鍵本身。`Ctrl+C` 這類組合鍵照常送出

## 指令參數

| 參數 | 預設值 | 說明 |
|---|---|---|
| （不加參數） | | 開啟 GUI |
| `--mac MAC` | （無） | 要控制的 host 的藍牙位址。GUI 不給時，自動選清單裡第一台已配對的電腦；`--selftest` 一定要給 |
| `--selftest` | | 不開 GUI。註冊 SDP 記錄 → 等 `--mac` 配對完成 → 連線 → 畫正方形、按一下 Shift → 結束 |

`--selftest` 連線失敗時，每 3 秒重試一次，最多 10 次；Windows host 自己連上的話就不用重試。

## 設定值

設定值都在 `src/bt_hid_kvm/constants/__init__.py`，要改就直接改這個檔案。表中的 UUID 和 `*_PATH` 是 App 的名字，不是硬體設定，見 [UUID 是寫死的嗎](#uuid-是寫死的嗎)。

| 常數 | 值 | 用途 |
|---|---|---|
| `TRIGGER_KEY` | `ecodes.KEY_LEFTMETA` | 觸發鍵 |
| `UINPUT_KEYBOARD_NAME` | `bt_hid_kvm keyboard` | 轉送回本機用的虛擬鍵盤名稱 |
| `PROFILE_UUID` | `9d2b6c0e-6a8f-4f1e-9b7a-3c5d2e1f0a11` | App 公布 HID SDP 記錄時，向 BlueZ 登記用的名字 |
| `PROFILE_PATH` | `/org/bluez/bt_hid_kvm` | D-Bus 上 Profile1 物件的路徑 |
| `CONTROL_PROFILE_UUID` / `CONTROL_PROFILE_PATH` | `f3874a2d-2a3d-42ba-8c8d-95c73fa6a56c` / `/org/bluez/bt_hid_kvm/control` | 請 bluetoothd 替 App 接 PSM 17 連線時，登記用的名字和路徑 |
| `INTERRUPT_PROFILE_UUID` / `INTERRUPT_PROFILE_PATH` | `3d416b4f-f503-4fee-a13a-a3aafae6b3b5` / `/org/bluez/bt_hid_kvm/interrupt` | 同上，接 PSM 19 |
| `AGENT_PATH` | `/org/bluez/bt_hid_kvm/agent` | D-Bus 上 Agent1 物件的路徑，配對時 BlueZ 透過它問配對碼 |
| `PSM_SDP` | `0x01` | 配對前直連 host 用的通道，只是為了讓 BlueZ 建立裝置資料 |
| `PSM_CONTROL` / `PSM_INTERRUPT` | `0x11` / `0x13` | HID 的 control 和 interrupt 通道 |
| `COMPUTER_MAJOR_CLASS` | `0x01` | Class of Device 的 major class「電腦」；「目標」清單只列這類裝置 |
| `CONNECT_TIMEOUT` | `10.0` 秒 | 每條 L2CAP 連線的逾時；配對前的直連、等 BlueZ 建立裝置資料也用這個值 |
| `SEND_TIMEOUT` | `1.0` 秒 | 送出報告的逾時，超過就判定斷線 |
| `PAIR_TIMEOUT` | `120.0` 秒 | 等配對完成的上限，要留時間讓兩邊核對配對碼 |
| `SCAN_DURATION` | `20.0` 秒 | 按一次「掃描」掃多久，約兩輪 Classic 掃描 |
| `INTERRUPT_SNDBUF` | `1` | interrupt 通道的 `SO_SNDBUF`。kernel 會調到最小值（實測 4608 bytes，約 4 筆報告），舊的滑鼠位移就不會在 kernel 裡排隊 |
| `MOUSE_FLUSH_INTERVAL` | `0.008` 秒 | 滑鼠報告的最短間隔，約 125 Hz |
| `IDLE_POLL_INTERVAL` | `0.1` 秒 | 沒有滑鼠移動待送時，輸入迴圈的檢查間隔 |
| `UI_POLL_INTERVAL_MS` | `50` | GUI 讀取事件佇列的間隔（毫秒） |
| `SCAN_REFRESH_MS` | `1000` | 掃描中更新「目標」清單的間隔（毫秒） |
| `MODE_COLOR_LOCAL` / `MODE_COLOR_REMOTE` | `#757575` / `#2e7d32` | 模式色塊的灰色和綠色 |

藍牙介面不是設定值：App 啟動時會從 BlueZ 找第一個介面（`hci0` 排在 `hci1` 前面），找不到就結束並顯示 `no Bluetooth adapter found`。

### UUID 是寫死的嗎

不是。三個 `*_UUID` 和 `*_PATH` 是 App 向 BlueZ 報上的名字，就像 App 的套件名稱，跟哪台電腦、哪個藍牙介面都無關。

```text
App  ──用 CONTROL_PROFILE_UUID 登記：PSM 17 交給我──► bluetoothd
host ──連 PSM 17──► bluetoothd ──交給登記者──► App 的 /org/bluez/bt_hid_kvm/control
```

- 每台電腦的 BlueZ 各有一張登記表，所以每台都用同一組不會衝突；同一台電腦開第二個 App 時，BlueZ 會拒絕（`UUID already registered`）
- host 辨識鍵盤滑鼠看的是 SDP 記錄裡標準的 HID UUID `0x1124`，不看這幾個
- 改版不用換。只有另外做一個要和 App 同時跑的程式（例如 fork）時，才給它新的一組

## 運作方式

### HID 連線

App 先向本機的 BlueZ 註冊 SDP 記錄，host 配對時讀到它。之後兩邊都能開連線：App 按「連線」時由本機連過去，Windows 則會自己連過來。

```text
App     ──註冊記錄、登記 PSM 17/19──► BlueZ（本機）
host    ──配對讀取──► 知道本機是鍵盤滑鼠
App     ──按「連線」時連過去──► host ──收到報告──► 游標移動、打字
Windows ──自己連過來──► BlueZ（本機）──交給──► App
```

- 連線走 L2CAP PSM 17（control）和 PSM 19（interrupt）。host 連進來時先開 control 再開 interrupt，App 收齊同一台 host 的兩條才算連上
- SDP 記錄設定 `HIDReconnectInitiate=true`、`HIDNormallyConnectable=false`。Linux host 照這個設定等本機連過去；Windows 配對完不管這個設定，自己連過來。實測 Windows 之後也接受本機連過去
- 連出去的 socket 不需要 root；PSM 17/19 由 `bluetoothd` 替 App 監聽，再把連線交給 App，所以 App 也不需要 root
- BlueZ 5.85 不讓外部程式用 HID UUID `0x1124` 註冊 profile（`UUID already registered`），所以改用 `PROFILE_UUID` 註冊；SDP 記錄的內容仍然宣告 `0x1124`

監聽 PSM 17/19 另外用兩個 profile 註冊（`CONTROL_PROFILE_UUID`、`INTERRUPT_PROFILE_UUID`）。PSM 被 input 外掛占住時，`bluetoothd` 會連同那個 profile 的 SDP 記錄一起跳過；分開註冊，HID 記錄才不會跟著消失。已經連上時又有 host 連進來，App 會關掉新的連線；interrupt 和 control 來自不同 host 時，兩條都關。

兩種報告的格式：

| 報告 | Report ID | 內容 |
|---|---|---|
| 鍵盤 | 1 | 8 bit modifier、1 byte 保留、6 個按鍵。另有 LED output report，App 讀到後直接丟掉 |
| 滑鼠 | 2 | 5 個按鍵、X/Y 各 int16、wheel int8、AC Pan int8 |

control 通道收到 host 的請求時這樣回：`SET_*` 回 HANDSHAKE success，`GET_PROTOCOL` 回 report protocol，其他 `GET_*` 回 unsupported。收到 `VIRTUAL_CABLE_UNPLUG` 就斷線。

### 配對

「配對」不掃描，而是用 MAC 直接連到 host，再請 BlueZ 用 App 自己的 agent 配對。

```text
App ──直連 PSM 1──► host
App ──Pair()──────► BlueZ ──問配對碼──► App 的 agent ──顯示──► 配對碼列
App ──設 Trusted──► BlueZ
```

- 第 1 行讓 BlueZ 建立 host 的裝置資料，`Pair()` 才有對象。這條連線不要求加密，kernel 不會自己發起配對，它會一直開到配對結束
- agent 用 `DisplayYesNo` 註冊，但不是 default agent：BlueZ 只把 App 自己發起的配對交給它，桌面的 agent 照常處理其他配對
- 對已配對的裝置呼叫 `Pair()` 會失敗（`AlreadyExists`），所以 App 會先移除本機這邊的舊配對

### 按鍵攔截

- **裝置怎麼分類**：有 `KEY_A`、`KEY_Z` 的是鍵盤；有 `REL_X`、`REL_Y`、`BTN_LEFT` 的是滑鼠；`phys` 是空的虛擬裝置會略過，例如 ydotoold 和 App 自己的 `bt_hid_kvm keyboard`
- **為什麼鍵盤一直被獨占**：如果按下 Meta 之後才獨占，KWin 收不到 Meta 放開，Meta 就會卡住。App 啟動時，也會先等所有按鍵放開才開始獨占
- **keycode 怎麼轉成 HID usage**：用 Linux kernel `drivers/hid/hid-input.c` 的 `hid_keyboard[]` 反查（usage `0x00`–`0x81`）。修飾鍵另外轉成 modifier bit

滑鼠移動會先累加，最多每 `MOUSE_FLUSH_INTERVAL` 送一筆；按鍵有變化就立刻送。藍牙忙的時候（App 佇列裡還有報告沒送完），位移會繼續累加，等鏈路空出來再合成一筆送出。相對位移可以直接相加，所以不會漏掉移動，也不會在停手後才慢慢補送。`REL_WHEEL_HI_RES`、`REL_HWHEEL_HI_RES` 會被忽略，因為一般的 wheel 事件已經帶了同樣的捲動量。

輸入 thread 不做任何會卡住的藍牙 I/O，報告交給 sender thread 送（佇列上限 256 筆）。佇列滿了就直接斷線，不會默默丟掉「放開按鍵」的報告。

## 疑難排解

### 啟動時找不到模組或沒有 AF_BLUETOOTH

看到 `ModuleNotFoundError: No module named 'evdev'`，或沒有 `AF_BLUETOOTH` 的錯誤，代表程式不是用專案的 `.venv` 跑的。請在 repo 根目錄用 `uv run bt-hid-kvm` 啟動：`.python-version` 會讓 uv 用系統的 `/usr/bin/python3.14`。實測 asdf 的 Python 3.12 和 uv 自己下載的 Python 3.14.7 都沒有 `socket.AF_BLUETOOTH`。

### 啟動時出現 UUID already registered

看到 `org.bluez.Error.NotPermitted: UUID already registered`，代表本機已經有另一個 App 在跑，例如舊的 AppImage。先關掉它，或執行 `pkill -f "bt_hid_kvm|bt-hid-kvm"`，再啟動一次。

### uv sync 編譯失敗

`evdev`、`dbus-python`、`PyGObject`、`pycairo` 都要在本機從原始碼編譯，少了任何一個系統套件就會失敗。照 README「安裝與啟動」的 `sudo apt install` 把套件裝齊，再執行一次 `uv sync`。

### 按觸發鍵沒反應

- 先確認狀態是「已連線」。沒連線時，觸發鍵只是一般的 Win 鍵
- 執行 `uv run python -m evdev.evtest`，選你的鍵盤，按一下那顆鍵，看它送出的是不是 `KEY_LEFTMETA`
- 送出的是 `KEY_LEFTALT` 的話，代表鍵盤在 Mac 模式，改按左下角第 3 顆，或把鍵盤切到 Windows 模式

### Windows 配對成功但鍵盤滑鼠不能用

通常是本機的 input 外掛還開著：Windows 連進來時被拒絕，還收到 unplug，之後 App 按「連線」也會被拒（`Connection refused`）。在本機執行 `journalctl -u bluetooth -b | grep -E "Refusing input device|L2CAP server failed"`，有印出東西就是這個原因。

照[讓 Windows host 連得進來](#讓-windows-host-連得進來)停用 input 外掛，再到 Windows 移除本機，重新配對。

### 連線出現 Connection refused

host 還沒把本機當成 HID 裝置，請照[第一次配對](#第一次配對)重做一次。剛配對完的第一次連線也可能被拒，因為 host 還在讀 SDP 記錄，`--selftest` 會自動重試；用 GUI 的話，等幾秒再按一次「連線」。Windows host 的話，先看[Windows 配對成功但鍵盤滑鼠不能用](#windows-配對成功但鍵盤滑鼠不能用)。

### 按「配對」出現 Host is down

log 出現 `pair failed: [Errno 112] Host is down`，代表本機用 MAC 連不到 host，大約 5 秒後就放棄了。依序檢查：

- host 有開機，藍牙也開著
- 「目標」是 host 的位址。Linux host 可以用 `bluetoothctl show` 查；也可以讓 host 開啟可被搜尋，在 App 按「掃描」
- 兩台不要離太遠

### 已連線但 host 沒有反應

GUI 顯示已連線，色塊也會變綠，但 host 收不到任何輸入。Linux host 請執行 `journalctl -u bluetooth -n 20 --no-pager`，看有沒有這行（最後一段是本機的 MAC）：

```text
hidp_add_connection() Rejected connection from !bonded device /org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF
```

有的話，代表 host 已經不把本機當成已配對裝置，`ClassicBondedOnly=true` 會拒絕這種 HID 連線。L2CAP 通道還是連著，所以 App 不會報錯。照[第一次配對](#第一次配對)重新配對就會恢復；雙系統的 host 要照[同一台 host 裝了 Linux 和 Windows](#同一台-host-裝了-linux-和-windows)重做。

實測發生過一次，是在 Linux host 睡眠喚醒之後，確切原因還沒確認。

### 本機鍵盤沒反應

用滑鼠關掉 App 視窗；本機模式下滑鼠不會被獨占。也可以從別的終端機執行 `pkill -f "bt_hid_kvm|bt-hid-kvm"`，原始碼版和 AppImage 都適用。程式一結束，kernel 就會把鍵盤滑鼠還給系統。

## 已知限制

使用上：

- 連線期間，觸發鍵不能在本機當 Win 快速鍵用
- 不會自動重連：host 重開機或藍牙斷線後，要再按一次「連線」
- 鍵盤一次最多送出 6 個非修飾鍵
- 一次只連一台 host

環境：

- 不支援熱插拔：App 開著時才插上的鍵盤滑鼠，要重開 App 才會被攔截
- 實體鍵盤的 Caps Lock 燈可能不會亮，因為燈號狀態會送到虛擬鍵盤（未實測）
- 實測過的 host 是 Linux + BlueZ 和 Windows 11；App 只用第一個藍牙介面
- 要控制 Windows host 時，本機不能同時用 Classic 藍牙的 HID 裝置，見[讓 Windows host 連得進來](#讓-windows-host-連得進來)

## 開發與測試

```text
bt_hid_kvm/                        repo 根目錄，資料夾名稱不限
├── .gitignore                     忽略 __pycache__、測試與 lint 快取、.venv/、build/、dist/
├── .python-version                把 uv 鎖在系統的 /usr/bin/python3.14
├── pyproject.toml                 套件資訊、依賴、bt-hid-kvm 指令、pytest 設定
├── uv.lock                        uv 鎖定的依賴版本
├── Makefile                       `make` 打包 AppImage
├── README.md                      最短上手路徑
├── docs/guide.md                  這份指南
├── packaging/appimage/            AppImage 的啟動腳本 AppRun、桌面檔、圖示
└── src/bt_hid_kvm/
    ├── __init__.py                套件標記，內容是空的
    ├── __main__.py                入口：GUI 或 --selftest
    ├── components/main_window.py  Tk 視窗
    ├── constants/__init__.py      觸發鍵、App 的 UUID、逾時等設定
    ├── constants/hid.py           report descriptor、SDP 記錄、keycode 對照表
    ├── constants/__tests__/       keycode 對照表的測試
    ├── utils/bt_hid_link.py       RegisterProfile、L2CAP 連線（連出去和接進來）、找藍牙介面
    ├── utils/bt_pairing.py        配對：用 MAC 直連、Agent1 問配對碼、host 清單與掃描
    ├── utils/hid_report.py        HID 報告編碼、滑鼠位移合併
    ├── utils/input_capture.py     evdev 獨占、uinput 轉送、模式切換
    └── utils/__tests__/           HID 報告、control 回覆、配對 agent、host 清單、切換模式、接受 host 連線、找藍牙介面的測試
```

在 repo 根目錄執行檢查：

```bash
uv run pytest
uv run ruff check .
```

`pytest` 和 `ruff` 是 `pyproject.toml` 的開發依賴，`uv sync` 會一起裝好。pytest 只找 `src/` 底下的測試；ruff 看得出 `src/bt_hid_kvm` 是專案自己的套件，不用額外設定。

測試檔名都帶 `_tdd`，例如 `test_hid_report_tdd.py`。它們都不需要藍牙或實體裝置：大多只測純函式；配對 agent 的測試會用到 `dbus-python` 和 `PyGObject`，但不會連上系統的 BlueZ；切換模式的測試用假的藍牙連線和 uinput；接受 host 連線的測試用假的 L2CAP socket。

## 打包成 AppImage

AppImage 是單一執行檔：它把 Python、程式用到的套件和共用函式庫都包進去，換一台 Linux 不用再裝 uv 和編譯用的系統套件。在 repo 根目錄執行 `make` 就會打包：

```text
make ──uv sync --locked──► .venv/（編譯好的套件）
     ──下載並檢查 sha256──► build/tools/（appimagetool、runtime）
     ──複製 Python 3.14、.venv 的套件、共用函式庫──► build/AppDir/
     ──打包──► dist/BT_HID_KVM-x86_64.AppImage
```

第一次執行會用 `curl` 下載 appimagetool 1.9.1 和 runtime 20251108，之後直接用 `build/tools/` 裡的檔案。`make clean` 會刪掉 `build/` 和 `dist/`。

執行方式和參數跟原始碼版一樣，例如 `./dist/BT_HID_KVM-x86_64.AppImage --selftest --mac <host 的 MAC>`。

幾個容易踩的坑：

- 改了程式碼要重新執行 `make`，AppImage 才會更新
- 打包前會先執行 `uv sync --locked`，所以打包的機器要先裝好 uv 和 README 裡的系統套件。改了 `pyproject.toml` 的依賴卻沒更新 `uv.lock` 時會直接失敗，先執行 `uv lock`
- glibc 沒有包進去，執行的機器 glibc 版本要不低於打包的機器；權限設定和 BlueZ 也一樣要準備好
