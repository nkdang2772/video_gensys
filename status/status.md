# Trạng thái dự án Video GenSystem

**Cập nhật:** 2026-08-24  
**Thư mục dự án:** `D:\video_gensystem`  
**Phiên bản ứng dụng:** `0.1.0`  
**Giai đoạn hiện tại:** Phần B — Domain CRUD
**Trạng thái:** Bước 6–7 hoàn thành

## Tech stack đã chốt

- Python 3.11+; Conda environment chuẩn pin Python 3.11, venv kiểm thử hiện dùng Python 3.12.7.
- Conda quản lý Python, SQLite, FFmpeg/FFprobe và dependency phát triển qua `environment.yml`.
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
- Thêm `environment.yml`; Conda là cách setup được khuyến nghị, còn `.venv` là fallback.
- `conda env create --dry-run -f environment.yml` đã resolve thành công trên Windows.
- Tách ComfyUI/PyTorch/CUDA khỏi environment chung để tránh xung đột GPU theo driver/workflow.

### Bước 6 — Series CRUD

- Service `app/services/series.py` hỗ trợ create, list, get by ID, update và soft delete.
- Slug được chuẩn hóa ASCII, unique toàn cục và không được tái sử dụng sau soft delete.
- Series đã soft delete bị ẩn mặc định khỏi list/get.
- CLI hoạt động với lệnh `python cli.py series create --name "Tên series"`.
- Migration `0002_series_lifecycle` bổ sung `series.deleted_at`.

### Bước 7 — Episode CRUD với snapshot

- Tạo Episode trong một database transaction do service sở hữu.
- Snapshot resolution, FPS, aspect ratio, style version, palette và font từ Series.
- Pin mọi reference series-specific đang active và style anchor theo đúng current version.
- Hỗ trợ pin shared reference được chọn explicit.
- Từ chối tạo Episode nếu reference cần dùng thiếu current version.
- Tạo đầy đủ cây thư mục episode theo quy trình.
- Khi database hoặc filesystem lỗi, database rollback và folder episode mới được dọn sạch.
- Migration `0002_series_lifecycle` bổ sung `reference.is_active`.

## Kết quả kiểm thử gần nhất

```text
python -m app --version: 0.1.0
pytest: 26 passed
alembic check: No new upgrade operations detected
PRAGMA journal_mode: wal
PRAGMA busy_timeout: 5000
Số bảng nghiệp vụ: 10
pip check: No broken requirements found
```

Kiểm thử đã bao phủ migration bằng raw SQL, CRUD cho mọi ORM model, Series CRUD,
CLI create series, Episode snapshot/pin/folder tree, rollback khi disk/database lỗi,
reference thiếu version, constraints của chosen asset, invariant nhân vật và bảo mật đường dẫn.

## Git

- Foundation commit: `a5a1554 feat: build foundation schema and path safety`
- Status/bug log commit: `11e2866 docs: add project status and bug log`
- Conda commit: `7291ec4 build: add conda environment management`
- GitHub Actions workflow đã được cấu hình cho Python 3.11.
- CI cloud sẽ chạy sau khi repository được push lên GitHub.

## Bước tiếp theo

Phần C — Import, bắt đầu bằng Bước 8: Script parser.

Chưa triển khai Bước 8 trở đi để bảo đảm đúng thứ tự dependency trong `build_order.txt`.
