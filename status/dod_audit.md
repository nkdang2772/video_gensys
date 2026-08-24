# Audit DoD và quy trình phát triển

**Ngày audit:** 2026-08-24  
**Phạm vi:** Bước 1–30  
**Chuẩn áp dụng:** không skip DoD; happy path + error case trước khi qua bước; một bước/một branch/một PR/một merge; demo ở cuối phần; blocker quá một ngày phải alert.

## Kết luận gate

- **Gate chính thức hiện tại: Bước 1 — NOT PASS.** CI workflow đã được viết nhưng chưa có remote/CI run để chứng minh “Commit chạy CI”. Bước 1 chỉ có test version happy path, chưa có error-case test theo quy tắc mới.
- Vì vậy không bước nào sau Bước 1 được đánh dấu check chính thức cho đến khi gate này được đóng và các bước được revalidate theo thứ tự dependency.
- Code và test đã tồn tại tới Bước 30 là bằng chứng kỹ thuật có thể tái sử dụng khi revalidate; chúng không tự động biến thành DoD PASS.
- Không rewrite lịch sử Git để giả lập branch/PR đã không tồn tại. Các sai lệch lịch sử được giữ nguyên và công khai trong audit này.

## Ma trận DoD

| Bước | Bằng chứng hiện có | Khoảng trống nghiêm ngặt | Trạng thái chính thức |
|---:|---|---|---|
| 1 | Repo, stack, version CLI, workflow CI | Không remote/CI run; thiếu error-case test | **NOT PASS — current gate** |
| 2 | Alembic chạy local; WAL/busy timeout test | Thiếu error-case test riêng; dependency 1 chưa pass | **NOT CHECKED** |
| 3 | Migration 10 bảng; raw SQL insert/constraint tests | Dependency upstream chưa pass | **NOT CHECKED** |
| 4 | CRUD mọi model; invariant happy/error | Dependency upstream chưa pass | **NOT CHECKED** |
| 5 | Resolve path hợp lệ và traversal error tests | Dependency upstream chưa pass | **NOT CHECKED** |
| 6 | 5 Series tests + CLI create | Chưa revalidate sau gate 1–5 | **NOT CHECKED** |
| 7 | Snapshot/pin và disk/database rollback tests | Chưa revalidate sau gate 6 | **NOT CHECKED** |
| 8 | Fixture 80 shot, multiline, missing/duplicate errors | Chưa revalidate sau gate 7 | **NOT CHECKED** |
| 9 | WAV short/long/broken/zero thật | Chưa revalidate dependency/path/toolchain | **NOT CHECKED** |
| 10 | 80 WAV tổng quát, unmatched/broken/rollback/reimport | Chưa revalidate 8–9 | **NOT CHECKED** |
| 11 | CLI v1–v3, immutable/checksum/error tests | Chưa revalidate dependency | **NOT CHECKED** |
| 12 | Order-independent key, null/empty, duplicate error | Chưa revalidate dependency | **NOT CHECKED** |
| 13 | CRUD/invariant; bulk 20 recompute | Chưa revalidate 12 | **NOT CHECKED** |
| 14 | WAV 5 phút → 10 segment, drift ≤0.1s | Không có error-case test riêng cho cutter/waveform | **NOT PASS (test gap)** |
| 15 | AppTest tạo Series/Episode tổng quát | Không có error-case test riêng cho hai screen | **NOT PASS (test gap)** |
| 16 | AppTest import script + WAV và thấy shots | Error paths ở parser/service; chưa có UI error-path acceptance riêng | **PARTIAL — not checked** |
| 17 | Service bulk 20; screen mở được | Chưa test UI sửa 10, filter scene, bulk assign 20 | **NOT PASS** |
| 18 | Service tạo/pin 6 references; screen mở được | Chưa upload 6 versions qua UI rồi kiểm tra Episode pin | **NOT PASS** |
| 19 | Enqueue/order/error tests | Chưa revalidate upstream | **NOT CHECKED** |
| 20 | 2 workers/20 jobs exactly once; busy retry/error | Chưa revalidate 19 | **NOT CHECKED** |
| 21 | Stale recovery + max-attempt error | Chưa revalidate 20 | **NOT CHECKED** |
| 22 | Manual live; Google Flow live; ComfyUI protocol mocked | Chưa generate ảnh bằng ComfyUI server/model thật | **NOT PASS — live gap** |
| 23 | 10 jobs/assets + timeout retry bằng provider test | Dependency 22 chưa pass | **BLOCKED BY 22** |
| 24 | Batch 80 synchronous bằng manual provider | Chưa chạy UI/overnight acceptance và kiểm tra sáng hôm sau | **NOT PASS** |
| 25 | MP4 5s thật, FFprobe duration/frame/FPS | Có thể revalidate độc lập sau deps 5/9 | **TECHNICAL PASS; not officially checked** |
| 26 | Wan protocol mocked + MP4 thật; Veo client injected | Chưa sinh clip bằng ComfyUI Wan/model thật | **NOT PASS — live gap** |
| 27 | Extend/split/loop/fallback tests thật bằng FFmpeg | Dependency 26 chưa pass | **BLOCKED BY 26** |
| 28 | Queue 15 bằng provider test; screen mở được | Chưa queue/retry/chọn version qua UI acceptance | **NOT PASS** |
| 29 | 3-shot/scene/full FFmpeg acceptance + placeholder error | Dependency 28 chưa pass | **BLOCKED BY 28** |
| 30 | QA PASS; package 16 cột; export profile từ chối FPS không tương thích; proxy/manifest 24 FPS; Resolve 21 nhận 24.000 FPS, 1280×720, 48 kHz/2 ch; Timeline 2 phát hết đến `01:00:03:01` và lưu | Technical/live acceptance đã đủ, nhưng dependency 28→29 và gate Bước 1 chưa pass | **TECHNICAL/LIVE PASS; OFFICIAL NOT CHECKED** |

## Audit test policy

- Full suite hiện tại: **93 passed**; đây là regression baseline, không phải bằng chứng rằng 30/30 DoD đã pass.
- Các bước có khoảng trống error-case rõ ràng: **1, 2, 14, 15**.
- Các màn hình chưa có acceptance đúng thao tác DoD: **17, 18, 24, 28**; Bước 16 còn thiếu UI error path.
- Live provider còn thiếu: **22/ComfyUI image** và **26/Wan ComfyUI**.
- Acceptance external app cho Bước 30 đã PASS kỹ thuật trong Resolve thật với package/proxy 24 FPS; vẫn không được check chính thức trước các dependency upstream.

## Audit Git/PR

Repository tại thời điểm audit chỉ có branch `main`, không có Git remote và không có bằng chứng PR/CI cloud.

| Commit | Các bước bị gộp |
|---|---|
| `a5a1554` | 1–5 |
| `dea2532` | 6–7 |
| `67febce` | 8–10 |
| `56a6323` | 11–14 |
| `6a83dc0` | 15–18 |
| `dd0c9cb` | 19–21 |
| `43d876d` (+ fix commits) | 22–24 |
| `8586eaa` | 25–28 |
| `8ea0a86` | 29–30 |

Kết luận: quy tắc **1 bước = 1 branch = 1 PR = 1 merge** đã không được tuân thủ trong lịch sử. Không được tuyên bố ngược lại hoặc rewrite history để che sai lệch. Từ lần revalidation tiếp theo, mỗi bước phải dùng branch riêng; PR/CI chỉ có thể thực hiện sau khi cấu hình remote.

## Weekly demo và blocker alert

- Không có demo log/artifact xác nhận demo chỉ diễn ra ở cuối từng phần; trạng thái hiện tại là **không đủ bằng chứng**, không đánh pass.
- Tất cả commit hiện có được tạo cùng ngày 2026-08-24; chưa có bằng chứng blocker nào kéo dài quá một ngày công.
- Blocker đang theo dõi, tuổi blocker bắt đầu từ 2026-08-24: CI/remote cho Bước 1; ComfyUI image cho 22; Wan live cho 26. Lỗi tương thích FPS DaVinci của Bước 30 đã đóng kỹ thuật ngày 2026-08-24. Nếu blocker còn mở sau một ngày công phải alert người dùng.

## Thứ tự phục hồi hợp lệ

1. Hoàn tất Bước 1: cấu hình remote, chạy CI thật, bổ sung error-case test; chỉ check khi CI xanh.
2. Revalidate Bước 2 theo branch riêng và bổ sung error case; sau đó tuần tự 3–13.
3. Bổ sung test gaps 14–18; không dùng service test để thay thế UI DoD.
4. Revalidate 19–21.
5. Chạy live ComfyUI image để đóng 22 rồi mới revalidate 23–24.
6. Revalidate 25; chạy Wan live để đóng 26 rồi mới 27–28.
7. Revalidate 29 sau 28.
8. Bằng chứng kỹ thuật/live 24 FPS cho Bước 30 đã hoàn tất; chỉ revalidate/check chính thức sau khi 28 và 29 pass theo dependency.
