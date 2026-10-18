# G8 Monitor – theo dõi robot và giám sát lỗi (v1.1.0: thu thập dữ liệu RCS + cảnh báo Telegram)

RCS/ICS **tự đẩy** dữ liệu lên tool này (trạng thái robot, cảnh báo, task). Tool còn **tự hỏi RCS** (máy RCS `192.168.110.100`, area 2, mặc định bật) đường đi robot và danh sách task. Trên web có nút **cập nhật bản đồ từ RCS** và **cập nhật bảng highbay từ file Excel**. Tool lưu log theo ngày và hiển thị trên web tiếng Việt (dùng được trên điện thoại). Lỗi quan trọng được **đẩy vào nhóm Telegram**, cấu hình trên **trang quản trị cổng 5504**.

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
2. Chạy `start.bat`. **Xem giao diện: `http://192.168.110.189:5503`** (cổng web). **RCS đẩy dữ liệu vào cổng 5502** (cổng nhận, tách riêng khỏi web). **Trang quản trị Telegram: `http://192.168.110.189:5504`** (cần mật khẩu).
3. Chạy `tools\firewall_open.bat` bằng **Run as administrator** một lần (mở 5502, 5503 và 5504). Máy đã chạy bản cũ thì chạy lại để mở thêm 5504.
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
| topologyList (4.1.5.1) | `/ics/out/topologyList` | `{"areaId":2}` | chỉ khi bấm **Cập nhật map từ RCS** / **Tải map (.zip) về máy**, hoặc chạy `update_map.py --rcs` | Lấy link tải file map |

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
- **Đường đi robot**: vẽ trên bản đồ bằng **nét đứt màu cam** (chọn robot thì nét liền, đậm; vòng tròn trắng viền cam là điểm đích). Chỉ vẽ **phần đường còn lại** (từ điểm gần robot nhất tới đích). Hai điểm liền nhau mà cách xa hơn `route_jump_mm` (mặc định 3 m) và nằm chéo (không dọc lối đi) thì không nối, để không có đường chéo cắt ngang bản đồ. Thẻ robot hiện "Đường đi: N điểm → đích (tên ô)" ở thẻ robot. Log `path.jsonl` chỉ ghi khi robot nhận **đường mới hoặc bị đổi tuyến** (`reroute=true`), không ghi mỗi lần đường rút ngắn.
- **Danh sách task**: tab Task có mục "Task đang có trên RCS" (chưa gửi/đang gửi/đang chạy/lỗi). Log `order.jsonl` ghi mỗi khi task đổi trạng thái. Task chuyển sang gửi lỗi/chạy lỗi mà callback chưa báo thì tạo sự cố.
- Không gọi được API thì tạo sự cố một lần, gọi lại được cũng báo. Tình trạng từng API xem ở tab **Hệ thống → Tool hỏi RCS định kỳ**.

## Cập nhật bản đồ và highbay trên web (tab Hệ thống)
Cần `pip install -r requirements.txt` trên máy chạy tool (`pillow numpy` để dựng bản đồ, `openpyxl` để đọc Excel). Mỗi lúc chỉ chạy một việc cập nhật. File tải lên/tải từ RCS được giữ lại trong `raw\upload\` (không đưa lên git) để đối chiếu khi cần.

### Bản đồ
| Nút | Làm gì |
|---|---|
| **Cập nhật map từ RCS** | Máy chủ tự tải map zip từ RCS → tách **ảnh nền** (`.pgm` → `map.png`) và **topology** (toạ độ các điểm → `points.json`) của loại xe `map_model` → **thay toàn bộ** bản đồ đang hiển thị. Bản đồ trên web nạp lại ngay, không cần restart |
| **Cập nhật từ file zip** | Như trên nhưng dùng file zip chọn từ máy đang xem (map xuất tay từ RCS), có hiện % đã gửi lên. Dùng khi map RCS tải qua API thiếu ảnh nền |
| **Tải map (.zip) về máy** | Máy chủ tải map từ RCS về `raw\upload\` trước, sau đó máy đang xem kéo file về. Không đổi bản đồ tool |

**Tiến độ và mạng chập chờn:** các nút trên hiện thanh tiến độ và chữ báo đang ở bước nào: hỏi RCS → máy chủ tải từ RCS (`x MB / y MB, %`) → dựng bản đồ, hoặc → kéo về máy này (`x MB / y MB, %`). Máy chủ tải từ RCS qua mạng LAN nên ổn định. Bước kéo về máy xem web (thường ở xa, hay mất gói) chia file thành **từng khúc 1 MB**: khúc nào lỗi thì chờ rồi thử lại khúc đó (tối đa 10 lần), không phải tải lại từ đầu. Nếu vẫn hỏng, file vẫn nằm trên máy chủ ở `raw\upload\`, bấm lại hoặc lấy trực tiếp trên máy chủ. Mỗi lúc chỉ chạy một việc; bấm khi đang chạy sẽ báo chờ.

Cách tool lấy map từ RCS:
1. Gọi **topologyList**. API này không trả bản đồ, chỉ trả link tải:
   ```
   {"code":1000, "data":{"mapId":2,
     "mapZipUrl":"http://<IP RCS>:8888/textureMap/2/default/Map/commonTopo.zip?token=...",
     "mapJsonUrl":"http://<IP RCS>:8888/textureMap/2/default/Map/compress.json?token=..."}}
   ```
2. Máy chủ tải file theo link `mapZipUrl` (`mapJsonUrl` không dùng), lưu thành `raw\upload\rcs_map_area2_YYYYMMDD-HHMMSS.zip` (giữ 5 bản gần nhất).
3. Chạy `tools\update_map.py` với file đó (giải nén zip lồng zip, chọn map loại xe, dựng ảnh, sao lưu bản cũ). Kết quả công cụ in ra hiện ngay dưới nút: các map có trong file, map đã chọn, số điểm, số ô highbay có toạ độ trên bản đồ mới.

Mỗi lần gọi ghi vào `api.jsonl` (dòng `map_download`: link, dung lượng, số giây, nơi lưu) và tab Sự cố. RCS đòi user/password thì hiện cửa sổ nhập (xem dưới), nhập xong bấm lại.

### Highbay (mapping node ↔ tên ô)
Mục đích: RCS chỉ gửi mã node (vd. `01001045`), còn người vận hành nhớ vị trí theo tên ô như `D36-12` / `D36-12-1`. Bảng highbay giúp tool dịch mã node ra tên ô, để biết ngay **robot đang ở đâu, task thao tác ở điểm nào, lỗi xảy ra ở đâu**.

Bấm **Tải file highbay (.xlsx)**, chọn file. Tool **bóc tách và cập nhật luôn** (ghi `data\nodes.json`, bản cũ lưu `nodes.json.bak`) và nạp ngay, không cần restart. Kết quả hiện dưới nút để tham khảo: số điểm, số ô-tầng, theo khu, theo dãy, mã trùng, số ô có toạ độ trên bản đồ, các điểm thêm/bỏ/đổi so với bảng cũ. Tool tự nhận 2 dạng file:

| Dạng file | Cột cần có | Cách cập nhật |
|---|---|---|
| **File vị trí xuất từ RCS** (vd. `Area_G8_NVL_SLAM_High_Location_20261017.xlsx`) | `Area Name`, `Location Code` (ô-tầng, vd. `E40-1-1`), `Node` (mã node RCS) | Các ô-tầng cùng node gom lại (`E40-1-1..4` → ô `E40-1`). Khu = `Area Name` |
| **File mapping** (vd. `raw\G8_mapping_Node_Highbay_20261007.xlsx`) | `Khu`, `Dãy`, `Node`, `Tên RCS`, `Tầng 1`–`Tầng 4` | Tên ô lấy từ Tầng 1 bỏ số tầng |

**Cả hai dạng đều thay toàn bộ bảng cũ**: mỗi lần tải lên phải là file đầy đủ, mới nhất (khu nào không có trong file sẽ không còn tên ô). Bản đồ cũng vậy: mỗi lần cập nhật là thay hoàn toàn bằng bản mới nhất.

- Cột `Location Coordinates` trong file RCS không dùng (giá trị gần như giống nhau ở mọi dòng). Toạ độ ô lấy từ bản đồ theo mã node.
- Báo "**N ô chưa có trên bản đồ hiện tại**" nghĩa là node mới chưa có trong bản đồ tool: bấm **Cập nhật map từ RCS** rồi tải lại file highbay. Vẫn thiếu thì kiểm tra mã Node.
- Nên cập nhật bản đồ trước rồi mới cập nhật highbay.

## User/password RCS
Mạng nội bộ RCS thường tắt xác thực nên để trống. Nếu RCS bật xác thực và từ chối tool (HTTP 401/403, hoặc trả lỗi có chữ auth/token/login...), **giao diện web tự hiện cửa sổ "RCS yêu cầu đăng nhập"**.
- Nhập user/password của RCS (hỏi người quản trị RCS) → **Lưu và thử lại**: tool ghi vào `config.json` của máy và hỏi RCS lại ngay, không cần restart.
- Bấm **Để sau** thì 10 phút sau mới hỏi lại.
- Muốn nhập/đổi chủ động: tab **Hệ thống → Tool hỏi RCS định kỳ → Nhập user/password RCS**.
- `update_map.py --rcs` gặp lỗi xác thực thì hỏi user/password ngay trong cửa sổ cmd.
- Tool gắn header xác thực WSSE vào các lệnh gọi API. Lệnh tải file map không cần, vì link đã có `token`.

Password lưu dạng chữ thường trong `config.json` (không đưa lên git); trang web chỉ dùng trong LAN, ai mở được web cũng đổi được user/password này.

## Giao diện
Thanh trên cùng dùng logo G8 HOME thật (`src\static\logo.png`, icon tab `icon.png`) và hiện số phiên bản. Màu giao diện theo logo VietGlory (đỏ, xám); đường đi dự kiến của robot màu cam theo logo G8. Chọn giao diện bằng **nút sổ xuống** trên thanh trên cùng, cạnh chữ G8 Monitor (hiện tên giao diện đang xem, ví dụ "Bản đồ ▼"); chấm đỏ trên nút là số lỗi/cảnh báo đang có. Trình duyệt nhớ giao diện xem lần cuối. Thêm giao diện mới: thêm một `<button data-t="...">` trong `#menu` và một `<section class="tab">` trong `src\index.html`.
- **Bản đồ** (mặc định): ảnh bản đồ nhà máy (dựng từ map RCS), kéo để di chuyển, hai ngón/cuộn chuột để zoom, nút + − ⤢ (⤢ = vừa khung). Chỉ là ảnh, không tương tác node/edge. Robot là chấm tròn có tên, **màu theo trạng thái** (xanh lá: đang chạy, xanh dương: rảnh, tím: sạc, đỏ nhấp nháy: lỗi, xám: mất tín hiệu/offline; viền cam hoặc dấu ! khi có cảnh báo). Vị trí cập nhật mỗi 3 giây, không chạy mượt.
  Chạm robot (hoặc bấm tên robot ở hàng trên) → **thanh thông báo** hiện trạng thái, vị trí (tên ô), task và **lỗi dự đoán**; thanh đỏ trên cùng liệt kê robot đang có lỗi nặng.
  Vị trí robot hiển thị theo **ô highbay gần nhất** (dạng `D36-16`, ví dụ "Gần D36-16 (Kho 2500)"); trên bản đồ vẫn đặt theo toạ độ.
- **Robot**: thẻ từng robot (trạng thái, pin, vị trí → tên ô highbay, task, kệ, "cập nhật x giây trước"). Lỗi tô đỏ, mất tín hiệu tô vàng.
- **Sự cố**: cảnh báo đang xảy ra (kèm mã lỗi như 8039, gợi ý của RCS) và dòng thời gian sự cố.
- **Task**: task đang có trên RCS (getOrderList) và trạng thái task RCS báo (kể cả gửi lỗi/chạy lỗi).
- **Hệ thống**: lần cuối nhận từng loại dữ liệu, tình trạng các API tool hỏi RCS (kèm nút nhập user/password RCS), xem log theo ngày/loại/từ khóa, **cập nhật bản đồ** (từ RCS / file zip, tải map về máy), **cập nhật highbay** (tải file Excel lên là cập nhật), tải file log.

Thanh trên cùng: xanh "Đang nhận dữ liệu"; đỏ "RCS im lặng ..." nếu quá `silence_warn_sec` không có tin robot.
Robot theo dõi: LT01–LT05, FK02 (khai ở `robots` trong config.json; robot chưa có dữ liệu vẫn hiện thẻ "Chưa nhận dữ liệu").

## Lỗi dự đoán (thanh thông báo trên bản đồ)
Suy ra từ dữ liệu RCS gửi, kèm cách xử lý bằng tiếng Việt (bảng mã lỗi trong `data\hints.json`, có thể sửa):
cảnh báo RCS đang xảy ra (mã 8039, 8024, 25216...) · robot Fault chưa có chi tiết · mất tín hiệu/offline · pin thấp · **nghi kẹt** (đang chạy task nhưng đứng yên quá `stuck_sec`, mặc định 300 giây, **tính từ lúc nhận task**, không cộng thời gian rảnh/offline trước đó) · sạc nhưng pin không tăng `charge_stall_min` phút · task vừa gửi lỗi/chạy lỗi. Đây là **dự đoán**, không phải kết luận.

## Cập nhật bản đồ bằng dòng lệnh (`tools\update_map.py`)
Cách dễ nhất là nút trên web (xem trên). Trên máy chạy tool cũng làm được bằng dòng lệnh, cần `pip install pillow numpy`:
- **Từ file map xuất từ RCS**: kéo thả file zip (vd. `raw\3-map2 (29).zip`) vào `tools\update_map.bat`, hoặc chạy `python tools\update_map.py "raw\3-map2 (29).zip"`. Zip lồng zip (RTA-C060..., RTA-C100..., RTA-FD200...) tự giải nén. Thư mục đã giải nén cũng được.
- **Tải thẳng từ RCS trên máy chạy tool**: `python tools\update_map.py --rcs` (hoặc chạy `tools\update_map.bat` không kéo file), dùng API topologyList với `rcs_api` trong config. Nếu file RCS trả về không có ảnh nền `.pgm` thì dùng cách thứ nhất.

Tuỳ chọn: `--list` chỉ xem trong file có những map nào; `--model RTA-C100` chọn map loại xe khác (mặc định `map_model` trong config, là `RTA-C060`); `--scale 3` hệ số thu nhỏ ảnh.
Công cụ tạo lại `data\map\map.png`, `points.json` (toạ độ điểm), `map_meta.json`. Bản đồ cũ được sao lưu vào `data\map\backup\` (giữ 5 bản gần nhất). Công cụ cũng kiểm tra các ô highbay trong `data\nodes.json` có trên bản đồ mới không. **Tool đang chạy tự nạp bản đồ mới trong vòng 10 giây, không cần restart.** Tải lại trang web để thấy ảnh mới.
Bản đồ hiện tại dựng từ `3-map2 (29).zip` (map `RTA-C060-LQ-2L2T-E-410`). Tên nguồn và giờ dựng xem ở tab Hệ thống. Nhãn khu (Kho 2500, Xưởng máy...) khai trong `ZONES` của `tools\build_map.py`.

## Cập nhật tên điểm highbay bằng dòng lệnh (`tools\update_names.py`)
Cách dễ nhất là nút trên web (xem trên, nhận cả file vị trí xuất từ RCS và file mapping). Bằng dòng lệnh: cần `pip install openpyxl`, kéo thả file Excel (vd. `raw\G8_mapping_Node_Highbay_20261007.xlsx`) vào `tools\update_names.bat`, hoặc chạy `python tools\update_names.py <file.xlsx>`. Thêm `--check` để chỉ kiểm tra, không ghi.
- Đọc sheet đầu tiên, dòng 1 là tiêu đề. Cột theo bảng ở phần **Highbay** trên (file RCS hoặc file mapping). Các cột khác bỏ qua, thứ tự cột không quan trọng.
- Tên ô bỏ số tầng (`D32-1-1` → ô `D32-1`). Dòng thiếu Node hoặc tên ô bị bỏ qua.
- Báo số điểm theo khu, các điểm thêm/bỏ/đổi so với `nodes.json` hiện tại, mã trùng, thiếu Tên RCS, số ô có/không có toạ độ trên bản đồ.
- Ghi `data\nodes.json` (bản cũ lưu thành `nodes.json.bak`). **Tool đang chạy tự nạp lại trong vòng 10 giây.**
**Kiểm tra lần đầu:** toạ độ `devicePostionRec` RCS gửi đang giả định là mm cùng hệ với bản đồ. Khi có dữ liệu thật, robot phải nằm trên đường đi. Nếu lệch đều một khoảng, chỉnh `xy_offset_mm` trong `config.json`. Nếu RCS không gửi toạ độ, tool lấy toạ độ từ mã điểm `devicePosition` (kém chính xác hơn).

## Tự phát hiện sự cố (ghi vào log sự cố)
Robot báo Fault / hết lỗi · offline / online lại · pin dưới `battery_low` · mất tín hiệu quá `robot_stale_sec` · RCS ngừng gửi dữ liệu · task gửi lỗi (5) / chạy lỗi (7) · mọi cảnh báo RCS (mức theo `alarmGrade`).
- **Offline** xét theo `state = "Offline"` (RCS thật gửi offline kèm `deviceStatus` 1 hoặc 5, hiếm khi 0). Offline trong giờ nghỉ (xem Telegram) ghi mức thấp, kèm chữ "giờ nghỉ".
- **Cọc sạc**: thiết bị khai trong `chargers` (1080–1083) hoặc tên toàn số không phải robot được hiện là "Cọc sạc 1082", gộp các cảnh báo chập chờn, không ghi "đã hết" mỗi giây, mức vừa.
- **Task lỗi** theo getOrderList: chỉ bỏ qua task lỗi có sẵn ở lần hỏi đầu sau khi khởi động; task mới xuất hiện đã ở trạng thái lỗi vẫn báo.
- **Cảnh báo sạc** tách mã lỗi `errorCode` (7203, 7209, 7214...), cọc sạc, trạng thái robot. Chữ Trung RCS gửi kèm (空闲, 离线, 负载异常...) được dịch sang tiếng Việt.

## Cảnh báo Telegram (trang quản trị cổng 5504)
Mở `http://192.168.110.189:5504`, đăng nhập bằng mật khẩu **`G8@Admin2026`** (đặt cố định trong `src\admin.py`, biến `ADMIN_PASSWORD`; đổi ở đó rồi khởi động lại tool). Sai 5 lần thì khóa IP đó 5 phút. Phiên đăng nhập giữ 12 giờ, khởi động lại tool thì phải đăng nhập lại.

**Cài bot lần đầu:**
1. Trên Telegram nhắn **@BotFather** → `/newbot` → đặt tên → nhận **token** dạng `123456789:ABC...`.
2. Thêm bot vào **nhóm chung**, nhắn một tin trong nhóm (vd `/start@ten_bot`).
3. Trang quản trị: dán token → **Lưu** → **Tìm chat ID** → chọn nhóm (chat ID nhóm là số âm) → tick **Bật gửi cảnh báo** → **Lưu** → **Gửi tin thử**.
4. PC chạy tool phải ra được Internet tới `api.telegram.org` (cổng 443).

Cài đặt lưu vào `config.json` của máy (mục `telegram`, `alerts`), áp dụng ngay, không cần khởi động lại. Token không hiện lại đầy đủ trên trang; để trống ô token khi lưu là giữ token cũ.

**Cách gửi:** mỗi lỗi (theo loại lỗi + robot/thiết bị) gửi tin **🔴/🟠 bắt đầu** khi đã kéo dài đủ **ngưỡng**; hết thì gửi **✅ kết thúc** (trả lời vào tin bắt đầu, kèm thời gian kéo dài). Lỗi hết trước ngưỡng thì không gửi gì. Chưa hết sau `Nhắc` phút (mặc định 30) thì nhắc **một lần**. Cảnh báo RCS mà RCS không bao giờ báo hết thì tự đóng sau `Tự đóng` phút (mặc định 120). Tin gửi tuần tự 1 tin/giây, lỗi mạng hoặc Telegram giới hạn thì tự thử lại.

**Giờ nghỉ** (mặc định 00:00–07:00, sửa trên trang): không báo robot offline (A8), không nhắc lại. Robot vẫn offline khi hết giờ nghỉ thì đếm ngưỡng từ lúc hết giờ nghỉ. Cột "Giờ nghỉ" trên trang cho bật giờ nghỉ cho lỗi khác. Lưu ý: theo log 13–18/10 robot thường offline từ ~21:30, nên với 00:00–07:00 mỗi tối sẽ có tin offline lúc ~21:30 (và 1 tin nhắc lúc ~22:00).

| Mã | Lỗi | Bắt đầu | Kết thúc | Ngưỡng mặc định |
|---|---|---|---|---|
| A1 | Va chạm | Cảnh báo RCS loại 28 | RCS báo hết (`alarmStatus=1`) | 0 |
| A2 | Nhận diện pallet lỗi (FK02) | Cảnh báo loại 50 (25216, 25222...) | Xe đi được > 0,5 m, hoặc 10 phút không lặp lại | 0 |
| A3 | Lỗi dẫn đường | Cảnh báo loại 8 | RCS báo hết | 0 |
| A4 | Thiết bị hỏng | Cảnh báo loại 2 | RCS báo hết | 0 |
| A5 | Cập nhật bản đồ lỗi | Cảnh báo loại 11 | 10 phút không lặp lại | 0 |
| A6 | Sạc lỗi | Cảnh báo loại 21 (mã 72xx) | RCS báo hết, robot vào sạc được, hoặc nhận task rời cọc | 60 giây |
| A7 | Task gửi lỗi / chạy lỗi | Task trạng thái 5 / 7 | Task chuyển trạng thái khác | 0 |
| A8 | Robot offline | `state = Offline`, ngoài giờ nghỉ | Online lại | 60 giây |
| A9 | Robot báo LỖI | `deviceStatus = 2` | Khác 2 | 0 |
| A10 | Mất tín hiệu robot | Không có dữ liệu robot | Có dữ liệu lại | 60 giây |
| A11 | Pin thấp | Pin < 20% và không sạc | Vào sạc hoặc pin ≥ 25% | 0 |
| A12 | RCS ngừng gửi dữ liệu | Không có bản tin trạng thái robot (khi đó không báo A10 từng robot) | Bản tin đến lại | 120 giây |
| A13 | Không gọi được API RCS | 3 lần gọi lỗi liên tiếp | Gọi được lại | 0 |
| A14 | Monitor khởi động lại | Mỗi lần tool khởi động (kèm giờ bản ghi cuối trước đó) | — | — |
| B1 | Nghi kẹt | Đang chạy task, di chuyển < 0,5 m (tính từ lúc nhận task) | Đi được > 0,5 m hoặc hết chạy task | 300 giây |
| B2 | Đường đi bất thường | Cảnh báo loại 23 | RCS báo hết | 60 giây |
| B3 | Kệ bất thường | Cảnh báo loại 22 | RCS báo hết | 60 giây |
| B4 | Có vật cản | Cảnh báo loại 12 | RCS báo hết | 180 giây |
| B5 | Tải bất thường | Cảnh báo loại 25 | RCS báo hết | 60 giây |
| B6 | Cọc sạc mất giao tiếp | Cọc sạc báo lỗi lặp lại liên tục | 5 phút không có lỗi mới | 300 giây |

Trên trang: bật/tắt từng lỗi, sửa ngưỡng và tham số (pin thấp/pin đủ, số lần lỗi API, "hết sau"), xem các lỗi **đang theo dõi** (đã gửi hay chưa đủ ngưỡng) và **tin nhắn gần đây**. Mọi tin (kể cả không gửi được) ghi vào `logs\YYYY-MM-DD\notify.jsonl`, xem ở tab Hệ thống → log "Tin nhắn Telegram".
Giới hạn: trạng thái lỗi đang mở nằm trong bộ nhớ; khởi động lại tool thì lỗi đang mở không gửi tin kết thúc (tin A14 báo việc khởi động lại). Tool đang chết thì không tự báo được: thấy thiếu tin A14 sau sự cố mất điện/tắt máy thì kiểm tra máy chạy tool.
Phát lại log thật 17/10 20:56 → 18/10 16:50 (~20 giờ) với cài đặt mặc định: 65 tin (32 bắt đầu, 27 kết thúc, 6 nhắc).

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
- `route_jump_mm` (3000): khi vẽ đường đi, đoạn nối hai điểm dài hơn số này (mm) và nằm chéo thì bỏ không vẽ.
- `log_push`, `log_api`: lưu nguyên bản tin RCS đẩy lên / phản hồi API RCS (xem phần Log).
- `listen.port_admin` (5504): cổng trang quản trị. `chargers`: mã thiết bị cọc sạc → tên hiển thị.
- `stuck_sec`: mẫu đổi 180 → 300 giây. Máy cũ có sẵn `"stuck_sec": 180` trong `config.json` thì sửa tay thành 300 (chỉ ảnh hưởng log sự cố trên web; Telegram dùng ngưỡng B1 trên trang quản trị).
- `telegram`, `alerts`: do trang quản trị ghi, không cần sửa tay.

## Lưu ý
- Tài liệu V3.0.6 không có trường "đã xử lý" của cảnh báo, nên tool dựa vào thời gian (`alarm_active_minutes`) và trạng thái robot.
- Chỉ dùng trong LAN. Web 5503 không có đăng nhập; trang quản trị 5504 có mật khẩu. Truy cập từ xa (VPN/Tailscale) để giai đoạn sau.
- `alarmGrade` RCS gửi 1/2/3, tool đang hiểu 2 = cao, 1 = vừa, còn lại thấp (ví dụ Va chạm mức 3 hiện mức thấp trên web). Chưa đối chiếu được với tài liệu; Telegram không phụ thuộc mức này.
- Ý nghĩa mã sạc lỗi 7203/7205/7207/7209/7214 chưa có trong `data\hints.json`, tin chỉ hiện mã.
- Ngoài nhận dữ liệu RCS đẩy lên, tool chỉ gọi API đọc (xem **Các API tool gọi lên RCS**), không gửi lệnh nên không ảnh hưởng vận hành.

## Cấu trúc thư mục
| Thư mục / file | Nội dung |
|---|---|
| `start.bat` | Chạy tool (bấm đúp) |
| `config.example.json` | Cấu hình mẫu (đưa lên git) |
| `config.json` | Cấu hình của máy (alias robot, rcs_api, ngưỡng cảnh báo...), tự tạo từ mẫu, không đưa lên git |
| `src` | Tool chính: `main.py` (nhận dữ liệu, hỏi RCS, web), `notify.py` (luật cảnh báo + gửi Telegram), `admin.py` + `admin.html` (trang quản trị 5504), `version.py` (số phiên bản), `rcs_api.py` (gọi API RCS, xác thực WSSE), `cfg.py` (nạp config mẫu + config máy, lưu cài đặt), `index.html` (giao diện), `static` (logo G8 HOME, icon) |
| `tools` | Công cụ phụ (nút trên web cũng gọi các công cụ này): `update_map.bat/.py` (cập nhật bản đồ), `build_map.py` (dựng ảnh bản đồ, update_map gọi), `update_names.bat/.py` (cập nhật tên điểm từ Excel), `simulate.py` (gửi dữ liệu giả), `firewall_open.bat` (mở cổng) |
| `data` | Dữ liệu tool đang dùng: `nodes.json` (tên ô highbay), `hints.json` (bảng mã lỗi + cách xử lý), `map` (`map.png`, `points.json`, `map_meta.json`, `backup`) |
| `raw` | Dữ liệu gốc đầu vào: file map xuất từ RCS (`.zip`), file Excel mapping highbay. `raw\upload\`: file tải lên/tải từ RCS qua nút trên web (không đưa lên git) |
| `docs` | Tài liệu giao thức RCS V3.0.6 (PDF) |
| `logs` | Log theo ngày (tự tạo, không đưa lên git) |

## Phiên bản
Số phiên bản ở `src\version.py`, hiện trên thanh trên cùng của web, trang quản trị, tab Hệ thống và tin A14.
- **1.1.0** (19/10/2026): cảnh báo Telegram (20 loại lỗi nhóm A/B, tin bắt đầu/kết thúc/nhắc), trang quản trị cổng 5504 có mật khẩu, giờ nghỉ offline. Sửa nhận diện: nghi kẹt không cộng thời gian rảnh trước khi nhận task (48% cảnh báo cũ là sai), offline theo `state`, cọc sạc 1080–1083 không còn hiện như robot, task lỗi mới không bị bỏ sót, sạc lỗi tách mã 72xx và dịch chữ Trung. Logo G8 HOME thật.
- **1.0.0**: thu thập dữ liệu RCS, web giám sát, bản đồ, cập nhật map/highbay (các bản trước khi có số phiên bản).
