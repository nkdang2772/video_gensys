# Nhật ký lỗi Video GenSystem

**Cập nhật:** 2026-08-24  
**Phạm vi:** Toàn dự án

## Tổng quan

- Lỗi đang mở: **0**
- Lỗi đã đóng: **29**
- Test regression hiện tại: **92/92 pass**

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

## BUG-029 — Status đánh đồng code/test evidence với DoD PASS

- **Trạng thái:** Đã đóng về mặt tài liệu; revalidation vẫn đang mở theo audit
- **Mức độ:** Blocker, governance
- **Phát hiện:** Recheck theo năm quy tắc DoD/test/branch-PR/demo/blocker của người dùng.
- **Triệu chứng:** `status.md` gọi Bước 29–30 hoàn thành dù DaVinci acceptance chưa chạy; các bước provider/UI khác cũng dùng test mock hoặc service test thay cho live/UI DoD.
- **Nguyên nhân:** Trạng thái trước đây theo dõi mức implementation/regression, không tách riêng completion gate nghiêm ngặt.
- **Cách sửa:** Hạ gate chính thức về Bước 1, thêm `status/dod_audit.md` với ma trận 1–30 và ghi rõ mọi khoảng trống/Git deviation; không rewrite lịch sử để tạo bằng chứng giả.
- **Regression kiểm soát:** Mọi cập nhật status sau audit phải ghi riêng `implementation evidence` và `official DoD status`; chỉ chuyển PASS khi có artifact/test/live evidence đúng DoD và dependency đã pass.

## Quy ước cập nhật

Mỗi lỗi mới cần ghi:

1. Mã lỗi và mô tả ngắn.
2. Trạng thái và mức độ.
3. Cách tái hiện hoặc triệu chứng.
4. Nguyên nhân gốc.
5. Thay đổi đã thực hiện.
6. Test ngăn lỗi tái diễn.

Không xóa lỗi đã đóng; giữ lại làm lịch sử kỹ thuật của dự án.
