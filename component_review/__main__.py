"""실행: python -m component_review  (인자가 없으면 폴더 선택 창이 뜬다)"""
import argparse
import sys

from .pipeline import run


def _ask_gui(args):
    import tkinter as tk
    from tkinter import filedialog, simpledialog, messagebox
    root = tk.Tk()
    root.withdraw()
    types = [("Excel/CSV", "*.xlsx *.xlsm *.xls *.csv"), ("All", "*.*")]
    if not args.iso_dir:
        args.iso_dir = filedialog.askdirectory(title="1/4  ISO PDF 폴더 선택")
    if args.iso_dir and not args.pid_root:
        args.pid_root = filedialog.askdirectory(title="2/4  Marked up PID 폴더 선택 (Subsystem 폴더들의 상위 폴더)")
    if args.pid_root and not args.system_list:
        args.system_list = filedialog.askopenfilename(title="3/4  Subsystem-ISO List 선택", filetypes=types)
    if args.system_list and not args.component_list:
        args.component_list = filedialog.askopenfilename(title="4/4  기존 Component List 선택", filetypes=types)
    if not all([args.iso_dir, args.pid_root, args.system_list, args.component_list]):
        messagebox.showinfo("취소", "선택이 취소되었습니다.")
        sys.exit(1)
    if args.subsystem is None:
        s = simpledialog.askstring("Subsystem", "처리할 Subsystem Number (쉼표로 여러 개, 비우면 PID 폴더가 있는 전체):")
        args.subsystem = s or ""
    return messagebox


def main(argv=None):
    ap = argparse.ArgumentParser(prog="component_review", description="Marked up PID 기준 Component List 검토")
    ap.add_argument("--iso-dir", help="ISO PDF 폴더")
    ap.add_argument("--pid-root", help="Marked up PID 폴더 (안에 Subsystem Number 이름의 폴더)")
    ap.add_argument("--system-list", help="Subsystem-ISO List (xlsx/csv)")
    ap.add_argument("--component-list", help="기존 Component List (xlsx/csv)")
    ap.add_argument("--subsystem", help="처리할 Subsystem Number (쉼표 구분). 생략하면 전체")
    ap.add_argument("--report-dir", help="리포트 저장 폴더 (기본: PID 폴더)")
    args = ap.parse_args(argv)
    box = None
    if not all([args.iso_dir, args.pid_root, args.system_list, args.component_list]):
        box = _ask_gui(args)
    subs = [s for s in (args.subsystem or "").split(",") if s.strip()] or None
    try:
        res = run(args.iso_dir, args.pid_root, args.system_list, args.component_list, subs, args.report_dir)
    except Exception as e:
        if box:
            box.showerror("오류", str(e))
        raise
    if box:
        box.showinfo("완료", f"리포트 저장: {res['report']}")


if __name__ == "__main__":
    main()
