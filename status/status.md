# Trạng thái dự án Video GenSystem

**Cập nhật:** 2026-08-24  
**Thư mục dự án:** `D:\video_gensystem`  
**Phiên bản ứng dụng:** `0.1.0`  
**Giai đoạn hiện tại:** Phần D — Reference + Shot Manager
**Trạng thái:** Bước 11–14 hoàn thành

**Nguyên tắc phạm vi:** hệ thống là nền tảng sản xuất hình/voice/motion tổng quát cho mọi series. “Xích Bích”, “Tam Quốc” và các tên nhân vật lịch sử chỉ là test fixture/ví dụ acceptance, không phải domain được hard-code.

## Tech stack đã chốt

- Python 3.11+; Conda environment chuẩn pin Python 3.11, venv kiểm thử hiện dùng Python 3.12.7.
- Conda quản lý Python, SQLite, FFmpeg/FFprobe và dependency phát triển qua `environment.yml`.
- Streamlit cho giao diện MVP.
- SQLAlchemy 2.x cho ORM.
- SQLite cho database local.
- Alembic cho database migration.
- Pytest cho unit/integration test nền tảng.
- NumPy và Matplotlib cho xử lý PCM/waveform local.

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

### Bước 8 — Script parser

- Parser riêng cho TXT, CSV và JSON trong `app/parsers/`.
- TXT hỗ trợ các tag SCENE, SHOT, SPEAKER, TEXT, VISUAL và MOTION_INTENT.
- TEXT/VISUAL nhiều dòng được giữ đúng thứ tự và xuống dòng.
- CSV hỗ trợ multiline đúng chuẩn quoted CSV; JSON hỗ trợ root list hoặc `{ "shots": [...] }`.
- Phát hiện shot ID thiếu, trùng không phân biệt hoa/thường, motion intent sai và shot ID không an toàn.
- Fixture Xích Bích cấu trúc 80 shot parse đủ từ `s001` đến `s080`.

### Bước 9 — FFprobe wrapper

- `app/media/ffprobe.py` gọi subprocess không qua shell, timeout mặc định 30 giây.
- Trả về duration thực, sample rate, channels và codec của audio stream.
- Từ chối file thiếu, file hỏng, JSON/metadata sai và duration bằng 0.
- Hỗ trợ cấu hình executable bằng `VIDEO_GENSYSTEM_FFPROBE_PATH` hoặc PATH của Conda.
- Đã test bằng WAV PCM thật: ngắn, dài, hỏng và duration 0.

### Bước 10 — Voice auto-link và import

- Match `s\d+` trong filename hoặc shot keyword ở đầu filename.
- Copy WAV vào episode trước khi tạo Asset; lưu path tương đối và checksum SHA-256.
- Đo duration bằng FFprobe và tạo immutable audio Asset version được chọn.
- Ghi duration thực vào `Shot.audio_start_sec`, `audio_end_sec` và `audio_duration_sec`.
- Re-import tạo version mới và chuyển `is_chosen` trong transaction.
- File sai tên, file hỏng, duplicate candidate và shot thiếu audio đều có warning; không silent skip.
- Lỗi sau khi copy rollback database và xóa file vừa tạo.
- Test batch 80 WAV PCM thật tạo đủ 80 chosen audio Asset.

**Giới hạn dữ liệu kiểm thử:** chưa tìm thấy corpus kịch bản và voice Xích Bích production trong các workspace. Fixture 80 shot và 80 WAV PCM sinh trong test xác minh đầy đủ logic/kích thước batch, nhưng cần chạy lại acceptance test khi corpus production được cung cấp.

### Bước 11 — Reference + Version CRUD

- Tạo reference series-specific hoặc shared cho character/style/location/prop/map.
- Reference slug unique toàn cục; explicit ID giữ được underscore như `character_example`.
- Version tăng tuần tự, copy vào library managed path, checksum SHA-256 và không ghi đè.
- `ReferenceVersion` chặn sửa mọi scalar field sau khi đã persist.
- File nguồn thay đổi không ảnh hưởng file version đã lưu.
- CLI hỗ trợ create, add-version và list-versions; test tạo một character và v1/v2/v3.

### Bước 12 — Character batch key

- Validate duplicate/invalid ID, canonical sort, JSON serialize và SHA-256.
- Thứ tự character đầu vào không làm đổi key.
- `[]` và `[null]` tạo key khác nhau đúng DoD.

### Bước 13 — Shot service

- Create/update/bulk update Shot với whitelist field và safe shot ID.
- Tự regenerate `character_batch_key` khi `characters_json` thay đổi.
- Cross-field invariant primary character được kiểm tra trước flush.
- Update đồng thời characters/primary hoạt động; update lỗi rollback savepoint, không để object bẩn.
- Bulk update 20 shot chỉ flush một lần và tạo đúng batch key.

### Bước 14 — Waveform + audio cutter

- Sinh waveform PNG bằng NumPy/Matplotlib với backend headless.
- Đọc PCM WAV 8/16/24/32-bit và không ghi đè source.
- Cắt WAV theo timestamp bằng frame boundary, output atomic và cleanup khi lỗi.
- Silence detection chỉ trả gợi ý interval, không tự cắt/xác nhận.
- Test cắt WAV thật dài 5 phút thành 10 segment; tổng duration lệch không quá 0.1 giây.

## Kết quả kiểm thử gần nhất

```text
python -m app --version: 0.1.0
pytest: 64 passed
alembic check: No new upgrade operations detected
PRAGMA journal_mode: wal
PRAGMA busy_timeout: 5000
Số bảng nghiệp vụ: 10
pip check: No broken requirements found
```

Kiểm thử đã bao phủ migration bằng raw SQL, CRUD cho mọi ORM model, Series CRUD,
CLI create series, Episode snapshot/pin/folder tree, parser TXT/CSV/JSON, FFprobe với
WAV thật, import/re-import 80 audio Asset, ReferenceVersion immutable/checksum,
character batch key, bulk update 20 Shot, waveform/silence/cắt WAV 5 phút,
warning/failure rollback, constraints của chosen asset và bảo mật đường dẫn.

## Git

- Foundation commit: `a5a1554 feat: build foundation schema and path safety`
- Status/bug log commit: `11e2866 docs: add project status and bug log`
- Conda commit: `7291ec4 build: add conda environment management`
- GitHub Actions workflow đã được cấu hình cho Python 3.11.
- CI cloud sẽ chạy sau khi repository được push lên GitHub.

## Bước tiếp theo

Phần E — UI cơ bản, bắt đầu bằng Bước 15: Series/Episode list.

Chưa triển khai Bước 15 trở đi để bảo đảm đúng thứ tự dependency trong `build_order.txt`.
