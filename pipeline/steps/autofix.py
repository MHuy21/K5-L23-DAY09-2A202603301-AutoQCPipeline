"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401

DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
CLIP_CODES = {"BOX_OUT_OF_IMAGE"}
REMOVE_CODES = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}          # + mọi mã bắt đầu bằng DUP_IMAGE_


def _is_remove(code):
    return code in REMOVE_CODES or code.startswith("DUP_IMAGE_")


def _fix(image, line, action, before, after):
    return dict(image=image, line=line, action=action, before=before, after=after)


def _remove_image(ds, stem):
    """Xoá ảnh + nhãn của `stem` khỏi ds. Trả về True nếu có xoá gì đó."""
    done = False
    img = ds.image_path(stem)
    if img is not None and img.exists():
        img.unlink()
        done = True
    lab = ds.label_path(stem)
    if lab.exists():
        lab.unlink()
        done = True
    return done


def _rename_classes(ds, cfg):
    """Ghi lại names trong data.yaml theo cfg["classes"]. Trả về fix, hoặc None nếu đã đúng."""
    want = list(cfg["classes"])
    old = ds.yaml_names()
    if [old.get(i) for i in range(len(old))] == want and len(old) == len(want):
        return None
    d = {}
    if ds.yaml_path.exists():
        d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
    d["names"] = {i: n for i, n in enumerate(want)}
    if "nc" in d:
        d["nc"] = len(want)
    ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return _fix("data.yaml", None, "rename_classes", str([old[k] for k in sorted(old)]), str(want))


def _clip(c, x, y, w, h):
    """Cắt box về [0,1]. Trả về (c, x, y, w, h) mới, hoặc None nếu không còn diện tích."""
    x1, x2 = max(0.0, x - w / 2), min(1.0, x + w / 2)
    y1, y2 = max(0.0, y - h / 2), min(1.0, y + h / 2)
    if x2 <= x1 or y2 <= y1:
        return None
    return c, (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1


def _fix_label_file(ds, stem, line_codes):
    """Sửa một file nhãn: `line_codes` = {số dòng gốc: {mã lỗi}}. Đọc 1 lần, ghi 1 lần."""
    path = ds.label_path(stem)
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8", errors="replace").splitlines()     # giữ cả dòng trống -> số dòng gốc
    fixes, out = [], []
    for n, text in enumerate(raw, 1):
        codes = line_codes.get(n)
        if not codes:
            out.append(text)
            continue
        if codes & DROP_CODES:                              # xoá dòng thắng mọi cách sửa khác
            fixes.append(_fix(stem, n, "drop_line", text.strip(), "(xoá dòng)"))
            continue
        if codes & CLIP_CODES:
            try:
                b = parse_yolo_line(text)
            except ValueError:                              # không parse được thì không thể cắt: xoá
                fixes.append(_fix(stem, n, "drop_line", text.strip(), "(xoá dòng)"))
                continue
            clipped = _clip(*b)
            if clipped is None:                             # nằm hẳn ngoài ảnh
                fixes.append(_fix(stem, n, "drop_line", text.strip(), "(xoá dòng: box nằm ngoài ảnh)"))
                continue
            c, x, y, w, h = clipped
            new = f"{c} {x:.6f} {y:.6f} {w:.6f} {h:.6f}"
            fixes.append(_fix(stem, n, "clip_box", text.strip(), new))
            out.append(new)
            continue
        out.append(text)                                    # mã lỗi dòng khác: không tự sửa
    if fixes:
        path.write_text("".join(l + "\n" for l in out), encoding="utf-8")
    return fixes


def fix(ds, issues, cfg):
    errors = [i for i in issues if i.severity == ERROR]
    fixes = []

    # 1. xoá ảnh (làm trước để bỏ qua các lỗi dòng của ảnh đã bị xoá)
    removed = set()
    for i in errors:
        if _is_remove(i.code) and i.image not in removed:
            removed.add(i.image)
            if _remove_image(ds, i.image):
                fixes.append(_fix(i.image, None, "remove_image", i.code, "(xoá ảnh + nhãn)"))

    # 2. ảnh thiếu nhãn: không bịa nhãn, chuyển người gán (mỗi ảnh 1 dòng)
    seen_missing = set()
    for i in errors:
        if i.code == "MISSING_LABEL_FILE" and i.image not in removed and i.image not in seen_missing:
            seen_missing.add(i.image)
            fixes.append(_fix(i.image, None, "needs_label", "(không có file)", "chuyển người gán"))

    # 3. tên lớp trong data.yaml (một lần dù có nhiều issue)
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        f = _rename_classes(ds, cfg)
        if f:
            fixes.append(f)

    # 4. lỗi theo dòng: gom theo file, giữ số dòng gốc
    per_file = defaultdict(lambda: defaultdict(set))
    for i in errors:
        if i.line is not None and i.code in DROP_CODES | CLIP_CODES and i.image not in removed:
            per_file[i.image][int(i.line)].add(i.code)
    for stem in sorted(per_file):
        fixes.extend(_fix_label_file(ds, stem, per_file[stem]))

    return fixes
