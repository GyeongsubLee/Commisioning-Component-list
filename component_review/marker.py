"""ISO 사본에 배관 색칠과 Tag 형광펜을 넣어 저장한다."""
import pymupdf

from .config import Config


def save_marked(src, dst, selections: dict, rgb, cfg: Config):
    """selections: {page_index: Selection}. 원본은 건드리지 않는다."""
    color = tuple(c / 255 for c in rgb)
    doc = pymupdf.open(src)
    for page in doc:
        sel = selections.get(page.number)
        if sel is None:
            continue
        page.remove_rotation()
        if sel.strokes:
            shape = page.new_shape()
            for a, b in sel.strokes:
                shape.draw_line(pymupdf.Point(a), pymupdf.Point(b))
            shape.finish(color=color, width=cfg.mark_width, stroke_opacity=cfg.mark_opacity,
                         lineCap=1, lineJoin=1, closePath=False)
            shape.commit(overlay=True)
        for t in sel.in_tags:
            annot = page.add_highlight_annot(pymupdf.Rect(t.rect))
            annot.set_colors(stroke=cfg.tag_highlight)
            annot.update()
    doc.save(dst, garbage=3, deflate=True)
    doc.close()
