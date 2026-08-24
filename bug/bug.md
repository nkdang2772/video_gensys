# Nhật ký lỗi Video GenSystem

**Cập nhật:** 2026-08-24  
**Phạm vi:** Phần A — Foundation

## Tổng quan

- Lỗi đang mở: **0**
- Lỗi đã đóng: **11**
- Test regression hiện tại: **46/46 pass**

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

## Quy ước cập nhật

Mỗi lỗi mới cần ghi:

1. Mã lỗi và mô tả ngắn.
2. Trạng thái và mức độ.
3. Cách tái hiện hoặc triệu chứng.
4. Nguyên nhân gốc.
5. Thay đổi đã thực hiện.
6. Test ngăn lỗi tái diễn.

Không xóa lỗi đã đóng; giữ lại làm lịch sử kỹ thuật của dự án.
