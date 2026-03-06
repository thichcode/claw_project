# Changelog

## 2026-03-06

### Added
- Home layout V2 kiểu NOC/Horus: map trung tâm, widgets nổi hai bên (kéo thả + resize).
- Widget Controls bar phía trên: bật/tắt widget trái/phải, chọn Auto F5 (Off/5/8/15/30/60s).
- Vùng map theo nhãn: Azure, AWS, HN, SGN, DNG.
- Zoom theo vùng + toggle Show Healthy on/off.
- Đường nối service-to-service trên map, line nhỏ + hiển thị metric demo (ping, Mbps).
- Click vào từng service dot để xem danh sách server/IP (demo) + role.
- Panel chi tiết service có metric demo động: CPU, RAM, packet loss.
- Quick Mode: War Mode + Time Rewind (15m/1h/24h).
- Business Impact strip: impacted users, revenue risk, SLA breach risk (demo estimate).
- Preset simulate trên Home: Normal / Degraded / Incident Storm.

### Changed
- Homepage tối ưu cho mục tiêu "glance in 5 seconds" nhưng vẫn có drill-down nhanh.
- Widget state được lưu localStorage để giữ vị trí/kích thước sau refresh.
- Region box trên map autosize theo số service/server (demo ratio).
- Sửa logic map link để đường nối service/service không bị mất khi ẩn healthy.
- Widget Controls chuyển lên top bar gọn nhẹ (không che map).
- Auto refresh tạm pause khi user đang thao tác (click/type) để tránh trượt thao tác.
- Live Signal Feed chuyển sang dedupe + top 5 (Operator Mode cơ bản, giảm nhiễu).
- Incidents panel thêm owner/next-step/ETA (demo flow rõ hơn).

### Fixed
- Fix lỗi runtime trên floating widget sau khi tách controls.
- Fix preset simulate: trước khi bơm event sẽ reset trạng thái open cũ (ack alerts + resolve incidents) để map thay đổi rõ theo mỗi preset.

### Notes
- Dữ liệu topology/server/network hiện là demo-first để trình diễn UI/flow.
- Khi chuyển production, thay fake server/IP và network metrics bằng dữ liệu thật từ DB/API.

---

## Changelog policy
- Mỗi khi thêm/sửa/chuyển đổi chức năng, bắt buộc cập nhật file này.
- Mẫu tối thiểu cho mỗi lần cập nhật:
  - `Added`
  - `Changed`
  - `Fixed` (nếu có)
  - `Notes` (nếu cần)
