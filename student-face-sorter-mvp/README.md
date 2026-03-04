# Student Face Sorter MVP (Offline)

MVP gom ảnh theo từng học sinh với flow:
1. `bootstrap`: cluster ảnh chưa gán tên
2. gán tên 1 lần (cluster -> tên học sinh)
3. `build-profiles`: tạo face profile cho từng học sinh
4. `weekly`: tuần sau auto gán, ảnh không chắc đưa vào `review/`

> Mục tiêu thực tế: ~90% auto đúng, phần còn lại review tay.

## 1) Cài đặt

```bash
cd student-face-sorter-mvp
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

## 2) Chuẩn bị dữ liệu

- Đặt ảnh tuần đầu vào `input/`
- Chạy:

```bash
python main.py bootstrap
```

Kết quả:
- `output/bootstrap_clusters/cluster_x/` (ảnh đã gom theo cụm)
- `data/bootstrap_index.csv`
- `data/bootstrap_cluster_embeddings.json`
- `data/cluster_name_map.json` (bạn tự điền mapping)

Ví dụ `data/cluster_name_map.json`:
```json
{
  "cluster_0": "Nguyen Van A",
  "cluster_1": "Tran Thi B"
}
```

Sau đó chạy:

```bash
python main.py build-profiles
```

Sẽ tạo:
- `data/student_embeddings.json`

## 3) Chạy hàng tuần

- Bỏ ảnh mới vào `input/`
- Chạy:

```bash
python main.py weekly
```

Kết quả:
- `output/<ten_hoc_sinh>/...` ảnh auto gán
- `review/` ảnh cần duyệt tay
- `data/last_run_report.csv`

## 4) Tinh chỉnh độ chính xác

- `ASSIGN_THRESHOLD`:
  - giảm xuống (vd 0.40) => ít nhầm hơn, nhiều ảnh vào review hơn
  - tăng lên (vd 0.50) => auto nhiều hơn, dễ nhầm hơn
- tăng chất lượng ảnh mẫu ban đầu (mặt rõ, đủ sáng)

## 5) Quyền riêng tư (bắt buộc)

- Chạy offline/local nội bộ
- Không upload ảnh học sinh lên cloud khi chưa được phép
- Mã hóa ổ đĩa + phân quyền thư mục
- Xóa dữ liệu tạm khi hoàn tất
