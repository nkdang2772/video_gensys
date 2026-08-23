# Trạng thái dự án Video GenSystem

**Cập nhật:** 2026-08-24  
**Thư mục dự án:** `D:\video_gensystem`  
**Phiên bản ứng dụng:** `0.1.0`  
**Giai đoạn hiện tại:** Phần A — Foundation  
**Trạng thái:** Hoàn thành

## Tech stack đã chốt

- Python 3.11+; môi trường local hiện dùng Python 3.12.7.
- Streamlit cho giao diện MVP.
- SQLAlchemy 2.x cho ORM.
- SQLite cho database local.
- Alembic cho database migration.
- Pytest cho unit/integration test nền tảng.

## Hạng mục đã hoàn thành

- Khởi tạo Git repository, package Python, `pyproject.toml`, README và workflow CI.
- CLI `python -m app --version` trả về `0.1.0`.
- Cấu hình SQLite trên mọi connection:
  - `PRAGMA journal_mode=WAL`.
  - `PRAGMA busy_timeout=5000`.
  - `PRAGMA foreign_keys=ON`.
- Migration `0001_initial` tạo đủ 10 bảng:
  - `series`
  - `episode`
  - `scene`
  - `shot`
  - `reference`
  - `reference_version`
  - `episode_reference_pin`
  - `asset`
  - `job`
  - `simple_qa_note`
- Thêm foreign keys, unique constraints, CHECK constraints và partial unique index cho chosen asset.
- Hoàn thiện ORM models và relationships cho toàn bộ schema.
- Hoàn thiện validation ở app layer:
  - `characters_json` chỉ chứa ID hợp lệ và không trùng.
  - `primary_character_id` phải thuộc `characters_json`.
  - Danh sách nhân vật rỗng yêu cầu primary character là null.
- Hoàn thiện path resolver:
  - Chỉ chấp nhận asset path tương đối với episode root.
  - Chuẩn hóa đường dẫn database bằng dấu `/`.
  - Chặn path traversal, absolute path và Windows drive-relative path.
- Tạo venv tại `.venv` và database local tại `data/app.db`.

## Kết quả kiểm thử gần nhất

```text
python -m app --version: 0.1.0
pytest: 15 passed in 0.78s
alembic check: No new upgrade operations detected
PRAGMA journal_mode: wal
PRAGMA busy_timeout: 5000
Số bảng nghiệp vụ: 10
pip check: No broken requirements found
```

Kiểm thử đã bao phủ migration bằng raw SQL, CRUD cho mọi ORM model, constraints của chosen asset, invariant nhân vật và bảo mật đường dẫn.

## Git

- Foundation commit: `a5a1554 feat: build foundation schema and path safety`
- GitHub Actions workflow đã được cấu hình cho Python 3.11.
- CI cloud sẽ chạy sau khi repository được push lên GitHub.

## Bước tiếp theo

Phần B — Domain CRUD, bắt đầu bằng Bước 6: Series CRUD.

Chưa triển khai code của Phần B để bảo đảm đúng thứ tự dependency trong `build_order.txt`.

