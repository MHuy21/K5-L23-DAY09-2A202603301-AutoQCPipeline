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

Cấu hình (giống nhau cho cả hai biến thể): `yolo26n.pt` (khởi tạo COCO), 20 epoch, `imgsz` 640, `batch` 16, seed 0 và 1, Colab Tesla T4; val = `gold_val` (40 ảnh), test = `data/test` (100 ảnh, 387 box). Chỉ khác dữ liệu train: `raw` 224 ảnh nhãn gốc, `clean` 202 ảnh của `clean_v1` (`manifest_sha1` khớp export hiện tại).

| biến thể | #ảnh train | số seed | map50 (TB ± độ lệch) | map50_95 (TB ± độ lệch) | precision (TB ± độ lệch) | recall (TB ± độ lệch) |
|---|---|---|---|---|---|---|
| raw | 224 | 2 | 0.726 ± 0.000 | 0.512 ± 0.004 | 0.764 ± 0.061 | 0.649 ± 0.028 |
| clean | 202 | 2 | 0.701 ± 0.025 | 0.487 ± 0.008 | 0.759 ± 0.003 | 0.625 ± 0.019 |

Chênh mAP50 (clean − raw) = **−0,025**, bằng đúng độ lệch giữa 2 seed của `clean` (±0,025; hai seed cho 0,718 và 0,683). Độ lệch ±0,000 của `raw` chỉ là do 2 seed tình cờ trùng điểm (0,7256 / 0,7259), không có nghĩa `raw` ổn định hơn. Precision gần như bằng nhau (0,764 và 0,759); recall chênh 0,024, cũng nằm trong độ lệch giữa seed của `raw` (±0,028).
**Kết luận: chưa kết luận được** `clean` tốt hơn hay kém hơn `raw`. Khác biệt nằm trong nhiễu của 2 seed × 100 ảnh test, nên tôi **không** nói "dữ liệu sạch giúp model tốt hơn".

**Giả thuyết giải thích và cách kiểm:**
1. **Model gần như không học thêm từ dữ liệu train.** Ở cả 4 lần chạy, `best.pt` (chọn theo val) rơi vào **epoch 1**: val mAP50 epoch 1 là 0,801 / 0,800 (`raw`) và 0,791 / 0,739 (`clean`), sau đó tụt xuống 0,5–0,7 rồi chỉ hồi lại khoảng 0,71–0,73 ở epoch 20. Model khởi tạo từ COCO đã biết sẵn car/person/truck/bus, nên điểm test chủ yếu phản ánh pretrained + 1 epoch, còn chất lượng nhãn train ít ảnh hưởng. *Kiểm:* đo test của chính `yolo26n.pt` khi chưa fine-tune; train lại với lr nhỏ hơn hoặc freeze backbone, rồi so lại raw và clean.
2. **`raw` có lợi thế không công bằng: rò rỉ test.** Pipeline đã phát hiện 5 ảnh `LEAK_TEST` trong raw (`img_0049`, `img_0101`, `img_0167`, `img_0174`, `img_0221` trùng ảnh test), và chúng vẫn nằm trong 224 ảnh train của `raw` nên điểm của `raw` có thể bị thổi phồng. Ngược lại, Ultralytics tự **bỏ 11 ảnh** có nhãn/ảnh hỏng của `raw` (log: "216 images, 19 backgrounds, 11 corrupt", "Using 213 train"), tức tự làm sạch một phần lỗi cú pháp mà pipeline sửa, nên khoảng cách raw–clean bị thu hẹp. *Kiểm:* train `raw` sau khi bỏ 5 ảnh `LEAK_TEST` rồi so lại; đọc danh sách 11 ảnh bị bỏ trong log.
3. **Lớp `truck` ít mẫu nên rất nhiễu.** AP50 của truck ở `clean` dao động 0,590 / 0,486 giữa 2 seed (raw: 0,657 / 0,640). Train `clean` chỉ có 41 box truck và `raw` có 32. Số box car giảm từ 122 (`raw`) xuống 101 (`clean`), có thể do vừa loại ảnh trùng vừa do người duyệt đổi nhãn car ↔ truck (18 cờ `POSSIBLE_WRONG_CLASS`); ranh giới hai lớp này vẫn mơ hồ. *Kiểm:* xem AP theo lớp với nhiều seed hơn; mở các ảnh truck bị đổi nhãn trong `06_review_log.csv`.
4. **`clean` chưa thật sự sạch.** Kết luận pipeline là Hold: còn 38/202 ảnh có cảnh báo chưa ai duyệt (`07_error_list_v3`: 21 `FALSE_POS`, 20 `LOOSE_BOX`, 13 `MISSING`…).

**Việc tiếp theo:** chạy ≥ 3–5 seed và báo khoảng tin cậy; thêm biến thể `oracle` (nhãn người) làm chặn trên; loại 5 ảnh `LEAK_TEST` khỏi `raw` để so công bằng; thử 40 epoch, hoặc lr nhỏ hơn để best không rơi vào epoch 1.

## 6. Quyết định và ghi chú AI

**(a) Quyết định: Hold.** Bản `clean_v1` là nháp, chưa phát hành. Để thành **Release** cần đưa tỉ lệ ảnh còn cảnh báo chưa duyệt xuống < 10%, tức người xem thêm ít nhất 18 trong 45 ảnh còn lại của hàng đợi (38 → ≤ 20/202), ưu tiên các ảnh còn `POSSIBLE_MISSING`/`WRONG_CLASS`; hoặc tăng ngân sách duyệt trong guideline. **Không** làm bằng cách nâng `second_opinion.conf` lên 0,8 cho "đạt", vì như vậy mất 25% recall `MISSING`.

**(b) Dùng AI để viết 4 module:**

- _Prompt chính:_ "Đọc docstring + test của `label_format`/`gate`/`autofix`/`second_opinion`, viết đúng hợp đồng (đầu vào, đầu ra, mã lỗi, severity); ngưỡng đọc từ `cfg`, không đọc đáp án, không ghi vào `data/raw`; kiểm bằng pytest."
- _Cách kiểm:_ chạy `pytest` từng file rồi toàn bộ (79 passed); thêm 3 ca tự viết (dòng dính 2 lỗi + dòng trống → chỉ 1 `drop_line`, idempotent; dòng rác/trống giữ số dòng gốc cho `FALSE_POS`; nhiều dự đoán trên 1 ảnh); đối chiếu với lỗi chèn trong calib và 3 lỗi tự nhìn thấy (`img_0001` `DUP_BOX` + thiếu người lính, `img_0071` gán nhầm `car`): cả 3 đều bị bắt và xử lý.
- _Một lần AI sai:_ bản đầu của `autofix._rename_classes` có dòng `d["nc"] = ... if "nc" in d else d.get("nc", ...)` luôn thêm khoá `nc` vào `data.yaml` kể cả khi file gốc không có. Tôi phát hiện khi đọc lại và sửa thành chỉ cập nhật `nc` khi khoá đã tồn tại. Ngoài ra, script thử ngưỡng viết bằng PowerShell 5.1 làm hỏng chuỗi tiếng Việt, phải viết lại bằng Python.
