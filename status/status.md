# Trạng thái dự án Video GenSystem

**Cập nhật:** 2026-08-24  
**Thư mục dự án:** `D:\video_gensystem`  
**Phiên bản ứng dụng:** `0.1.0`  
**Giai đoạn hiện tại:** Audit/revalidation tuần tự theo DoD nghiêm ngặt
**Gate chính thức:** **Bước 1–8 — PASS; Bước 9 — đang revalidate**
**Trạng thái:** Code lịch sử tồn tại đến Bước 30, nhưng chỉ Bước 1–8 đã đủ branch/PR/CI/merge để được đánh PASS chính thức. Bước 9 đã đạt test local nhưng chưa được đánh PASS trước khi có PR, CI xanh và merge; Bước 10 chưa được bắt đầu.

**Nguyên tắc phạm vi:** hệ thống là nền tảng sản xuất hình/voice/motion tổng quát cho mọi series. “Xích Bích”, “Tam Quốc” và các tên nhân vật lịch sử chỉ là test fixture/ví dụ acceptance, không phải domain được hard-code.

**Quy ước vận hành:** trước mỗi giai đoạn triển khai hoặc sửa lỗi, phải đọc lại toàn bộ `status/status.md` và phần tổng quan/lỗi mới nhất trong `bug/bug.md` để đối chiếu dependency, giới hạn đã biết, test baseline và trạng thái Git.

## Gate DoD gần nhất — 2026-08-24

- **Bước 1 PASS:** branch `codex/step1-revalidation-pr`, PR [#1](https://github.com/nkdang2772/video_gensys/pull/1), 2/2 GitHub checks xanh và merge commit `5c41e24` trên `main`.
- Bằng chứng Bước 1: CLI thật `python -m app --version` trả `0.1.0`; option không hợp lệ trả non-zero và thông báo argparse; full CI **94/94 pass**.
- **Bước 2 PASS:** branch `codex/step2-revalidation`, PR [#2](https://github.com/nkdang2772/video_gensys/pull/2), 2/2 GitHub checks xanh và merge commit `e2bd5e4` trên `main`.
- Bằng chứng Bước 2: database mới chạy `alembic upgrade head` đến revision `0002`; raw query trả `journal_mode=wal`, `busy_timeout=5000`; happy/error targeted **3/3 pass**; full CI **95/95 pass**.
- **Bước 3 PASS:** branch `codex/step3-revalidation`, PR [#3](https://github.com/nkdang2772/video_gensys/pull/3), 2/2 GitHub checks xanh và merge commit `4a11233` trên `main`.
- Bằng chứng Bước 3: SQLite CLI liệt kê đúng 10 bảng; toàn bộ cột mục 4; raw insert một record/bảng; foreign key, CHECK và partial unique error paths; full CI **96/96 pass**.
- **Bước 4 PASS:** branch `codex/step4-revalidation`, PR [#4](https://github.com/nkdang2772/video_gensys/pull/4), 2/2 GitHub checks xanh và merge commit `03a64a7` trên `main`.
- Bằng chứng Bước 4: đủ 17 CHECK constraint trong ORM metadata; CRUD trực tiếp 10 model; invariant nhân vật; `alembic check` sạch; full CI **97/97 pass**.
- **Bước 5 PASS:** branch `codex/step5-revalidation`, PR [#5](https://github.com/nkdang2772/video_gensys/pull/5), 2/2 GitHub checks xanh và merge commit `45b990a` trên `main`.
- Bằng chứng Bước 5: `resolve()` chặn traversal/absolute/drive-relative; `to_relative()` chỉ nhận absolute path trong episode root; targeted **9/9 pass**, full CI **99/99 pass**.
- **Bước 6 PASS:** branch `codex/step6-revalidation`, PR [#6](https://github.com/nkdang2772/video_gensys/pull/6), 2/2 GitHub checks xanh và merge commit `e6e8e2a` trên `main`.
- Bằng chứng Bước 6: đủ create/list/get/update/soft delete, slug unique toàn cục, CLI create; targeted **7/7 pass**, full CI **100/100 pass**; BUG-033 đã đóng.
- **Bước 7 PASS:** branch `codex/step7-revalidation`, PR [#7](https://github.com/nkdang2772/video_gensys/pull/7), 2/2 GitHub checks xanh và merge commit `27bd010` trên `main`.
- Bằng chứng Bước 7: snapshot, pin active series references + style anchor, folder tree, rollback disk/database và tính bất biến sau redesign; targeted **6/6 pass**, full CI **101/101 pass**.
- **Bước 8 PASS:** branch `codex/step8-revalidation`, PR [#8](https://github.com/nkdang2772/video_gensys/pull/8), 2/2 GitHub checks xanh và merge commit `bc43965` trên `main`.
- Bằng chứng Bước 8: TXT/CSV/JSON, fixture 80 shot, multiline, thiếu/trùng/unsafe shot ID; targeted **12/12 pass**, full CI **104/104 pass**; BUG-034–036 đã đóng.
- **Bước 9 đang revalidate** trên branch `codex/step9-revalidation`: wrapper đã được kiểm tra bằng WAV thật ngắn/dài/hỏng/zero-duration và test giả lập xác nhận subprocess nhận timeout mặc định đúng **30 giây**. Targeted **5/5 pass**, full regression **105/105 pass**; PR/CI/merge còn chờ.
- Các mô tả “đã hoàn thành” bên dưới là inventory implementation lịch sử, không phải dấu check DoD cho Bước 9–30.

## Tech stack đã chốt

- Python 3.11+; Conda environment chuẩn pin Python 3.11, venv kiểm thử hiện dùng Python 3.12.7.
- Conda quản lý Python, SQLite, FFmpeg/FFprobe và dependency phát triển qua `environment.yml`.
- Streamlit cho giao diện MVP.
- SQLAlchemy 2.x cho ORM.
- SQLite cho database local.
- Alembic cho database migration.
- Pytest cho unit/integration test nền tảng.
- NumPy và Matplotlib cho xử lý PCM/waveform local.
- Pillow cho chuẩn hoá ảnh live JPEG/WebP từ Google Flow thành PNG managed.
- FFmpeg 9/FFprobe trong Conda environment `video-gensystem` cho render/probe motion thật.

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

### Bước 15 — Series/Episode screens

- Streamlit entry point `streamlit_app.py` với router năm màn hình và session-state selection.
- Series screen list/create/open, cấu hình resolution/FPS/aspect ratio.
- Episode screen list/create/open, gọi transactional Episode service để snapshot/pin/folder tree.
- Library root cấu hình bằng `VIDEO_GENSYSTEM_LIBRARY_ROOT`.

### Bước 16 — Import screen

- Nhận script TXT/CSV/JSON bằng upload hoặc local path; preview kết quả parser.
- Transactional script import tạo Scene/Shot và giữ bản source trong episode folder.
- Nhận local WAV folder hoặc multiple WAV uploads, gọi voice auto-link/import service.
- Hiển thị shot list, duration, kết quả liên kết và warning; không silent skip.

### Bước 17 — Shot Manager screen

- Filter theo Scene, bảng inline edit speaker/visual/motion/status.
- Bulk chọn shot và character, chọn primary, gọi service để regenerate batch key.
- Chỉ hiển thị shared character hoặc character đúng Series hiện tại.
- Phát chosen audio theo từng shot; episode chưa có shot hiển thị hướng dẫn import.

### Bước 18 — Reference Library screen

- Tab theo character/style/location/prop/map và nested tab shared/series-specific.
- Create reference, chọn local file hoặc upload version mới.
- Hiển thị current version; nhắc rõ Episode pins được snapshot khi Episode được tạo.
- Test sáu character reference tổng quát có version và được pin đủ khi tạo Episode.

### UI verification

- AppTest end-to-end dùng tên tổng quát: tạo Series, Episode, import script hai shot, link hai WAV thật, mở Shot Manager và Reference Library.
- Các ví dụ “Tam Quốc”, “Xích Bích” trong DoD có thể nhập trực tiếp qua UI nhưng không xuất hiện trong logic production.

### Bước 19 — Job model + enqueue

- Queue service hỗ trợ enqueue, get status và list queued theo Episode/job type.
- Validate job type, priority, JSON payload, max attempts và Shot phải thuộc đúng Episode.
- Thứ tự queue cố định: high, normal, image, gpu, overnight, export; FIFO theo created time và ID trong cùng priority.

### Bước 20 — Atomic worker claim

- Mỗi lần claim mở DBAPI connection riêng, dùng `BEGIN IMMEDIATE`, update running/worker PID rồi commit ngay.
- Handler chạy hoàn toàn ngoài claim transaction; success/failure được ghi bằng transaction ngắn riêng.
- Retry SQLITE_BUSY/SQLITE_LOCKED bằng exponential backoff có jitter và giới hạn số lần thử.
- Poll loop hỗ trợ filter job type, stop event, finite job count và exit khi queue rỗng.
- Integration test hai worker cùng xử lý 20 job; đủ 20 ID duy nhất và cả hai worker đều thực sự nhận job.

### Bước 21 — Stale job recovery

- Timeout mặc định 30 phút, có thể cấu hình bằng `timedelta`.
- Job stale được đánh failed/error stale, tăng attempt và bỏ worker PID.
- Job failed còn attempt tự quay về queued; job đạt max attempts giữ failed.
- Integration test mô phỏng worker chết sau claim và xác nhận job được claim lại bởi worker khác.

### Bước 22 — ImageProvider interface + adapters

- Interface thống nhất `generate(prompt, reference_images, config) -> Path` và cost metadata không dùng mutable global state.
- Google Flow adapter mở localhost task bridge có token cho extension `h2dev_flow`; không gọi Gemini API và không cần API key.
- Extension nhận prompt + pinned reference, điều khiển Flow bằng `chrome.debugger`, tải PNG theo task ID rồi báo kết quả về worker.
- ComfyUI adapter upload pinned references, inject prompt vào API workflow, POST `/prompt`, poll `/history/{id}` và tải `/view`.
- Manual adapter copy PNG vào output managed, không ghi đè source/output cũ.
- Cả ba adapter validate PNG; test protocol Google/ComfyUI bằng transport giả lập và manual bằng file thật.

### Bước 23 — Image generation worker

- Chỉ nhận `image_gen` có Shot; load đúng ReferenceVersion đã pin trong Job payload, không lấy current version mới.
- Provider chạy ngoài DB transaction; Asset image version mới được tạo với `is_chosen=false`, checksum, size, width/height và provenance.
- Job ghi provider cùng cost USD/credit/estimated; bridge token không lưu DB.
- Idempotency theo `workflow_id=job:{id}` tránh sinh Asset trùng nếu worker chết sau commit Asset.
- Provider timeout được failed/increment attempt/requeue đến max attempts; test timeout hai lần và thành công lần ba.
- Test 10 image jobs tạo đúng 10 Asset version.

### Bước 24 — Image Gallery + character batch queue

- Screen thứ sáu hiển thị variation grid, chọn chosen version, queue regenerate với prompt sửa và theo dõi Job.
- Batch pending shots sort theo `character_batch_key`, pinned version IDs và order index; duplicate active jobs bị loại.
- Batch dùng priority overnight, giữ render order độc lập với Shot order.
- Acceptance tự động với 80 shot tổng quát tạo đủ 80 Asset, mỗi Shot có một image.

### Bước 25 — Ken Burns FFmpeg

- `app/motion/kenburns.py` render MP4 bằng FFmpeg `zoompan`, hỗ trợ zoom in/out và pan bốn hướng.
- Validate duration/FPS/zoom/direction, ảnh nguồn, output `.mp4`, không ghi đè và ghi file atomic.
- `probe_video` trả duration, FPS, frame count, width, height và codec.
- Acceptance thật từ ảnh Google Flow: `live_test/kenburns_5s.mp4`, 5.0 giây, 30 FPS, 150 frame, 1376×768, H.264.

### Bước 26 — VideoProvider + Wan/Veo adapters

- Interface `VideoProvider.generate(source_image, prompt, config) -> Path` và cost metadata.
- Wan 2.2 adapter upload source image vào ComfyUI, inject prompt, submit/poll workflow, tải MP4 và validate container.
- Integration test Wan dùng protocol ComfyUI giả lập nhưng MP4 FFmpeg thật; FFprobe xác nhận 12 frame/12 FPS.
- Veo cloud adapter dùng optional Google GenAI SDK, long-running operation, download atomic và mặc định model `veo-3.1-generate-preview`; không live-call để tránh chi phí/API side effect.

### Bước 27 — Motion fill + fallback

- `extend` phát clip một lần, lấy frame cuối và nối đuôi Ken Burns nhẹ tới đúng effective duration.
- `loop` chỉ chạy khi policy được chọn explicit; clip dài hơn target được trim cuối.
- `split` tạo kế hoạch sub-shot ID ổn định (`s042_01`...) với tổng duration khớp shot gốc.
- Generative provider thử tối đa ba lần, sau đó thử sprite renderer nếu có và cuối cùng luôn về Ken Burns.
- Test cả extend/split/loop và Wan fail ba lần → sprite fail → Ken Burns thành công.

### Bước 28 — Motion Queue

- Screen thứ bảy queue Wan/Veo job, hiển thị progress/error, retry job failed, preview MP4 variation và chọn `is_chosen`.
- Motion worker giữ provider/FFmpeg ngoài DB transaction, tạo immutable Asset `video`, metadata/checksum và idempotency theo Job.
- Acceptance queue 15 shot tổng quát; priority GPU, retry reset rõ ràng và chosen motion constraint hoạt động.

### Bước 29 — Preview player

- Screen Preview hỗ trợ Shot, Scene và Full; shot proxy mux voice/visual thành H.264 + AAC để HTML5 player phát đồng bộ.
- Mọi proxy được chuẩn hóa 1280×720, FPS theo Episode; scene/full concat theo `order_index` bằng FFmpeg.
- Shot thiếu chosen visual hoặc file bị mất dùng placeholder đỏ có `shot_id`; danh sách placeholder vẫn chính xác khi tái dùng proxy cache.
- Acceptance thật 3 shot tạo đủ shot proxy, scene preview và full preview 3.021 giây, 1280×720, 12 FPS, H.264/AAC.

### Bước 30 — Asset checker và export package

- Asset checker thực thi toàn bộ nhóm rule tự động mục 17: shot ID/audio/chosen visual, file/checksum/metadata, job unresolved, resolution/FPS/codec, fill policy/timing, placeholder, frame đen/trắng và loop boundary heuristic.
- Nội dung, character consistency, warp/flicker, map, nhịp dựng, music/SFX và seamless loop vẫn được liệt kê là QA thủ công, không báo pass giả.
- Sinh `qa/report.html` và `qa/report.json`; acceptance 3 shot hoàn chỉnh đạt PASS, 0 error/0 warning, timing 3.0/3.0 giây.
- Export hard-link nếu cùng volume, fallback copy; tên media bắt đầu bằng `shot_id`; sinh `project_manifest.json`, `README_IMPORT.txt` và `shot_manifest.csv` UTF-8.
- Yêu cầu Bước 30 ghi 16 cột trong khi doc mục 18 liệt kê 17 trường. Quyết định: CSV giữ đúng 16 trường dựng timeline, còn `notes` nằm trong `project_manifest.json`.
- Rebuild export không xóa package cũ mà đổi tên thành `export_backup_<timestamp>` trước khi tạo package mới.
- Acceptance artifact được giữ tại `live_test/step29_30_acceptance/.../generic-preview-episode` (ignored khỏi Git).
- Không tìm thấy DaVinci Resolve trong registry, Start Menu hoặc các path cài phổ biến trên C:/D:; vì vậy chưa thể xác nhận thao tác import/timeline bằng ứng dụng Resolve thật trên máy này.

### Giới hạn live provider

- Manual provider đã chạy end-to-end bằng PNG thật.
- Google Flow bridge đã chạy live bằng tài khoản Pro và extension thật: prompt được nhận, Flow sinh ảnh, extension tải file về máy và provider tạo PNG managed hợp lệ.
- Live artifact: `live_test/google_flow_live.png`, 1376×768, 1,628,786 byte, SHA-256 `70ab37b201b8a8ec793bf7a67c06c75d642984ce3469dc573bd133cfabbf4a87`.
- Chrome của máy hiện lưu download tại `D:\Download`; cấu hình bằng `VIDEO_GENSYSTEM_FLOW_DOWNLOADS_ROOT` hoặc trường Chrome Downloads folder trong UI.
- Flow trả ảnh live dưới MIME JPEG nên Chrome tự đổi `.png` thành `.jpg`; provider đã hỗ trợ `.png/.jpg/.jpeg/.webp` và chuẩn hoá về PNG.
- Một lượt live tiếp theo đã gửi prompt đúng nhưng cả bốn variation bị Google Flow báo “Không thành công” ở 13%; đây là lỗi dịch vụ/model bên ngoài và không làm hỏng bridge/queue local.
- Extension nguồn được quản lý tại `integrations/h2dev_flow_extension` và sẽ được đồng bộ với bản người dùng đang dùng.
- ComfyUI live acceptance vẫn cần server local đang chạy với model/workflow tương thích.

## Kết quả kiểm thử gần nhất

```text
python -m app --version: 0.1.0
pytest: 92 passed
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
transactional script import và Streamlit AppTest end-to-end, warning/failure rollback,
constraints của chosen asset, bảo mật đường dẫn, queue priority, SQLite lock retry,
hai worker claim đồng thời, stale recovery, ba image provider adapters, retry timeout,
image Asset versioning/cost, gallery UI và batch 80 shot, Ken Burns MP4 thật,
video metadata, Wan/Veo adapters, motion fill/fallback, motion worker, Motion Queue UI,
preview shot/scene/full với placeholder/cache, QA HTML/JSON, export 16 cột và rebuild backup.

## Git

- Foundation commit: `a5a1554 feat: build foundation schema and path safety`
- Status/bug log commit: `11e2866 docs: add project status and bug log`
- Conda commit: `7291ec4 build: add conda environment management`
- GitHub Actions workflow đã được cấu hình cho Python 3.11.
- CI cloud sẽ chạy sau khi repository được push lên GitHub.

## Bước tiếp theo

- Cài/mở DaVinci Resolve rồi import acceptance package hoặc corpus production để hoàn tất DoD GUI còn lại của Bước 30.
- Khi có corpus production, chạy lại end-to-end ở kích thước tập thật; fixture hiện tại chứng minh workflow tổng quát, không hard-code Xích Bích.
- Wan live acceptance vẫn cần ComfyUI đang chạy, workflow Wan 2.2 API JSON và model tương thích; Veo live là optional và có thể phát sinh phí.
