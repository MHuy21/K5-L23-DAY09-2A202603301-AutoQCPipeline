"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401

CHECK = "second_opinion"


def _labels_with_lines(ds, stem):
    """[(số dòng gốc, lớp, (cx, cy, w, h))] của các dòng nhãn hợp lệ; dòng hỏng bị bỏ qua (label_format đã báo)."""
    out = []
    n_classes = len(ds.classes)
    for ln, text in ds.read_label_lines(stem) or []:
        try:
            c, x, y, w, h = parse_yolo_line(text)
        except ValueError:
            continue
        if 0 <= c < n_classes:
            out.append((ln, c, (x, y, w, h)))
    return out


def _check_image(ds, stem, preds, p, size):
    issues = []
    W, H = size
    labels = _labels_with_lines(ds, stem)
    names = ds.classes

    def cname(c):
        return names[c] if 0 <= c < len(names) else str(c)

    # --- mỗi dự đoán đáng tin -> tối đa 1 issue (MISSING / LOOSE_BOX / WRONG_CLASS)
    for r in preds:
        rc, rconf, rbox = int(r[0]), float(r[1]), tuple(float(v) for v in r[2:6])
        if rconf < p["conf"] or rbox[2] * W * rbox[3] * H < p["min_area_px"]:
            continue
        cands = [(iou_xywh(rbox, lb), lc) for _, lc, lb in labels]
        cands = [(iou, lc) for iou, lc in cands if iou >= p["iou_missing"]]
        if not cands:
            issues.append(Issue(CHECK, WARN, "POSSIBLE_MISSING", stem,
                                f"model thấy {cname(rc)} (conf {rconf:.2f}) nhưng nhãn không có box nào",
                                extra={"conf": round(rconf, 4), "pred_class": rc, "box": [round(v, 4) for v in rbox]}))
            continue
        same = [iou for iou, lc in cands if lc == rc]
        if same:
            best = max(same)
            if best < p["iou_loose"]:
                issues.append(Issue(CHECK, WARN, "POSSIBLE_LOOSE_BOX", stem,
                                    f"box {cname(rc)} lệch/lỏng so với model (IoU {best:.2f})",
                                    extra={"conf": round(rconf, 4), "iou": round(best, 4), "pred_class": rc}))
            continue                                        # nhãn đúng lớp đã phủ vật này
        best_iou, best_c = max(cands)                       # chỉ còn cands khác lớp
        if best_iou >= p["iou_match"]:
            issues.append(Issue(CHECK, WARN, "POSSIBLE_WRONG_CLASS", stem,
                                f"nhãn {cname(best_c)} nhưng model nói {cname(rc)} (conf {rconf:.2f}, IoU {best_iou:.2f})",
                                extra={"conf": round(rconf, 4), "iou": round(best_iou, 4), "pred_class": rc, "label_class": best_c}))
        # IoU khác lớp trong [iou_missing, iou_match): mơ hồ -> không cờ

    # --- mỗi box nhãn không khớp dự đoán nào (conf >= fp_conf, KHÔNG lọc diện tích) -> FALSE_POS
    fp_preds = [tuple(float(v) for v in r[2:6]) for r in preds if float(r[1]) >= p["fp_conf"]]
    for ln, lc, lb in labels:
        best = max((iou_xywh(lb, rb) for rb in fp_preds), default=0.0)
        if best < p["iou_missing"]:
            issues.append(Issue(CHECK, WARN, "POSSIBLE_FALSE_POS", stem,
                                f"box {cname(lc)} không khớp vật nào model thấy (IoU tốt nhất {best:.2f})", ln,
                                {"iou": round(best, 4), "label_class": lc}))
    return issues


def run(ds, cfg, preds=None):
    p = cfg["second_opinion"]
    if preds is None:
        preds = get_preds(ds, cfg, "checker")
    issues = []
    for img in ds.image_files():
        stem = img.stem
        if stem not in preds or ds.read_label_lines(stem) is None:     # không có dự đoán hoặc không có file nhãn
            continue
        size = ds.image_size(stem)
        if size is None:                                               # ảnh hỏng: check images đã báo
            continue
        issues.extend(_check_image(ds, stem, preds[stem] or [], p, size))
    return issues
