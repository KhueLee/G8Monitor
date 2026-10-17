# G8 Monitor – theo dõi robot và giám sát lỗi (giai đoạn 1: thu thập dữ liệu RCS)

RCS/ICS **tự đẩy** dữ liệu lên tool này (trạng thái robot, cảnh báo, task). Tool còn **tự hỏi RCS** (máy RCS `192.168.110.100`, area 2, mặc định bật) đường đi robot và danh sách task, và tải map RCS khi bấm nút. Tool lưu log theo ngày và hiển thị trên web tiếng Việt (dùng được trên điện thoại).

## Cài Git và tải tool về máy client (PC chạy tool)
1. **Cài Git**: tải Git for Windows tại https://git-scm.com/download/win (bản 64-bit), chạy file cài, để mặc định và bấm Next đến hết. Ở bước "Adjusting your PATH environment" giữ lựa chọn **Git from the command line and also from 3rd-party software**.
   Nếu máy có `winget` thì chỉ cần chạy trong cmd/PowerShell: `winget install --id Git.Git -e`
2. Mở cmd **mới** và kiểm tra: `git --version` (hiện `git version 2.x...` là được).
3. **Tải tool về** (vd. vào `C:\G8Monitor`). Repo để công khai (public) nên **không cần tài khoản GitHub, không đăng nhập**:
   ```
   cd /d C:\
   git clone https://github.com/KhueLee/G8Monitor.git
   cd G8Monitor
   ```
   Máy client chỉ tải về và cập nhật (`clone`, `pull`), không đẩy code lên nên không cần khai `user.name`/`user.email`. Nếu Git vẫn hiện cửa sổ đăng nhập thì gõ sai địa chỉ repo, bấm huỷ và kiểm tra lại URL.
4. Cài Python 3 (https://www.python.org/downloads/, tích **Add python.exe to PATH** khi cài) rồi làm tiếp phần **Cài và chạy** bên dưới.

**Cập nhật bản mới**: tắt tool (đóng cửa sổ `start.bat`), rồi trong thư mục tool chạy `git pull` (không cần đăng nhập), sau đó chạy lại `start.bat`.
- `config.json` là cấu hình riêng của từng máy, **không đưa lên git**, nên `git pull` không ghi đè. Trên git chỉ có file mẫu `config.example.json`. Lần đầu chạy, tool tự chép mẫu thành `config.json`, sau đó sửa `config.json` theo máy.
- Tool đọc `config.example.json` làm giá trị mặc định rồi lấy `config.json` đè lên, nên **khóa mới trong bản mới tự có hiệu lực**, không phải chép tay. Chỉ cần sửa `config.json` khi muốn khác mặc định.
- **Máy đã chạy bản cũ**: `config.json` cũ có `"area_id": 1` sẽ đè mặc định 2. Mở `config.json`, sửa `rcs_api` → `"area_id": 2` (hoặc xoá dòng `area_id` để dùng mặc định). `base` đang trống thì tool tự dùng `http://192.168.110.100:7000`.
- **Máy đã clone trước khi tách `config.example.json`**: trước khi pull, sao lưu cấu hình: `copy config.json config.local.json`, rồi `git pull` (git sẽ xoá `config.json` cũ; nếu báo lỗi vì file đã sửa thì chạy `git checkout -- config.json` rồi `git pull` lại), sau đó `move /y config.local.json config.json`.
- Xem đã sửa gì trên máy: `git status`, `git diff`. Bỏ hết thay đổi trên máy, về đúng bản trên GitHub: `git checkout -- .` (không ảnh hưởng `config.json`).
- Thư mục `logs` cũng không đưa lên git nên `git pull` không ảnh hưởng log.

## Cài và chạy
1. `pip install -r requirements.txt` (chạy tool chỉ cần `starlette uvicorn`; `pillow numpy openpyxl` dùng cho công cụ cập nhật bản đồ/tên điểm)
2. Chạy `start.bat`. **Xem giao diện: `http://192.168.110.189:5503`** (cổng web). **RCS đẩy dữ liệu vào cổng 5502** (cổng nhận, tách riêng khỏi web).
3. Chạy `tools\firewall_open.bat` bằng **Run as administrator** một lần (mở cả 5502 và 5503).
4. PC chạy tool phải có IP cố định 192.168.110.189.

## Khai trong RCS
RCS → Configuration Management → System Configuration → **Third-party Service Configuration**, nhập 3 URL:

| Loại | URL | Ghi chú |
|---|---|---|
| Trạng thái robot | `http://192.168.110.189:5502/ics/agv-status` | Bật báo định kỳ (mục 4.2.1 tài liệu) |
| Cảnh báo | `http://192.168.110.189:5502/ics/alarm` | Báo 1 lần khi xảy ra, không gửi lại (4.2.3) |
| Trạng thái task | `http://192.168.110.189:5502/ics/task-status` | Chỉ báo ở node đã cấu hình trong mẫu task (3.2.1) |

Tool luôn trả `{"code":1000,"desc":"success"}` để RCS không gửi lại liên tục.
Cổng 5502 chỉ nhận 3 đường dẫn trên; cổng 5503 chỉ phục vụ web. Thử không cần RCS: `python tools\simulate.py --loop` (gửi dữ liệu giả vào 5502).

## Các API tool gọi lên RCS
Chỉ gọi **API đọc**, không gửi lệnh nào cho robot (không tạo/huỷ task, không điều khiển xe), nên không ảnh hưởng vận hành. Mọi API là HTTP POST JSON tới `http://192.168.110.100:7000`.

| API (mục tài liệu) | Đường dẫn | Nội dung gửi | Khi nào gọi | Dùng để |
|---|---|---|---|---|
| getRobotTaskPath (4.1.2.5) | `/ics/out/getRobotTaskPath` | `{"areaId":2}` | mỗi 5 giây (`path_sec`) | Đường đi từng robot, vẽ trên bản đồ |
| getOrderList (4.1.1.7) | `/ics/out/task/getOrderList` | `{"areaId":2,"StartPage":"1","pageSize":"50"}` | mỗi 30 giây (`order_sec`) | 50 task mới nhất và trạng thái |
| topologyList (4.1.5.1) | `/ics/out/topologyList` | `{"areaId":2}` | chỉ khi bấm **Tải map (.zip)** hoặc chạy `update_map.py --rcs` | Lấy link tải file map |

Sau topologyList, tool tải file map bằng HTTP GET theo link RCS trả về (máy chủ file RCS, cổng 8888). Đây là file tĩnh, không phải API.

## Tool hỏi RCS định kỳ (getRobotTaskPath, getOrderList)
**Mặc định bật**, khai trong `config.json` → `rcs_api`:

| Khóa | Mặc định | Ý nghĩa |
|---|---|---|
| `enabled` | `true` | `false` để tắt hẳn việc hỏi RCS |
| `base` | `http://192.168.110.100:7000` | `http://<IP máy RCS>:7000` (cổng API RCS 7000) |
| `area_id` | `2` | Area ID trên RCS (số khu vực bản đồ) |
| `user`, `password` | trống | Chỉ cần khi RCS bật xác thực WSSE (mục 2.3 tài liệu). Xem mục **User/password RCS** bên dưới |
| `path_sec` | `5` | Hỏi **getRobotTaskPath** mỗi bao nhiêu giây. Nên ≥ 3 để RCS không tải nặng |
| `order_sec`, `order_page_size` | `30`, `50` | Hỏi **getOrderList** mỗi 30 giây, lấy 50 task mới nhất |
| `timeout_sec` | `8` | Chờ RCS trả lời tối đa bao nhiêu giây |

Đặt `0` để tắt từng loại.
- **Đường đi robot**: vẽ trên bản đồ (nét đứt, chọn robot thì nét đậm, vòng tròn trắng là điểm đích), hiện "Đường đi: N điểm → đích (tên ô)" ở thẻ robot. Log `path.jsonl` chỉ ghi khi robot nhận **đường mới hoặc bị đổi tuyến** (`reroute=true`), không ghi mỗi lần đường rút ngắn.
- **Danh sách task**: tab Task có mục "Task đang có trên RCS" (chưa gửi/đang gửi/đang chạy/lỗi). Log `order.jsonl` ghi mỗi khi task đổi trạng thái. Task chuyển sang gửi lỗi/chạy lỗi mà callback chưa báo thì tạo sự cố.
- Không gọi được API thì tạo sự cố một lần, gọi lại được cũng báo. Tình trạng từng API xem ở tab **Hệ thống → Tool hỏi RCS định kỳ**.

## Tải map từ RCS (nút trên web)
Tab **Hệ thống → Tải map từ RCS → ⬇️ Tải map (.zip)**. Không gọi định kỳ, chỉ khi bấm nút.
1. Tool gọi **topologyList**. API này không trả bản đồ, chỉ trả link tải:
   ```
   {"code":1000, "data":{"mapId":2,
     "mapZipUrl":"http://<IP RCS>:8888/textureMap/2/default/Map/commonTopo.zip?token=...",
     "mapJsonUrl":"http://<IP RCS>:8888/textureMap/2/default/Map/compress.json?token=..."}}
   ```
2. Tool tải file theo link `mapZipUrl` (map nén: topo và ảnh nền; `mapJsonUrl` không dùng).
3. Trình duyệt lưu file về máy đang mở web, tên `rcs_map_area2_YYYYMMDD-HHMM.zip`. Kéo thả file này vào `tools\update_map.bat` để cập nhật bản đồ tool (xem phần **Cập nhật bản đồ** bên dưới).

Mỗi lần tải ghi vào `api.jsonl` (phản hồi topologyList, link, dung lượng file) và tab Sự cố. RCS đòi user/password thì hiện cửa sổ nhập như dưới, nhập xong bấm tải lại.

## User/password RCS
Mạng nội bộ RCS thường tắt xác thực nên để trống. Nếu RCS bật xác thực và từ chối tool (HTTP 401/403, hoặc trả lỗi có chữ auth/token/login...), **giao diện web tự hiện cửa sổ "RCS yêu cầu đăng nhập"**.
- Nhập user/password của RCS (hỏi người quản trị RCS) → **Lưu và thử lại**: tool ghi vào `config.json` của máy và hỏi RCS lại ngay, không cần restart.
- Bấm **Để sau** thì 10 phút sau mới hỏi lại.
- Muốn nhập/đổi chủ động: tab **Hệ thống → Tool hỏi RCS định kỳ → Nhập user/password RCS**.
- `update_map.py --rcs` gặp lỗi xác thực thì hỏi user/password ngay trong cửa sổ cmd.
- Tool gắn header xác thực WSSE vào các lệnh gọi API. Lệnh tải file map không cần, vì link đã có `token`.

Password lưu dạng chữ thường trong `config.json` (không đưa lên git); trang web chỉ dùng trong LAN, ai mở được web cũng đổi được user/password này.

## Giao diện
Chọn giao diện bằng **nút sổ xuống** ở góc trái thanh trên cùng (hiện tên giao diện đang xem, ví dụ "🗺️ Bản đồ ▼"); chấm đỏ trên nút là số lỗi/cảnh báo đang có. Trình duyệt nhớ giao diện xem lần cuối. Thêm giao diện mới: thêm một `<button data-t="...">` trong `#menu` và một `<section class="tab">` trong `src\index.html`.
- **Bản đồ** (mặc định): ảnh bản đồ nhà máy (dựng từ map RCS), kéo để di chuyển, hai ngón/cuộn chuột để zoom, nút + − ⤢ (⤢ = vừa khung). Chỉ là ảnh, không tương tác node/edge. Robot là chấm tròn có tên, **màu theo trạng thái** (xanh lá: đang chạy, xanh dương: rảnh, tím: sạc, đỏ nhấp nháy: lỗi, xám: mất tín hiệu/offline; viền cam hoặc dấu ! khi có cảnh báo). Vị trí cập nhật mỗi 3 giây, không chạy mượt.
  Chạm robot (hoặc bấm tên robot ở hàng trên) → **thanh thông báo** hiện trạng thái, vị trí (tên ô), task và **lỗi dự đoán**; thanh đỏ trên cùng liệt kê robot đang có lỗi nặng.
  Vị trí robot hiển thị theo **ô highbay gần nhất** (dạng `D36-16`, ví dụ "Gần D36-16 (Kho 2500)"); trên bản đồ vẫn đặt theo toạ độ.
- **Robot**: thẻ từng robot (trạng thái, pin, vị trí → tên ô highbay, task, kệ, "cập nhật x giây trước"). Lỗi tô đỏ, mất tín hiệu tô vàng.
- **Sự cố**: cảnh báo đang xảy ra (kèm mã lỗi như 8039, gợi ý của RCS) và dòng thời gian sự cố.
- **Task**: task đang có trên RCS (getOrderList) và trạng thái task RCS báo (kể cả gửi lỗi/chạy lỗi).
- **Hệ thống**: lần cuối nhận từng loại dữ liệu, tình trạng các API tool hỏi RCS (kèm nút nhập user/password RCS), bản đồ đang dùng, xem log theo ngày/loại/từ khóa, **nút tải map từ RCS** (.zip), tải file log.

Thanh trên cùng: xanh "Đang nhận dữ liệu"; đỏ "RCS im lặng ..." nếu quá `silence_warn_sec` không có tin robot.
Robot theo dõi: LT01–LT05, FK02 (khai ở `robots` trong config.json; robot chưa có dữ liệu vẫn hiện thẻ "Chưa nhận dữ liệu").

## Lỗi dự đoán (thanh thông báo trên bản đồ)
Suy ra từ dữ liệu RCS gửi, kèm cách xử lý bằng tiếng Việt (bảng mã lỗi trong `data\hints.json`, có thể sửa):
cảnh báo RCS đang xảy ra (mã 8039, 8024, 25216...) · robot Fault chưa có chi tiết · mất tín hiệu/offline · pin thấp · **nghi kẹt** (đang chạy task nhưng đứng yên quá `stuck_sec`, mặc định 180 giây) · sạc nhưng pin không tăng `charge_stall_min` phút · task vừa gửi lỗi/chạy lỗi. Đây là **dự đoán**, không phải kết luận.

## Cập nhật bản đồ khi map RCS đổi (`tools\update_map.py`)
Cần `pip install pillow numpy`. Hai cách:
- **Từ file map xuất từ RCS** (hoặc file tải bằng nút **Tải map (.zip)** ở tab Hệ thống): kéo thả file zip (vd. `raw\3-map2 (29).zip`) vào `tools\update_map.bat`, hoặc chạy `python tools\update_map.py "raw\3-map2 (29).zip"`. Zip lồng zip (RTA-C060..., RTA-C100..., RTA-FD200...) tự giải nén. Thư mục đã giải nén cũng được.
- **Tải thẳng từ RCS trên máy chạy tool**: `python tools\update_map.py --rcs` (hoặc chạy `tools\update_map.bat` không kéo file), dùng API topologyList với `rcs_api` trong config. Nếu file RCS trả về không có ảnh nền `.pgm` thì dùng cách thứ nhất.

Tuỳ chọn: `--list` chỉ xem trong file có những map nào; `--model RTA-C100` chọn map loại xe khác (mặc định `map_model` trong config, là `RTA-C060`); `--scale 3` hệ số thu nhỏ ảnh.
Công cụ tạo lại `data\map\map.png`, `points.json` (toạ độ điểm), `map_meta.json`. Bản đồ cũ được sao lưu vào `data\map\backup\` (giữ 5 bản gần nhất). Công cụ cũng kiểm tra các ô highbay trong `data\nodes.json` có trên bản đồ mới không. **Tool đang chạy tự nạp bản đồ mới trong vòng 10 giây, không cần restart.** Tải lại trang web để thấy ảnh mới.
Bản đồ hiện tại dựng từ `3-map2 (29).zip` (map `RTA-C060-LQ-2L2T-E-410`). Tên nguồn và giờ dựng xem ở tab Hệ thống. Nhãn khu (Kho 2500, Xưởng máy...) khai trong `ZONES` của `tools\build_map.py`.

## Cập nhật tên điểm highbay (`tools\update_names.py`)
Cần `pip install openpyxl`. Kéo thả file Excel mapping (vd. `raw\G8_mapping_Node_Highbay_20261007.xlsx`) vào `tools\update_names.bat`, hoặc chạy `python tools\update_names.py <file.xlsx>`. Thêm `--check` để chỉ kiểm tra, không ghi.
- Đọc sheet đầu tiên, dòng 1 là tiêu đề. Cột cần có: **Khu, Dãy, Node, Tên RCS (name), Tầng 1–Tầng 4**. Các cột khác bỏ qua, thứ tự cột không quan trọng.
- Tên ô lấy từ Tầng 1 bỏ số tầng (`D32-1-1` → ô `D32-1`). Dòng không có Node hoặc Tầng 1 bị bỏ qua.
- Báo số điểm theo khu, các điểm thêm/bỏ/đổi so với `nodes.json` hiện tại, mã trùng, thiếu Tên RCS, và ô không có trên bản đồ.
- Ghi `data\nodes.json` (bản cũ lưu thành `nodes.json.bak`). **Tool đang chạy tự nạp lại trong vòng 10 giây.**
**Kiểm tra lần đầu:** toạ độ `devicePostionRec` RCS gửi đang giả định là mm cùng hệ với bản đồ. Khi có dữ liệu thật, robot phải nằm trên đường đi. Nếu lệch đều một khoảng, chỉnh `xy_offset_mm` trong `config.json`. Nếu RCS không gửi toạ độ, tool lấy toạ độ từ mã điểm `devicePosition` (kém chính xác hơn).

## Tự phát hiện sự cố (ghi vào log sự cố)
Robot báo Fault / hết lỗi · offline / online lại · pin dưới `battery_low` · mất tín hiệu quá `robot_stale_sec` · RCS ngừng gửi dữ liệu · task gửi lỗi (5) / chạy lỗi (7) · mọi cảnh báo RCS (mức theo `alarmGrade`).

## Log theo ngày
`logs\YYYY-MM-DD\`, mỗi dòng là một JSON, mở bằng Notepad/Excel được, xem/tìm ở tab Hệ thống. Giữ `retention_days` ngày (30), tự xóa cũ.

**Log nguyên gốc (mặc định bật):**
| File | Nội dung |
|---|---|
| `push.jsonl` | **Mọi bản tin RCS chủ động đẩy lên** (agv-status, alarm, task-status): giờ nhận, loại, IP gửi, nguyên nội dung JSON. Tắt bằng `"log_push": false` |
| `api.jsonl` | **Mọi lần tool hỏi API RCS và RCS trả về** (getRobotTaskPath, getOrderList, và topologyList khi bấm tải map): giờ, API, URL, nội dung gửi, có gửi xác thực không, mã HTTP, thời gian trả lời (ms), **nguyên phản hồi RCS**, lỗi nếu có. Lần tải file map ghi thêm dòng `map_download` (link, dung lượng). Tắt bằng `"log_api": false` |

Hai file này lớn nhất (agv-status gửi liên tục, getRobotTaskPath hỏi mỗi 5 giây), có thể vài chục đến vài trăm MB/ngày tuỳ số robot. Ổ đĩa ít chỗ thì giảm `retention_days` hoặc tắt bớt.

**Log đã xử lý:** `incident.jsonl` (sự cố), `alarm.jsonl`, `task.jsonl`, `agv.jsonl` (ghi khi đổi trạng thái/task/pin hoặc mỗi `agv_log_interval_sec`), `path.jsonl` (đường đi mới), `order.jsonl` (task đổi trạng thái), `raw.jsonl` (bản tin RCS không đọc được hoặc xử lý lỗi).

## config.json
Cấu hình riêng của máy, không đưa lên git (tự tạo từ `config.example.json` khi chạy lần đầu). Khóa nào không có trong `config.json` thì lấy theo `config.example.json`. Muốn đổi giá trị mặc định cho mọi máy thì sửa `config.example.json` rồi commit.
- `alias`: tên RCS (`deviceName`, ví dụ `0001`) → tên hiển thị (`LT01`). **Cần sửa theo robot thật.**
- `alarm_active_minutes`: cảnh báo coi là "đang xảy ra" nếu mới báo trong số phút này và chưa có `alarmStatus=1`.
- `nodes_file` (`data/nodes.json`): bảng điểm highbay (cùng file với ManualControl2) để dịch mã điểm ra tên ô. Tạo bằng `update_names.py`.
- `rcs_api`: tool hỏi RCS định kỳ (xem phần trên). `map_model`: loại xe dùng khi cập nhật bản đồ.
- `log_push`, `log_api`: lưu nguyên bản tin RCS đẩy lên / phản hồi API RCS (xem phần Log).

## Lưu ý
- Tài liệu V3.0.6 không có trường "đã xử lý" của cảnh báo, nên tool dựa vào thời gian (`alarm_active_minutes`) và trạng thái robot.
- Giai đoạn này chỉ trong LAN, chưa có đăng nhập. Truy cập từ xa (VPN/Tailscale) và thông báo Telegram để giai đoạn sau.
- Ngoài nhận dữ liệu RCS đẩy lên, tool chỉ gọi API đọc (xem **Các API tool gọi lên RCS**), không gửi lệnh nên không ảnh hưởng vận hành.

## Cấu trúc thư mục
| Thư mục / file | Nội dung |
|---|---|
| `start.bat` | Chạy tool (bấm đúp) |
| `config.example.json` | Cấu hình mẫu (đưa lên git) |
| `config.json` | Cấu hình của máy (alias robot, rcs_api, ngưỡng cảnh báo...), tự tạo từ mẫu, không đưa lên git |
| `src` | Tool chính: `main.py` (nhận dữ liệu, hỏi RCS, web), `rcs_api.py` (gọi API RCS, xác thực WSSE), `cfg.py` (nạp config mẫu + config máy, lưu user/password RCS), `index.html` (giao diện) |
| `tools` | Công cụ phụ: `update_map.bat/.py` (cập nhật bản đồ), `build_map.py` (dựng ảnh bản đồ, update_map gọi), `update_names.bat/.py` (cập nhật tên điểm từ Excel), `simulate.py` (gửi dữ liệu giả), `firewall_open.bat` (mở cổng) |
| `data` | Dữ liệu tool đang dùng: `nodes.json` (tên ô highbay), `hints.json` (bảng mã lỗi + cách xử lý), `map` (`map.png`, `points.json`, `map_meta.json`, `backup`) |
| `raw` | Dữ liệu gốc đầu vào: file map xuất từ RCS (`.zip`), file Excel mapping highbay. Bỏ file mới vào đây rồi chạy công cụ trong `tools` |
| `docs` | Tài liệu giao thức RCS V3.0.6 (PDF) |
| `logs` | Log theo ngày (tự tạo, không đưa lên git) |
