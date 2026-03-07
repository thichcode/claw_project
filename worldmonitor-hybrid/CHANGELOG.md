# Changelog

## 2026-03-07

### Changed
- API incidents: harden endpoint `POST /incidents/{id}/ack` theo state-machine — incident `resolved` sẽ trả `409`, incident đã `acked` giữ idempotent (không ghi event trùng), chỉ cho chuyển `open -> acked`.
- Home: thêm hint nhẹ khi `/locations` rỗng để báo đang ở Global-only trong lúc backend chưa trả dữ liệu location.
- Home: tinh chỉnh Quick Mode bar (padding/gradient + row gap) để nhóm control rõ ràng và dễ scan hơn.
- Home: thêm pill ngữ cảnh hiển thị nhanh location/time range/war mode ở topbar để scan trạng thái nhanh hơn.
- Home: chuyển Key KPI Snapshot thành panel có toggle ẩn/hiện để bố cục gọn hơn khi cần tập trung.
- Home: thêm indicator mũi tên cho các panel toggle để biết trạng thái đang mở/đóng khi quét nhanh.
- Home data flow: chuẩn hoá các trường đếm (`open_alerts/open_incidents`) về số không âm trước khi tính KPI/hotspot/active regions, tránh lệch số khi API trả giá trị âm hoặc sai kiểu.
- Home: tăng phản hồi hover cho chip Location để dễ nhận biết mục tiêu đang chọn.
- Home data flow: khi đang lọc theo location cụ thể, KPI/topbar dùng số alert/incident của chính location đang focus (từ danh sách đã lọc) thay vì summary global để tránh lệch ngữ cảnh vận hành.
- Home data flow: harden dữ liệu `/locations` bằng `ensureArray` trước khi chuẩn hoá mã vùng, tránh lỗi `.map is not a function` khi API tạm trả sai kiểu.
- Home data flow: khi lọc theo location cụ thể, bộ đếm `open` ở topbar/KPI chỉ tính record có `status=open` (thay vì đếm toàn bộ incidents/alerts đã fetch), tránh cộng nhầm item `acked/resolved`.

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

### Changed (latest rounds)
- Home: thêm nhãn "Key KPI Snapshot" để nhóm KPI rõ ràng hơn khi quét nhanh.
- Tối ưu lớp gọi API bằng cache token ngắn hạn + chống login đồng thời, giảm overhead auth lặp lại khi Home fetch nhiều endpoint.
- Tối ưu data flow Home: gom fetch topology/incidents/alerts chạy song song và tái sử dụng topology global khi đang ở chế độ `location=all` để tránh gọi API trùng.
- Home: chuyển filter location thành pill chips rõ trạng thái active/inactive để dễ scan.
- Bổ sung retry 1 lần khi API trả `401` (auto reset token + login lại) để Home giảm lỗi rớt dữ liệu khi token hết hạn giữa lúc fetch nhiều endpoint.
- Home: thêm panel "Operational Notes" có toggle ẩn/hiện để recap nhanh blast radius + revenue exposure.
- Home data flow: tái sử dụng promise topology của location đang chọn khi dựng `topologyByLocation`, giảm 1 API call `/topology?location_code=...` bị trùng mỗi lần render.
- Home: chuyển banner cảnh báo demo thành panel toggle để giảm clutter mà vẫn giữ cảnh báo rõ.
- Home data flow: chuẩn hoá danh sách location code (dedupe + bỏ giá trị rỗng) và luôn giữ location đang chọn trong tập topology fetch để tránh thiếu dữ liệu khi filter thủ công qua URL.
- Home: tinh gọn Quick Mode bar bằng pill link đồng nhất + highlight trạng thái đang bật để scan nhanh hơn.
- Home data flow: chuẩn hoá danh sách location từ API `/locations` (trim + bỏ rỗng + dedupe) và tái sử dụng chung cho cả location chips lẫn topology fetch để tránh gọi trùng/hiển thị lặp khi dữ liệu nguồn bẩn.
- Home: gom style KPI cards thành class riêng để đồng nhất spacing/typography, giảm inline noise.
- Home: tăng khoảng cách trong KPI cards để nhãn/giá trị dễ quét hơn.
- Home: KPI label uppercase + số dùng tabular-nums để quét nhanh và thẳng hàng.
- Home: gom khối filter/quick/KPI vào control stack có viền nền để bố cục sạch, dễ scan hơn.
- Home: tăng padding/gap trong control stack để các khối dễ thở và scan nhanh hơn.
- Home data flow: harden dữ liệu incidents/alerts/topology nodes bằng `ensureArray` trước khi slice/sort để tránh vỡ trang khi API trả về sai kiểu tạm thời.
- Home data flow: chuẩn hoá `summary.open_alerts/open_incidents` về số an toàn (fallback 0) để tránh NaN KPI khi API tạm trả string/null.
- Home data flow: chuẩn hoá `topology.nodes[].open_alerts/open_incidents` về số an toàn khi tính hotspot + active regions để tránh lệch ranking/count nếu API trả string/null.
- Home data flow: khi chọn location, Home chỉ fetch incidents/alerts theo `location_code` (thay vì toàn cục) để widget nổi phản ánh đúng khu vực đang focus.
- Home: KPI grid chuyển sang auto-fit min width để bố cục gọn, không bị bó cứng 4 cột trên màn hình hẹp.
- Home: topbar cho phép wrap trên màn hình hẹp để giữ layout sạch.
- Home: thêm nền pill cho cụm Auto Refresh + status badge để nhóm thông tin trạng thái rõ ràng hơn.
- Home data flow: chuẩn hoá `location` từ URL theo danh sách `/locations` (match không phân biệt hoa/thường) để tránh gọi API sai mã location khi query param dùng khác casing.
- Home data flow: chuẩn hoá `range` từ URL về tập hợp hợp lệ (`15m/1h/24h`), fallback `1h` khi query param bẩn để tránh state/link lệch nhau.
- Home data flow: nếu `location` trên URL không khớp danh sách `/locations` thì fallback về `all` để tránh gọi API theo mã location không hợp lệ.
- Home: thêm nhãn "Locations" trước filter chips để nhóm khu vực rõ ràng hơn.
- Home data flow: thêm fallback tính `Active regions` từ topology global khi `/locations` rỗng hoặc thiếu mã vùng, tránh KPI về 0 sai lệch.
- Home data flow: dedupe location code theo key không phân biệt hoa/thường khi chuẩn hoá `/locations` và dựng danh sách topology fetch, tránh gọi API trùng nếu nguồn trả lẫn `us`/`US`.
- Home data flow: chuẩn hoá `topologyGlobal.nodes[].location_code` theo key lowercase khi tính `Active regions`, tránh đếm trùng khu vực nếu dữ liệu lẫn hoa/thường (`US`/`us`).

### Added (latest rounds)
- Thêm KPI card `Active regions` trên Home để thấy nhanh số khu vực đang có alert/incident.

---

## Changelog policy
- Mỗi khi thêm/sửa/chuyển đổi chức năng, bắt buộc cập nhật file này.
- Mẫu tối thiểu cho mỗi lần cập nhật:
  - `Added`
  - `Changed`
  - `Fixed` (nếu có)
  - `Notes` (nếu cần)
