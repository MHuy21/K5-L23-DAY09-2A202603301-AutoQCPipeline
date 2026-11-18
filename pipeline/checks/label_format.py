"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401

CHECK = "label_format"


def _check_file(ds, stem, p):
    """Kiểm mọi dòng của một file nhãn. `p` = cfg["label_format"]."""
    issues = []
    n_classes = len(ds.classes)
    size = ds.image_size(stem)              # None nếu ảnh hỏng / không có ảnh -> bỏ qua BOX_TINY
    seen = []                               # (số dòng, lớp, box) của các dòng hợp lệ phía trước, để tìm DUP_BOX

    for ln, text in ds.read_label_lines(stem) or []:      # số dòng gốc, đã bỏ dòng trống
        # 1. định dạng
        try:
            c, x, y, w, h = parse_yolo_line(text)
        except ValueError as e:
            issues.append(Issue(CHECK, ERROR, "BAD_FORMAT", stem, f"dòng không đúng 5 cột số: {e}", ln, {"text": text.strip()}))
            continue
        # 2. id lớp
        if not 0 <= c < n_classes:
            issues.append(Issue(CHECK, ERROR, "BAD_CLASS_ID", stem, f"id lớp {c} ngoài 0..{n_classes - 1}", ln, {"class_id": c}))
            continue
        # 3. box rỗng
        if w <= 0 or h <= 0:
            issues.append(Issue(CHECK, ERROR, "BOX_ZERO", stem, f"box rộng/cao <= 0 (w={w}, h={h})", ln))
            continue

        box = (x, y, w, h)
        # 4. tràn ảnh: mức tràn lớn nhất trong 4 mép
        overflow = max(0.0 - (x - w / 2), (x + w / 2) - 1.0, 0.0 - (y - h / 2), (y + h / 2) - 1.0)
        if overflow > p["overflow_tol"]:
            issues.append(Issue(CHECK, ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ra ngoài ảnh {overflow:.4f}", ln,
                                {"overflow": round(overflow, 6)}))
        # 5. box lặp: cùng lớp với một dòng trước đó, IoU cao -> báo ở dòng sau
        for prev_ln, prev_c, prev_box in seen:
            if prev_c == c:
                iou = iou_xywh(prev_box, box)
                if iou > p["dup_box_iou"]:
                    issues.append(Issue(CHECK, ERROR, "DUP_BOX", stem, f"trùng box dòng {prev_ln} (IoU {iou:.2f})", ln,
                                        {"dup_of": prev_ln, "iou": round(iou, 4)}))
                    break
        seen.append((ln, c, box))
        # 6. box quá nhỏ (px) — cảnh báo
        if size is not None:
            W, H = size
            short_px = min(w * W, h * H)
            if short_px < p["min_box_px"]:
                issues.append(Issue(CHECK, WARN, "BOX_TINY", stem, f"cạnh ngắn {short_px:.1f}px < {p['min_box_px']}px", ln,
                                    {"short_px": round(short_px, 2)}))
        # 7. box quá lớn — cảnh báo
        if w * h > p["max_box_frac"]:
            issues.append(Issue(CHECK, WARN, "BOX_HUGE", stem, f"box chiếm {w * h:.2%} ảnh", ln, {"area_frac": round(w * h, 4)}))
    return issues


def run(ds, cfg):
    p = cfg["label_format"]
    issues = []
    for lp in ds.label_files():
        issues.extend(_check_file(ds, lp.stem, p))
    return issues
