# G8 Monitor – theo dõi robot và giám sát lỗi (giai đoạn 1: thu thập dữ liệu RCS)

RCS/ICS **tự đẩy** dữ liệu lên tool này; tool lưu log theo ngày và hiển thị trên web tiếng Việt (dùng được trên điện thoại).

## Cài và chạy
1. `pip install starlette uvicorn`
2. Chạy `start.bat`. **Xem giao diện: `http://192.168.110.189:5503`** (cổng web). **RCS đẩy dữ liệu vào cổng 5502** (cổng nhận, tách riêng khỏi web).
3. Chạy `firewall_open.bat` bằng **Run as administrator** một lần (mở cả 5502 và 5503).
4. PC chạy tool phải có IP cố định 192.168.110.189.

## Khai trong RCS
RCS → Configuration Management → System Configuration → **Third-party Service Configuration**, nhập 3 URL:

| Loại | URL | Ghi chú |
|---|---|---|
| Trạng thái robot | `http://192.168.110.189:5502/ics/agv-status` | Bật báo định kỳ (mục 4.2.1 tài liệu) |
| Cảnh báo | `http://192.168.110.189:5502/ics/alarm` | Báo 1 lần khi xảy ra, không gửi lại (4.2.3) |
| Trạng thái task | `http://192.168.110.189:5502/ics/task-status` | Chỉ báo ở node đã cấu hình trong mẫu task (3.2.1) |

Tool luôn trả `{"code":1000,"desc":"success"}` để RCS không gửi lại liên tục.
Cổng 5502 chỉ nhận 3 đường dẫn trên; cổng 5503 chỉ phục vụ web. Thử không cần RCS: `python simulate.py --loop` (gửi dữ liệu giả vào 5502).
Vị trí robot hiển thị theo **ô highbay gần nhất** (dạng `D36-16`, ví dụ "Gần D36-16 (Kho 2500)"); trên bản đồ vẫn đặt theo toạ độ.

Robot theo dõi: LT01–LT05, FK02 (khai ở `robots` trong config.json; robot chưa có dữ liệu vẫn hiện thẻ "Chưa nhận dữ liệu").

## Giao diện (5 tab)
- **Bản đồ** (mở đầu tiên): ảnh bản đồ nhà máy (dựng từ map RCS), kéo để di chuyển, hai ngón/cuộn chuột để zoom, nút + − ⤢ (⤢ = vừa khung). Chỉ là ảnh, không tương tác node/edge. Robot là chấm tròn có tên, **màu theo trạng thái** (xanh lá: đang chạy, xanh dương: rảnh, tím: sạc, đỏ nhấp nháy: lỗi, xám: mất tín hiệu/offline; viền cam hoặc dấu ! khi có cảnh báo). Vị trí cập nhật mỗi 3 giây, không chạy mượt.
  Chạm robot (hoặc bấm tên robot ở hàng trên) → **thanh thông báo** hiện trạng thái, vị trí (tên ô), task và **lỗi dự đoán**; thanh đỏ trên cùng liệt kê robot đang có lỗi nặng.
- **Robot**: thẻ từng robot (trạng thái, pin, vị trí → tên ô highbay, task, kệ, "cập nhật x giây trước"). Lỗi tô đỏ, mất tín hiệu tô vàng.
- **Sự cố**: cảnh báo đang xảy ra (kèm mã lỗi như 8039, gợi ý của RCS) và dòng thời gian sự cố.
- **Task**: trạng thái task RCS báo (kể cả gửi lỗi/chạy lỗi).
- **Hệ thống**: lần cuối nhận từng loại dữ liệu, xem log theo ngày/loại/từ khóa, tải file log.

Thanh trên cùng: xanh "Đang nhận dữ liệu"; đỏ "RCS im lặng ..." nếu quá `silence_warn_sec` không có tin robot.

## Lỗi dự đoán (thanh thông báo trên bản đồ)
Suy ra từ dữ liệu RCS gửi, kèm cách xử lý bằng tiếng Việt (bảng mã lỗi trong `hints.json`, có thể sửa):
cảnh báo RCS đang xảy ra (mã 8039, 8024, 25216...) · robot Fault chưa có chi tiết · mất tín hiệu/offline · pin thấp · **nghi kẹt** (đang chạy task nhưng đứng yên quá `stuck_sec`, mặc định 180 giây) · sạc nhưng pin không tăng `charge_stall_min` phút · task vừa gửi lỗi/chạy lỗi. Đây là **dự đoán**, không phải kết luận.

## Cập nhật bản đồ khi map RCS đổi
`pip install pillow numpy`, giải nén `RTA-C060-...zip` từ file map, rồi `python build_map.py <thư_mục_đã_giải_nén>`. Tạo lại `map\map.png`, `map_meta.json`, `points.json` (toạ độ điểm). Chạy lại `start.bat`.
Bản đồ hiện tại dựng từ `3-map2 (29).zip`.
**Kiểm tra lần đầu:** toạ độ `devicePostionRec` RCS gửi đang giả định là mm cùng hệ với bản đồ. Khi có dữ liệu thật, robot phải nằm trên đường đi. Nếu lệch đều một khoảng, chỉnh `xy_offset_mm` trong `config.json`. Nếu RCS không gửi toạ độ, tool lấy toạ độ từ mã điểm `devicePosition` (kém chính xác hơn).

## Tự phát hiện sự cố (ghi vào log sự cố)
Robot báo Fault / hết lỗi · offline / online lại · pin dưới `battery_low` · mất tín hiệu quá `robot_stale_sec` · RCS ngừng gửi dữ liệu · task gửi lỗi (5) / chạy lỗi (7) · mọi cảnh báo RCS (mức theo `alarmGrade`).

## Log theo ngày
`logs\YYYY-MM-DD\` gồm `incident.jsonl`, `alarm.jsonl`, `task.jsonl`, `agv.jsonl` (ghi khi đổi trạng thái/task/pin hoặc mỗi `agv_log_interval_sec`), `raw.jsonl` (dữ liệu không đọc được; bật `log_raw` để lưu mọi bản tin). Giữ `retention_days` ngày (30), tự xóa cũ. Mỗi dòng là một JSON, mở bằng Excel/Notepad được.

## config.json
- `alias`: tên RCS (`deviceName`, ví dụ `0001`) → tên hiển thị (`LT01`). **Cần sửa theo robot thật.**
- `alarm_active_minutes`: cảnh báo coi là "đang xảy ra" nếu mới báo trong số phút này và chưa có `alarmStatus=1`.
- `nodes.json`: bảng điểm highbay (cùng file với ManualControl2) để dịch mã điểm ra tên ô.

## Lưu ý
- Tài liệu V3.0.6 không có trường "đã xử lý" của cảnh báo, nên tool dựa vào thời gian (`alarm_active_minutes`) và trạng thái robot.
- Giai đoạn này chỉ trong LAN, chưa có đăng nhập. Truy cập từ xa (VPN/Tailscale) và thông báo Telegram để giai đoạn sau.
- Tool này không gọi ngược RCS (chỉ nhận), nên không ảnh hưởng vận hành.
