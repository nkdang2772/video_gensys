# Nhật ký lỗi Video GenSystem

**Cập nhật:** 2026-08-24  
**Phạm vi:** Toàn dự án

## Tổng quan

- Lỗi đang mở: **0**
- Lỗi đã đóng: **44**
- Test regression gần nhất trên `main`: **131/131 pass** (Bước 25, PR #27, merge commit `77af71b`)
- Gate chính thức: **Bước 1–25 PASS**; Bước 26 chưa bắt đầu revalidation.

## OBS-001 — Batch FFprobe 80 WAV từng thiếu file

- **Trạng thái:** Đã xác nhận và xử lý tại BUG-039
- **Phát hiện:** Lượt full regression đầu của Bước 8 import 78/80 WAV và báo thiếu audio cho `s060` cùng một shot khác.
- **Đối chứng:** Test batch 80 WAV chạy riêng pass; lặp tiếp 3/3 lần đều pass 80/80; full suite Bước 8 pass 104/104. Revalidation Bước 9 pass WAV thật ngắn/dài/hỏng/zero-duration, timeout 30 giây và full suite 105/105. Revalidation Bước 10 tiếp tục import đủ 80/80 WAV và full suite 106/106; hiện tượng vẫn không tái hiện.
- **Xử lý hiện tại:** Revalidation Bước 16 tái hiện 79/80 chosen audio, thiếu `s011`; đã bổ sung retry chỉ cho timeout FFprobe và giữ warning nếu hết số lần thử.

## BUG-032 — `to_relative()` chấp nhận input tương đối phụ thuộc working directory

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, an toàn đường dẫn
- **Phát hiện:** Revalidation Bước 5 sau khi PR #4 được merge.
- **Triệu chứng:** Contract yêu cầu `absolute_path`, nhưng hàm gọi `Path.resolve()` trực tiếp nên input như `images/s001.png` có thể được chấp nhận hoặc từ chối tùy current working directory.
- **Nguyên nhân:** Thiếu validation `Path.is_absolute()` trước bước resolve/containment check.
- **Cách sửa:** Từ chối input không absolute bằng `ValueError`; giữ containment check sau resolve; thêm round-trip test `resolve()` → `to_relative()`.
- **Regression test:** `tests/test_paths.py` pass 9/9; full suite pass 99/99.

## BUG-031 — ORM metadata thiếu 17 CHECK constraint của migration

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, schema parity
- **Phát hiện:** Rà soát trực tiếp migration và ORM trong revalidation Bước 4.
- **Triệu chứng:** Database production tạo bởi Alembic có 17 CHECK constraint cho Reference, ReferenceVersion, Shot, Asset và Job; database test tạo bằng `Base.metadata.create_all()` không có các constraint này.
- **Nguyên nhân:** Model chỉ khai báo cột, relationship, unique index/constraint; CHECK constraint mới tồn tại trong `0001_initial.py`.
- **Cách sửa:** Khai báo lại đúng tên và biểu thức của cả 17 CHECK constraint trong `__table_args__`; thêm test khóa tập tên constraint; CRUD test gọi `session.delete()` trực tiếp cho cả 10 model trong một unit-of-work để tránh cascade che coverage.
- **Regression test:** `tests/test_models.py` pass 6/6 không warning; `alembic check` không phát hiện operation mới; full suite pass 97/97.

## BUG-030 — Test schema chưa tách happy/error và chưa khóa contract cột

- **Trạng thái:** Đã đóng
- **Mức độ:** Trung bình, khoảng trống DoD
- **Phát hiện:** Revalidation Bước 3 sau khi PR #2 được merge.
- **Triệu chứng:** Một test duy nhất vừa insert thành công vừa thử partial unique failure; danh sách 10 bảng được kiểm tra nhưng field contract mục 4 chưa được assert tường minh.
- **Nguyên nhân:** Test migration ban đầu ưu tiên smoke test ngắn thay vì chia hai acceptance path độc lập.
- **Cách sửa:** Tách happy/error thành hai test; thêm expected column set cho toàn bộ 10 bảng; error path kiểm tra foreign key, CHECK version dương và partial unique chosen asset.
- **Regression test:** `tests/test_migration.py` pass 2/2; full suite pass 96/96.

## BUG-029 — Bước 2 thiếu error-case test riêng cho Alembic

- **Trạng thái:** Đã đóng
- **Mức độ:** Trung bình, vi phạm quy trình DoD
- **Phát hiện:** Audit tuần tự sau khi Bước 1 được merge bằng PR #1.
- **Triệu chứng:** SQLite/WAL và migration chỉ có happy-path test; chưa chứng minh Alembic thất bại rõ ràng khi người dùng yêu cầu revision không tồn tại.
- **Nguyên nhân:** Test Foundation ban đầu tập trung vào migration/schema thành công và constraint của Bước 3.
- **Cách sửa:** Bổ sung subprocess test chạy `alembic upgrade not-a-real-revision`, yêu cầu return code khác 0 và thông báo không tìm thấy revision.
- **Regression test:** `tests/test_db.py` cùng `tests/test_migration.py` pass 3/3; full suite phải pass trước khi tạo PR Bước 2.

## BUG-001 — SQLAlchemy không suy luận được kiểu `created_at`

- **Trạng thái:** Đã đóng
- **Mức độ:** Blocker
- **Phát hiện:** Khi import ORM models trong lượt test đầu.
- **Triệu chứng:** `sqlalchemy.exc.ArgumentError` vì trường `ReferenceVersion.created_at` dùng `Mapped[Any]`.
- **Nguyên nhân:** SQLAlchemy 2.x không thể ánh xạ `typing.Any` sang SQL type.
- **Cách sửa:** Đổi annotation thành `Mapped[datetime]`, khai báo `DateTime(timezone=True)` và default UTC.
- **Regression test:** Toàn bộ model import và CRUD test chạy thành công.

## BUG-002 — Alembic không bảo đảm thư mục cha của SQLite tồn tại

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao
- **Phát hiện:** Khi kiểm tra lệnh `alembic upgrade head` với database mặc định.
- **Triệu chứng:** Database có thể không mở được nếu thư mục `data/` chưa tồn tại.
- **Nguyên nhân:** Alembic tạo SQLite file nhưng không tự tạo thư mục cha.
- **Cách sửa:** Gọi helper `_ensure_sqlite_parent()` trong `migrations/env.py` trước khi mở engine; thêm `data/.gitkeep`.
- **Regression test:** Upgrade–downgrade–upgrade chạy thành công.

## BUG-003 — Path resolver chưa từ chối đầy đủ đường dẫn Windows có drive

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, liên quan bảo mật
- **Phát hiện:** Khi bổ sung test cho path traversal trên Windows.
- **Triệu chứng:** Dạng `C:Windows\win.ini` không phải absolute path theo mọi API nhưng vẫn có drive component.
- **Nguyên nhân:** Chỉ kiểm tra `Path.is_absolute()` và POSIX absolute path là chưa đủ trên Windows.
- **Cách sửa:** Kiểm tra thêm `PureWindowsPath(raw).drive`; vẫn xác minh resolved path nằm trong episode root.
- **Regression test:** Chặn `../../etc/passwd`, backslash traversal, Windows absolute path và drive-relative path.

## BUG-004 — Venv ban đầu tại ổ D dùng sai Python 3.10

- **Trạng thái:** Đã đóng
- **Mức độ:** Blocker môi trường
- **Phát hiện:** Khi cài package trực tiếp trong `D:\video_gensystem\.venv`.
- **Triệu chứng:** Pip báo project yêu cầu Python `>=3.11`, nhưng venv dùng Python 3.10.6.
- **Nguyên nhân:** Shell elevated trỏ tới Python khác với shell kiểm thử thông thường.
- **Cách sửa:** Tạo lại venv bằng executable Python 3.12.7 tường minh.
- **Regression test:** `python --version`, CLI version, migration, pytest và `pip check` đều pass trong venv mới.

## BUG-005 — Pytest elevated không đọc được temp directory mặc định

- **Trạng thái:** Đã đóng
- **Mức độ:** Trung bình, chỉ ảnh hưởng môi trường test local
- **Phát hiện:** Khi chạy test trực tiếp tại ổ D bằng tài khoản elevated.
- **Triệu chứng:** `PermissionError` tại `%LOCALAPPDATA%\Temp\pytest-of-khoad`.
- **Nguyên nhân:** Quyền sở hữu/quyền đọc của temp directory khác giữa runtime thường và runtime elevated.
- **Cách sửa:** Chạy pytest với `--basetemp .venv\pytest-tmp` để temp nằm trong thư mục dự án đã được cấp quyền.
- **Regression test:** 15 test pass trực tiếp tại `D:\video_gensystem`.

## BUG-006 — Schema Foundation chưa hỗ trợ soft delete và reference active

- **Trạng thái:** Đã đóng
- **Mức độ:** Blocker cho Bước 6–7
- **Phát hiện:** Khi đối chiếu yêu cầu Series soft delete và pin reference active với schema `0001`.
- **Triệu chứng:** `Series` không có lifecycle field; `Reference` không thể phân biệt active/inactive.
- **Nguyên nhân:** Hai field này không nằm trong data model ban đầu nhưng là dependency trực tiếp của build order.
- **Cách sửa:** Tạo migration mới `0002_series_lifecycle`, thêm `series.deleted_at` và `reference.is_active`; không sửa migration lịch sử `0001`.
- **Regression test:** Test list/get sau soft delete và test bỏ qua inactive reference khi pin.

## BUG-007 — Tạo Episode có nguy cơ để lại database hoặc folder orphan

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao
- **Phát hiện:** Khi thiết kế transaction kết hợp SQLite và filesystem.
- **Triệu chứng:** Database transaction không tự rollback thao tác tạo folder.
- **Nguyên nhân:** SQLite và filesystem không có distributed transaction chung.
- **Cách sửa:** Service sở hữu transaction; ghi database và tạo folder trong cùng operation, đồng thời xóa chính xác episode root vừa tạo khi filesystem, flush hoặc commit thất bại.
- **Regression test:** Mô phỏng disk failure sau khi đã tạo folder con và database unique failure sau khi tạo folder; không còn Episode/pin/folder orphan.

## BUG-008 — Reference thiếu current version có thể tạo Episode không tái lập được

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao
- **Phát hiện:** Khi triển khai EpisodeReferencePin.
- **Triệu chứng:** Reference active hoặc style anchor có `current_version` không tồn tại thì không thể tạo pin chính xác.
- **Nguyên nhân:** Thiếu validation trước khi tạo Episode.
- **Cách sửa:** Mọi reference cần pin phải có `current_version > 0` và đúng `ReferenceVersion`; nếu thiếu, toàn bộ operation rollback và folder được dọn.
- **Regression test:** Reference khai báo version nhưng thiếu record tương ứng bị từ chối; database và filesystem vẫn sạch.

## BUG-009 — FFprobe chạy trực tiếp từ Conda package cache bị thiếu DLL

- **Trạng thái:** Đã đóng
- **Mức độ:** Trung bình, môi trường test
- **Phát hiện:** Lượt test WAV thật đầu tiên.
- **Triệu chứng:** FFprobe exit code `3221225781` và không có stderr.
- **Nguyên nhân:** Executable trong thư mục package cache không có runtime DLL/PATH đầy đủ như executable trong Conda environment.
- **Cách sửa:** Fixture dò executable theo PATH và các Conda environment, sau đó chạy `ffprobe -version` để chỉ chọn binary hoạt động; package cache chỉ là fallback.
- **Regression test:** WAV ngắn, dài, hỏng, zero-duration và batch 80 WAV đều chạy bằng FFprobe thật.

## BUG-010 — WAV hỏng đầu tiên chặn WAV hợp lệ cùng shot

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao
- **Phát hiện:** Rà soát failure path của voice auto-link.
- **Triệu chứng:** Shot bị đánh dấu đã claim trước khi probe; candidate hợp lệ xuất hiện sau bị coi là duplicate và bỏ qua.
- **Nguyên nhân:** Cập nhật `claimed_shots` quá sớm.
- **Cách sửa:** Chỉ claim shot sau khi FFprobe thành công; candidate sau vẫn được thử nếu candidate trước hỏng.
- **Regression test:** File `a_s001.wav` hỏng và `b_s001.wav` hợp lệ cho ra một Asset cùng warning rõ ràng cho file hỏng.

## BUG-011 — Shot ID không an toàn có thể đi vào tên asset đích

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, liên quan bảo mật/path safety
- **Phát hiện:** Rà soát đường dẫn copy voice.
- **Triệu chứng:** Shot ID chứa separator hoặc `..` có thể tạo tên/path không hợp lệ.
- **Nguyên nhân:** Parser và import service chưa giới hạn character set của shot ID.
- **Cách sửa:** Chỉ chấp nhận chữ, số, `_` và `-`; import service kiểm tra lại dữ liệu database trước mọi thao tác copy.
- **Regression test:** Parser từ chối `../s001`; voice import từ chối unsafe shot ID và không tạo file.

## BUG-012 — Validator Shot quá sớm cản update characters và primary cùng lúc

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao
- **Phát hiện:** Khi triển khai Shot update service.
- **Triệu chứng:** Đổi từ primary cũ sang tổ hợp characters/primary mới có thể fail ở field đầu tiên dù trạng thái cuối hợp lệ.
- **Nguyên nhân:** Cross-field invariant được kiểm tra trong validator riêng của từng field trước khi field còn lại được gán.
- **Cách sửa:** Field validator chỉ kiểm tra type/duplicate cục bộ; invariant chéo được kiểm tra bằng method và Session `before_flush`. Service gán characters trước primary trong savepoint.
- **Regression test:** Đổi atomic từ `old` sang `[new, support]` với primary `new` thành công.

## BUG-013 — Explicit reference ID có underscore bị đổi thành dấu gạch ngang

- **Trạng thái:** Đã đóng
- **Mức độ:** Trung bình
- **Phát hiện:** Rà soát CLI DoD `tao_thao` và character IDs.
- **Triệu chứng:** Dùng slugifier của Series biến `tao_thao` thành `tao-thao`, gây lệch với ID trong `characters_json`.
- **Nguyên nhân:** Series slug và reference/entity ID dùng chung normalization policy.
- **Cách sửa:** Reference có normalizer riêng, giữ `_` khi người dùng cung cấp explicit slug; slug tự sinh từ name vẫn thân thiện.
- **Regression test:** CLI và service giữ nguyên explicit reference slug `tao_thao`/`character_example`.

## BUG-014 — ReferenceVersion có thể bị sửa sau khi persist

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao
- **Phát hiện:** Khi triển khai yêu cầu immutable version.
- **Triệu chứng:** ORM mặc định cho phép UPDATE file path, checksum, version hoặc descriptor cũ.
- **Nguyên nhân:** Database constraint chỉ bảo đảm unique version, không cấm UPDATE.
- **Cách sửa:** Session `before_flush` kiểm tra history của mọi scalar field immutable và raise `ImmutableReferenceVersionError`.
- **Regression test:** Sửa `file_path` của version cũ bị từ chối; file đã copy vẫn giữ nguyên khi source thay đổi.

## BUG-015 — Shot update lỗi có thể để object mang giá trị tạm trong Session

- **Trạng thái:** Đã đóng
- **Mức độ:** Trung bình
- **Phát hiện:** Rà soát failure path của update service.
- **Triệu chứng:** Validator raise sau khi đã gán attribute có thể để object dirty nếu caller quên rollback.
- **Nguyên nhân:** Update nhiều field không có savepoint riêng.
- **Cách sửa:** Bọc update và bulk update trong nested transaction; lỗi rollback về state trước operation.
- **Regression test:** Update primary không thuộc character set raise và object vẫn giữ primary hợp lệ cũ.

## BUG-016 — Protobuf warning làm AppTest fail dưới chế độ warning-as-error

- **Trạng thái:** Đã đóng
- **Mức độ:** Trung bình, dependency test
- **Phát hiện:** Lượt Streamlit AppTest đầu tiên trên Python 3.12.
- **Triệu chứng:** Protobuf extension cũ phát `DeprecationWarning`, bị pytest `-W error` nâng thành lỗi import Streamlit.
- **Nguyên nhân:** Streamlit 1.37 trong môi trường local dùng protobuf extension có API sắp bị Python 3.14 loại bỏ.
- **Cách sửa:** Chỉ suppress DeprecationWarning bên thứ ba trong scope import AppTest; warning của code dự án vẫn là error.
- **Regression test:** Full suite chạy `-W error`, AppTest end-to-end pass.

## BUG-017 — Shot Manager lộ character reference của series khác

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, data scope
- **Phát hiện:** Rà soát character selector trên Shot Manager.
- **Triệu chứng:** Query ban đầu lấy mọi active character reference trong database.
- **Nguyên nhân:** Thiếu điều kiện shared-or-owning-series.
- **Cách sửa:** Chỉ lấy `shared_across_series` hoặc `owning_series_id` bằng Series của Episode hiện tại.
- **Regression test:** AppTest mở Shot Manager trong đúng Episode context; query production đã giới hạn scope.

## BUG-018 — Shot Manager chưa xử lý Episode rỗng trước data editor

- **Trạng thái:** Đã đóng
- **Mức độ:** Trung bình
- **Phát hiện:** Rà soát luồng mở Episode trước khi import script.
- **Triệu chứng:** Data editor có thể nhận DataFrame không cột cùng danh sách disabled columns không tồn tại.
- **Nguyên nhân:** Thiếu empty-state guard.
- **Cách sửa:** Hiển thị hướng dẫn “Import a script first” và return trước khi tạo editor.
- **Regression test:** AppTest mở Shot Manager ngay sau khi tạo Episode, không exception.

## BUG-019 — WAV uploads trùng filename có thể ghi đè trong staging

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, no-silent-overwrite
- **Phát hiện:** Rà soát multiple-file uploader.
- **Triệu chứng:** Hai uploaded file cùng basename sẽ ghi đè trong temporary folder trước khi import service thấy chúng.
- **Nguyên nhân:** Staging loop chưa kiểm tra filename case-insensitive.
- **Cách sửa:** Track normalized basename và từ chối duplicate trước mọi overwrite.
- **Regression test:** Logic staging dùng safe basename và explicit duplicate error; voice service vẫn xử lý warning/rollback như trước.

## BUG-020 — Raw SQLite datetime adapter deprecated trên Python 3.12

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, worker blocker
- **Phát hiện:** Chạy queue test với `-W error`.
- **Triệu chứng:** Atomic claim fail khi bind trực tiếp timezone-aware `datetime` vào raw sqlite3 cursor.
- **Nguyên nhân:** Default datetime adapter của Python sqlite3 đã deprecated từ Python 3.12.
- **Cách sửa:** Bind timestamp UTC thành chuỗi ISO theo đúng định dạng SQLite/SQLAlchemy, không dùng adapter deprecated.
- **Regression test:** Tất cả claim/concurrent/recovery test chạy dưới `-W error`.

## BUG-021 — Output không hợp lệ có thể để Job mắc ở running

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, queue lifecycle
- **Phát hiện:** Rà soát failure path của worker sau handler.
- **Triệu chứng:** Nếu handler trả payload không JSON-serializable, `mark_job_done` raise ngoài exception handler và Job còn running.
- **Nguyên nhân:** Khối try ban đầu chỉ bao quanh handler, không bao quanh bước hoàn tất Job.
- **Cách sửa:** Đưa cả handler và `mark_job_done` vào cùng failure boundary; lỗi completion chuyển Job sang failed và tăng attempt.
- **Regression test:** Handler trả set trong output bị đánh failed, tăng attempt; stale recovery vẫn là lớp bảo vệ cuối khi process chết đột ngột.

## BUG-022 — Registry rỗng có thể vô tình kích hoạt provider thật

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, external side effect
- **Phát hiện:** Review dependency injection của image worker.
- **Triệu chứng:** Caller truyền `{}` để cấm provider nhưng biểu thức fallback coi dict rỗng là false và tự tạo Google/ComfyUI/manual adapters.
- **Nguyên nhân:** Dùng `providers or default_image_providers()` thay vì phân biệt rõ `None` với mapping rỗng.
- **Cách sửa:** Chỉ tạo default registry khi `providers is None`; mapping rỗng giữ nguyên và job fail rõ provider unavailable.
- **Regression test:** Truyền registry rỗng làm Job failed rõ ràng và monkeypatch xác nhận default factory không được gọi.

## BUG-023 — Filename reference có thể phá multipart upload ComfyUI

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, request integrity
- **Phát hiện:** Security review phần tự dựng multipart bằng standard library.
- **Triệu chứng:** Filename chứa quote hoặc CR/LF có thể thay đổi Content-Disposition/header của request upload.
- **Nguyên nhân:** Dùng trực tiếp basename local trong multipart header.
- **Cách sửa:** Từ chối quote/CR/LF trước khi dựng request; upload explicit `type=input` và `overwrite=true`.
- **Regression test:** ComfyUI adapter test xác minh reference node nhận đúng managed upload name.

## BUG-024 — Google provider triển khai sai kênh người dùng thực tế

- **Trạng thái:** Đã đóng
- **Mức độ:** Blocker, sai integration contract
- **Phát hiện:** Người dùng xác nhận đang dùng Google Flow qua extension `h2dev_flow`, không dùng Gemini API.
- **Triệu chứng:** Adapter cũ yêu cầu `GEMINI_API_KEY` và không thể tận dụng phiên đăng nhập/Flow workflow hiện có.
- **Nguyên nhân:** Diễn giải “Nano Banana qua Gemini API” theo REST API mà chưa đối chiếu tool thực tế của người dùng.
- **Cách sửa:** Thay toàn bộ Google runtime bằng localhost bridge có token giữa Python worker và Chrome extension; provider ID đổi thành `google_flow`.
- **Regression test:** Integration test mở bridge thật, extension simulator lấy prompt/reference, tạo download theo task ID và trả PNG; không có request Gemini.

## BUG-025 — Chrome đổi đuôi ảnh Flow và Downloads root không trùng mặc định

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, chặn live acceptance
- **Phát hiện:** Bài test Google Flow live bằng tài khoản Pro và extension thật.
- **Triệu chứng:** Flow sinh và extension tải ảnh thành công nhưng provider báo không tìm thấy `C:\Users\khoad\Downloads\...png`.
- **Nguyên nhân:** Chrome của máy lưu tại `D:\Download`; ảnh Flow có MIME JPEG nên Chrome tự đổi tên đích `.png` thành `.jpg`.
- **Cách sửa:** Thêm cấu hình/env `VIDEO_GENSYSTEM_FLOW_DOWNLOADS_ROOT`; provider chỉ dò các suffix ảnh cho phép trong Downloads root đã resolve, chuyển JPEG/WebP sang PNG bằng Pillow và vẫn kiểm tra path containment/no-overwrite.
- **Regression test:** Extension simulator ghi JPEG với đuôi `.jpg` dù task yêu cầu `.png`; provider tìm đúng file, tạo PNG hợp lệ và cleanup source. Full suite 82/82 pass.
- **Live verification:** Artifact `live_test/google_flow_live.png` là PNG 1376×768, SHA-256 `70ab37b201b8a8ec793bf7a67c06c75d642984ce3469dc573bd133cfabbf4a87`.

## BUG-026 — Test chọn nhầm FFmpeg không có encoder H.264

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, chặn Bước 25–27
- **Phát hiện:** Lượt test Ken Burns media thật đầu tiên.
- **Triệu chứng:** Sáu motion test fail với `Unknown encoder 'libx264'` dù executable FFmpeg vẫn chạy được.
- **Nguyên nhân:** Fixture chọn FFmpeg đầu tiên trong một Conda environment cũ (`speed_est`), binary đó không được build với libx264.
- **Cách sửa:** Tạo environment chuẩn `video-gensystem` từ `environment.yml`; fixture ưu tiên environment này và chỉ nhận FFmpeg khi danh sách encoder có `libx264`.
- **Regression test:** Ken Burns 5 giây tạo đúng 150 frame/30 FPS ở acceptance thật; motion suite 7/7 và full suite 89/89 pass.

## BUG-027 — Proxy cache làm mất trạng thái placeholder

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, QA integrity
- **Phát hiện:** Review lần hai sau acceptance preview đầu tiên.
- **Triệu chứng:** Khi shot/full proxy đã tồn tại và được tái dùng, result trả danh sách placeholder rỗng dù shot vẫn thiếu chosen visual.
- **Nguyên nhân:** Fast path của cache return trước khi kiểm tra chosen asset và file thật.
- **Cách sửa:** Tính trạng thái visual/placeholder trước cache return; sequence cache cũng dựng lại danh sách placeholder từ DB + filesystem.
- **Regression test:** Render full preview có `s003` thiếu visual, gọi lại với `force=false` vẫn trả chính xác `("s003",)`.

## BUG-028 — Export cũ chặn rebuild hoặc dễ dẫn đến xóa thủ công

- **Trạng thái:** Đã đóng
- **Mức độ:** Trung bình, recoverability
- **Phát hiện:** Review workflow export lặp lại sau khi editor yêu cầu package mới.
- **Triệu chứng:** Folder `/export` không rỗng làm lần export sau thất bại; giải pháp thủ công dễ xóa nhầm package đã giao.
- **Nguyên nhân:** Chưa có lifecycle an toàn cho package export trước đó.
- **Cách sửa:** Khi người dùng chọn rebuild, rename package hiện tại thành `export_backup_<timestamp>` rồi tạo package mới; không recursive delete/overwrite.
- **Regression test:** Export 3 shot hai lần, package mới hợp lệ và đúng một backup cũ vẫn tồn tại.

## BUG-033 — Series update lỗi vẫn có thể để lại thay đổi một phần

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, transaction/data integrity
- **Phát hiện:** Revalidation Bước 6 với tổ hợp update slug hợp lệ và name rỗng.
- **Triệu chứng:** `update_series()` raise `ValueError` cho name rỗng nhưng ORM object vẫn giữ slug mới ở trạng thái dirty; một `commit()` sau đó có thể lưu slug dù update đã báo thất bại.
- **Nguyên nhân:** Hàm gán slug vào model trước khi validate toàn bộ trường đầu vào.
- **Cách sửa:** Chuẩn hóa và validate tất cả thay đổi vào bản sao trước; chỉ mutate ORM model sau khi mọi validation đều pass.
- **Regression test:** Update đồng thời `slug="unexpected-slug"` và `name="   "` phải raise; commit/refresh sau lỗi vẫn giữ nguyên name và slug cũ.

## BUG-034 — Record rỗng bỏ qua kiểm tra thiếu shot_id

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, parser/data integrity
- **Phát hiện:** Revalidation Bước 8 với JSON `[{}]` và CSV row rỗng có delimiter.
- **Triệu chứng:** `normalize_records()` bỏ qua record không có giá trị nên parser trả danh sách rỗng thay vì `ParseError` cho shot thiếu ID.
- **Nguyên nhân:** Blank-record shortcut chạy trước validation `shot_id`.
- **Cách sửa:** Mọi record do parser tạo đều phải qua validation; dòng CSV vật lý trống vẫn do `csv` tự bỏ qua.
- **Regression test:** JSON `[{}]` phải raise `ParseError` chứa `Missing shot_id`.

## BUG-035 — CSV quote chưa đóng được chấp nhận

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, parser/data integrity
- **Phát hiện:** Revalidation Bước 8 với quoted field kết thúc file khi chưa đóng quote.
- **Triệu chứng:** CSV lỗi cú pháp vẫn được parse thành một Shot hợp lệ.
- **Nguyên nhân:** `csv.DictReader` dùng mặc định `strict=False`.
- **Cách sửa:** Khởi tạo reader với `strict=True` và chuyển `csv.Error` thành `ParseError` có source context.
- **Regression test:** Quoted TEXT chưa đóng phải raise `ParseError` chứa `Invalid CSV`.

## BUG-036 — TXT parser làm mất dòng trống trong multiline

- **Trạng thái:** Đã đóng
- **Mức độ:** Trung bình, content fidelity
- **Phát hiện:** Revalidation Bước 8 với hai paragraph trong TEXT/VISUAL.
- **Triệu chứng:** Dòng trống nội bộ bị collapse, làm thay đổi bố cục nội dung so với script nguồn.
- **Nguyên nhân:** Khi nối dòng kế tiếp, parser gọi `rstrip("\n")` và xóa newline đã ghi cho dòng trống.
- **Cách sửa:** Nối dòng tiếp theo mà không xóa newline đã tích lũy; bước normalize chỉ loại whitespace ngoài cùng.
- **Regression test:** TEXT và VISUAL có một dòng trống giữa hai đoạn phải giữ đúng `"line 1\n\nline 2"`.

## BUG-037 — Sửa tại chỗ descriptor JSON né được immutable guard

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, tính bất biến dữ liệu
- **Phát hiện:** Revalidation Bước 11 với mutation `version.descriptor_json["label"] = ...`.
- **Triệu chứng:** Gán lại toàn bộ field bị chặn, nhưng sửa trực tiếp dictionary không làm SQLAlchemy đánh dấu `ReferenceVersion` dirty nên `before_flush` không chạy.
- **Nguyên nhân:** Cột JSON chưa dùng mutable change tracking.
- **Cách sửa:** Áp dụng `MutableDict.as_mutable(JSON)` cho `ReferenceVersion.descriptor_json`; immutable listener hiện nhận và từ chối mutation tại chỗ.
- **Regression test:** Mutation tại chỗ phải raise `ImmutableReferenceVersionError`; rollback/refresh giữ descriptor gốc. Targeted 8/8, full 107/107 và `alembic check` sạch.

## BUG-038 — Chuỗi characters_json bị tách thành nhiều character ID

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, data integrity
- **Phát hiện:** Revalidation Bước 13 với `characters_json="hero"`.
- **Triệu chứng:** Service tạo Shot với `characters_json=["h", "e", "r", "o"]` thay vì từ chối sai kiểu.
- **Nguyên nhân:** `_normalize_characters()` gọi `list(value)` trước khi kiểm tra input là list/tuple; Python coi chuỗi là iterable ký tự.
- **Cách sửa:** Từ chối mọi input không phải `list` hoặc `tuple` trước khi sao chép/validate nội dung.
- **Regression test:** Truyền chuỗi phải raise `ValueError` và không tạo Shot. Targeted 6/6, full 109/109.

## BUG-039 — FFprobe timeout thoáng qua làm batch UI chỉ import 79/80 WAV

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, acceptance/import reliability
- **Phát hiện:** Revalidation Bước 16 bằng AppTest import 80 WAV thật.
- **Triệu chứng:** Một lượt AppTest vượt timeout 20 giây; DB còn lại có 80 Shot nhưng chỉ 79 chosen audio, thiếu `s011`. Lượt retry sau đó đạt 80/80.
- **Nguyên nhân:** Một FFprobe subprocess có thể timeout thoáng qua; Voice import coi mọi `FFprobeError` là lỗi cuối của file và tiếp tục batch, nên một shot hợp lệ bị thiếu audio.
- **Cách sửa:** Thêm `FFprobeTimeoutError` riêng; Voice import retry tối đa 2 lần chỉ cho timeout. File hỏng và lỗi metadata vẫn không retry, vẫn sinh warning rõ ràng.
- **Regression test:** Mock timeout lần đầu và metadata hợp lệ lần hai phải tạo một chosen Asset, không warning; AppTest UI import 80/80 WAV. Targeted liên quan 18/18, full 117/117.

## BUG-040 — Bulk assign không chọn shot báo thành công giả

- **Trạng thái:** Đã đóng
- **Mức độ:** Trung bình, UX/data integrity
- **Phát hiện:** Revalidation Bước 17 bằng Streamlit AppTest.
- **Triệu chứng:** Nhấn `Apply bulk characters` khi chưa chọn shot hiển thị `Updated 0 shots`, khiến thao tác không hợp lệ trông như đã thành công.
- **Nguyên nhân:** UI gọi `bulk_update_shots()` với danh sách rỗng; service chủ ý trả danh sách rỗng cho no-op nhưng màn hình không validate ý định người dùng.
- **Cách sửa:** Shot Manager từ chối danh sách chọn rỗng trước khi mở transaction và hiển thị lỗi `Select at least one shot for bulk assignment.`
- **Regression test:** AppTest tạo Episode có Shot, mở Shot Manager, nhấn bulk apply khi không chọn shot và xác nhận lỗi; targeted 13/13, full 120/120.

## BUG-041 — Job đúng bằng stale timeout bị recovery sớm

- **Trạng thái:** Đã đóng
- **Mức độ:** Trung bình, queue lifecycle
- **Phát hiện:** Revalidation Bước 21 đối chiếu điều kiện `running > timeout` trong DoD.
- **Triệu chứng:** Job có `started_at` đúng 30 phút trước thời điểm recovery bị đánh `stale`, tăng attempt và requeue dù chưa vượt timeout.
- **Nguyên nhân:** Query dùng `started_at <= stale_before`, bao gồm cả boundary bằng timeout.
- **Cách sửa:** Đổi predicate thành `started_at < stale_before`; job chỉ stale khi thời gian chạy thực sự lớn hơn timeout.
- **Regression test:** Job đúng 30 phút phải giữ `running`, attempt/worker PID không đổi; job 31 phút vẫn requeue và job hết attempt vẫn failed. Targeted 3/3, full 125/125.

## BUG-042 — Cost metadata chấp nhận NaN hoặc ném lỗi thô

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, billing/metadata integrity
- **Phát hiện:** Revalidation Bước 22 khi kiểm tra cost fields trên cả ba ImageProvider.
- **Triệu chứng:** `cost_usd="not-a-number"` ném `ValueError` thay vì `ProviderError`; `NaN` vượt qua kiểm tra số âm và có thể đi vào Job metadata.
- **Nguyên nhân:** Validator gọi `float()` trực tiếp và chỉ kiểm tra `< 0`, không bắt lỗi chuyển đổi hoặc kiểm tra số hữu hạn.
- **Cách sửa:** Chuẩn hóa cost qua helper chung, bắt `TypeError`/`ValueError`, yêu cầu số hữu hạn và không âm trước khi tạo `ProviderCost`.
- **Regression test:** Google Flow, ComfyUI và manual trả cost metadata đúng; chuỗi không phải số, `NaN` và số âm đều raise `ProviderError`. Targeted 2/2, full 126/126.

## BUG-043 — AppTest Image Gallery phụ thuộc tên element nội bộ của Streamlit

- **Trạng thái:** Đã đóng
- **Mức độ:** Trung bình, CI portability
- **Phát hiện:** CI push đầu tiên của PR #26 Bước 24; local 129/129 nhưng GitHub CI 128 pass/1 fail.
- **Triệu chứng:** `at.get("imgs")` trả 2 trên Streamlit local nhưng trả danh sách rỗng trên phiên bản CI, dù UI vẫn render đủ hai variation và hai nút chọn.
- **Nguyên nhân:** Test phụ thuộc tên element-tree nội bộ `imgs`, không phải contract/key ổn định của ứng dụng.
- **Cách sửa:** Xác nhận grid bằng hai button key `gallery_choose_*` và đúng một button disabled cho chosen asset.
- **Regression test:** Targeted 4/4 và full 129/129 pass lại local trước khi push CI mới.

## BUG-044 — FFprobe timeout thoáng qua vẫn ảnh hưởng caller ngoài voice import

- **Trạng thái:** Đã đóng
- **Mức độ:** Cao, media reliability
- **Phát hiện:** Full regression đầu của Bước 25: 129 pass/1 fail tại WAV thật 0,125 giây do subprocess FFprobe timeout 30 giây; chạy riêng ngay sau đó pass.
- **Triệu chứng:** BUG-039 đã retry ở Voice import, nhưng caller trực tiếp của `probe_audio()`/`probe_video()` vẫn thất bại khi FFprobe timeout thoáng qua.
- **Nguyên nhân:** Retry được đặt ở service Voice thay vì wrapper media dùng chung.
- **Cách sửa:** Wrapper chung retry tối đa hai lần chỉ cho `TimeoutExpired`; OSError/metadata/file hỏng vẫn fail ngay, timeout liên tục vẫn raise `FFprobeTimeoutError`.
- **Regression test:** Giả lập timeout lần đầu rồi gọi FFprobe thật lần hai phải pass; timeout liên tục phải gọi đúng hai lần với 30 giây rồi raise. Targeted liên quan 8/8, full 131/131.

## Quy ước cập nhật

Mỗi lỗi mới cần ghi:

1. Mã lỗi và mô tả ngắn.
2. Trạng thái và mức độ.
3. Cách tái hiện hoặc triệu chứng.
4. Nguyên nhân gốc.
5. Thay đổi đã thực hiện.
6. Test ngăn lỗi tái diễn.

Không xóa lỗi đã đóng; giữ lại làm lịch sử kỹ thuật của dự án.
