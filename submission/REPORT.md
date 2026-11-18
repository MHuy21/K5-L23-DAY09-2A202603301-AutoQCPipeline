# Báo cáo Day 09 — Dương Mạnh Huy, 2A202603301

## 1. Kết luận trước

Pipeline kết luận **Hold** (mã thoát 10). Vào **224** ảnh raw → cửa vào loại **22** → còn **202** ảnh được QC, sửa, duyệt và xuất bản **nháp** `submission/export/clean_v1/` (202 ảnh, manifest ghi `decision = Hold`, chưa phát hành).
Lý do: sau khi máy sửa và người duyệt 80/80 ảnh ngân sách, **không còn lỗi bắt buộc** (`n_errors = 0`), nhưng **38/202 ảnh (18,8%)** vẫn còn cảnh báo chưa có người xem, vượt ngưỡng 10% của dự án (`08_summary.json`).

## 2. Lỗi và phân việc

Số liệu từ `02_error_list_v1` (cửa vào trên 224 ảnh, QC vòng 1 trên 202 ảnh).

| Mã lỗi                                              |          Số ảnh/dòng | Ai sửa (máy/người)        | Vì sao                                                               |
| --------------------------------------------------- | -------------------: | ------------------------- | -------------------------------------------------------------------- |
| `DUP_IMAGE_EXACT`                                   |          8 ảnh / 224 | máy (loại ở cửa vào)      | trùng md5, chắc chắn                                                 |
| `DUP_IMAGE_NEAR`                                    |          4 ảnh / 224 | máy (loại)                | phash ≤ 12, đã mở xem cả 4 cặp đều trùng thật                        |
| `LEAK_TEST`                                         |          5 ảnh / 224 | máy (loại)                | trùng ảnh tập test → rò rỉ, bắt buộc loại                            |
| `BAD_SIZE` / `CORRUPT_IMAGE`                        |            3 / 2 ảnh | máy (loại)                | ảnh < 250 px hoặc cắt cụt (`load()` lỗi)                             |
| `BAD_CLASS_ID`                                      |       6 dòng / 6 ảnh | máy (`drop_line`)         | id 93, 4, −1 không phải lớp nào: không đoán được lớp đúng → xoá dòng |
| `BAD_FORMAT`                                        |       3 dòng / 3 ảnh | máy (`drop_line`)         | thiếu cột / `nan`                                                    |
| `BOX_ZERO`                                          |       4 dòng / 4 ảnh | máy (`drop_line`)         | box rộng/cao = 0                                                     |
| `DUP_BOX`                                           |       7 dòng / 7 ảnh | máy (`drop_line`)         | dòng sau lặp dòng trước (IoU > 0,9), vd. `img_0001` dòng 3           |
| `BOX_OUT_OF_IMAGE`                                  |       8 dòng / 8 ảnh | máy (`clip_box`)          | cắt về [0,1], giữ lớp — sửa cú pháp an toàn                          |
| `BAD_CLASS_NAME`                                    | 2 dòng / `data.yaml` | máy (`rename_classes`)    | tên lớp viết hoa sai → ghi lại theo `cfg["classes"]`                 |
| `MISSING_LABEL_FILE`                                |          6 ảnh / 202 | **người** (`needs_label`) | máy không được bịa nhãn, không tạo file rỗng                         |
| `POSSIBLE_MISSING`                                  |     53 dòng / 52 ảnh | **người**                 | ngữ nghĩa: model lớn thấy vật mà nhãn không có                       |
| `POSSIBLE_LOOSE_BOX`                                |     28 dòng / 24 ảnh | **người**                 | box lệch/lỏng — cần mắt người                                        |
| `POSSIBLE_FALSE_POS`                                |     29 dòng / 27 ảnh | **người**                 | box nhãn không khớp vật nào model thấy                               |
| `POSSIBLE_WRONG_CLASS`                              |     18 dòng / 18 ảnh | **người**                 | nhầm lớp hợp lệ (vd. `img_0071`: trẻ em gán `car`)                   |
| `EMPTY_LABEL`, `BOX_TINY`, `BOX_HUGE`, `CLASS_RARE` |   12 / 4 / 3 / 1 ảnh | người                     | cảnh báo: ảnh nền hay thiếu nhãn, box quá nhỏ/lớn                    |

Máy tạo **35 thay đổi** (`03_fixes.csv`: 20 `drop_line`, 8 `clip_box`, 6 `needs_label`, 1 `rename_classes`), mỗi thay đổi có trước → sau. Sau sửa (`04_error_list_v2`) chỉ còn 6 lỗi bắt buộc, đều là `MISSING_LABEL_FILE`.

**Hàng đợi** (`05_review_queue.csv`, 125 ảnh): điểm = Σ trọng số mã × (1 + conf của model). Đầu hàng là `img_0020` (11,5: vừa bị máy xoá dòng + `POSSIBLE_MISSING` + `POSSIBLE_WRONG_CLASS` với conf cao), tiếp theo là 6 ảnh `NEEDS_LABEL` (trọng số 10: không có người thì không thể xuất). Với ngân sách **80 ảnh**, người xem đúng 80 ảnh đầu hàng, phủ **94/123 cờ ngữ nghĩa (trên 74/103 ảnh)**: 51 `MISSING`, 18 `WRONG_CLASS`, 13 `FALSE_POS`, 12 `LOOSE_BOX`. 45 ảnh cuối hàng không được xem → chính là nguồn của Hold.

## 3. Calibration (2 ngưỡng)

| Tham số                 | Khởi đầu | Đã chọn | Precision / Recall (trước → sau)                                                                                    | Lý do (đánh đổi)                                                                                                                                                                                                                       |
| ----------------------- | -------- | ------- | ------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `duplicates.phash_dist` | 2        | **12**  | `DUP_IMAGE_NEAR`: 1,00 / 0,50 → 1,00 / 0,67 (`EXACT` giữ 1,00 / 1,00)                                               | Từ 4 đến 14 calib cho cùng P/R; tôi lấy giá trị lớn nhất mà **trên raw không loại oan ảnh nào** (12 bắt thêm cặp `img_0186`/`img_0061` dist 10 là trùng thật). 16 có recall calib cao nhất (0,83) nhưng loại oan trên raw (xem dưới).  |
| `second_opinion.conf`   | 0,25     | **0,6** | `WRONG_CLASS` 0,56 / 0,83 → 0,62 / 0,83; `MISSING` 0,50 / 1,00 → 0,57 / 1,00; `LOOSE_BOX` 0,29 / 0,40 → 0,20 / 0,20 | Ngưỡng cao nhất mà recall `MISSING` vẫn 1,00 (từ 0,7 tụt còn 0,88, 0,8 còn 0,75): bớt cờ sai cho người, không mất vật bị thiếu. Đánh đổi: recall `LOOSE_BOX` giảm. Không chọn 0,8 dù nó cho Release: chọn theo sweep, không theo gate. |

**Calibration đánh lừa ở đâu:** trên calib (39 ảnh) `phash_dist = 16` là tốt nhất (`DUP_IMAGE_NEAR` P = 1,00, R = 0,83, F1 = 0,91), "precision = 1" gợi ý không có rủi ro. Nhưng chạy thử trên raw, 16 loại **31** ảnh thay vì 22. Mở xem: `img_0011` (tennis) bị coi là trùng `img_0008` (trượt tuyết), `img_0177` (lướt sóng) bị coi là trùng `img_0113` (người ngồi bàn), cả hai cách nhau đúng dist 16. Calib quá nhỏ nên không có cặp ảnh khác nhau nào có phash gần nhau đến vậy; precision 1,00 chỉ là do thiếu mẫu âm. Ngoài ra, ở 20 recall của `DUP_IMAGE_EXACT` lại **giảm** (1,00 → 0,33) do ghép cặp sai, nên đường cong không đơn điệu như ta tưởng.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được

**(a) Gate chặn thật.** `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` → kết luận **REWORK**, mã thoát **20**, log "KHÔNG xuất: còn lỗi bắt buộc (Rework)", thư mục `work/exp_nb/clean_v1` **không tồn tại**. Lý do: 6 lỗi `MISSING_LABEL_FILE` (`img_0031`, `img_0053`, `img_0126`, `img_0135`, `img_0170`, `img_0219`) không có người gán. Autofix chỉ ghi `needs_label`, không tạo file rỗng để "lách" cổng.

**(b) Điểm mù (có bằng chứng):**

1. **Ảnh trùng bị biến đổi mạnh:** cặp `img_0084`/`img_0074` (cùng cảnh, bị cắt) có dist 16 > 12 nên lọt qua; trên calib cũng chỉ bắt được 4/6 `DUP_IMAGE_NEAR`. Nâng ngưỡng thì loại oan ảnh khác (§3), nên đây là đánh đổi chứ không sửa được bằng ngưỡng.
2. **Box lỏng nhẹ:** `POSSIBLE_LOOSE_BOX` ở conf 0,6 chỉ có P / R = 0,20 / 0,20 trên calib, tức 4/5 box phình to cố ý không bị bắt. Sau duyệt vẫn còn 20 cờ `LOOSE_BOX` chưa ai xem (`07_error_list_v3`).
3. **Model lớn cũng có thể sai:** `POSSIBLE_FALSE_POS` có precision 0,31 (11 cờ sai / 16 cờ trên calib). Nếu model và người gán cùng nhầm một lớp (vd. xe tải nhỏ ↔ car), sẽ không có cờ nào, vì `second_opinion` chỉ thấy chỗ hai bên **không đồng ý**.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)

**Chưa chạy.**

## 6. Quyết định và ghi chú AI

**(a) Quyết định: Hold.** Bản `clean_v1` là nháp, chưa phát hành. Để thành **Release** cần đưa tỉ lệ ảnh còn cảnh báo chưa duyệt xuống < 10%, tức người xem thêm ít nhất 18 trong 45 ảnh còn lại của hàng đợi (38 → ≤ 20/202), ưu tiên các ảnh còn `POSSIBLE_MISSING`/`WRONG_CLASS`; hoặc tăng ngân sách duyệt trong guideline. **Không** làm bằng cách nâng `second_opinion.conf` lên 0,8 cho "đạt", vì như vậy mất 25% recall `MISSING`.

**(b) Dùng AI để viết 4 module:**

- _Prompt chính:_ "Đọc docstring + test của `label_format`/`gate`/`autofix`/`second_opinion`, viết đúng hợp đồng (đầu vào, đầu ra, mã lỗi, severity); ngưỡng đọc từ `cfg`, không đọc đáp án, không ghi vào `data/raw`; kiểm bằng pytest."
- _Cách kiểm:_ chạy `pytest` từng file rồi toàn bộ (79 passed); thêm 3 ca tự viết (dòng dính 2 lỗi + dòng trống → chỉ 1 `drop_line`, idempotent; dòng rác/trống giữ số dòng gốc cho `FALSE_POS`; nhiều dự đoán trên 1 ảnh); đối chiếu với lỗi chèn trong calib và 3 lỗi tự nhìn thấy (`img_0001` `DUP_BOX` + thiếu người lính, `img_0071` gán nhầm `car`): cả 3 đều bị bắt và xử lý.
- _Một lần AI sai:_ bản đầu của `autofix._rename_classes` có dòng `d["nc"] = ... if "nc" in d else d.get("nc", ...)` luôn thêm khoá `nc` vào `data.yaml` kể cả khi file gốc không có. Tôi phát hiện khi đọc lại và sửa thành chỉ cập nhật `nc` khi khoá đã tồn tại. Ngoài ra, script thử ngưỡng viết bằng PowerShell 5.1 làm hỏng chuỗi tiếng Việt, phải viết lại bằng Python.
