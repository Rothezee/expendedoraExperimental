"""Renderizado de Markdown en un widget Text de Tkinter (subset para manual de usuario)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

import tkinter as tk

DEFAULT_MANUAL_PATH = Path(__file__).resolve().parent / "docs" / "manual_usuario.md"

_INLINE_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_IMAGE_LINE_RE = re.compile(r"^!\[(.*?)\]\((.+?)\)\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")

MANUAL_IMAGE_MAX_WIDTH = 720


def manual_markdown_path() -> Path:
    return DEFAULT_MANUAL_PATH


def load_manual_markdown(path: Optional[Path] = None) -> str:
    md_path = path or DEFAULT_MANUAL_PATH
    if not md_path.is_file():
        return (
            "# Manual no encontrado\n\n"
            f"No se encontró el archivo:\n\n`{md_path}`"
        )
    return md_path.read_text(encoding="utf-8")


def _configure_tags(text: tk.Text, colors: dict) -> None:
    text.tag_configure("h1", font=("Segoe UI", 20, "bold"), spacing3=10, foreground=colors.get("text", "#34495E"))
    text.tag_configure("h2", font=("Segoe UI", 15, "bold"), spacing3=8, foreground=colors.get("primary", "#3498DB"))
    text.tag_configure("h3", font=("Segoe UI", 12, "bold"), spacing3=6, foreground=colors.get("text", "#34495E"))
    text.tag_configure("body", font=("Segoe UI", 11), lmargin1=4, lmargin2=4, spacing3=4)
    text.tag_configure("bullet", font=("Segoe UI", 11), lmargin1=18, lmargin2=32, spacing3=3)
    text.tag_configure("numbered", font=("Segoe UI", 11), lmargin1=18, lmargin2=32, spacing3=3)
    text.tag_configure("quote", font=("Segoe UI", 11, "italic"), lmargin1=16, lmargin2=16, background="#F8F9FA", foreground="#566573")
    text.tag_configure("code", font=("Consolas", 10), background="#F0F3F4", foreground="#2C3E50")
    text.tag_configure("code_block", font=("Consolas", 10), background="#F0F3F4", lmargin1=12, lmargin2=12, spacing1=4, spacing3=6)
    text.tag_configure("diagram", font=("Consolas", 9), background="#EBF5FB", foreground="#1B4F72", lmargin1=12, lmargin2=12, spacing1=4, spacing3=4)
    text.tag_configure("diagram_title", font=("Segoe UI", 9, "bold"), foreground="#1B4F72", spacing3=6)
    text.tag_configure("table", font=("Segoe UI", 10), lmargin1=8, lmargin2=8, spacing3=2)
    text.tag_configure("table_header", font=("Segoe UI", 10, "bold"), background="#ECF0F1")
    text.tag_configure("hr", spacing1=8, spacing3=8)
    text.tag_configure("bold", font=("Segoe UI", 11, "bold"))
    text.tag_configure("img_caption", font=("Segoe UI", 9), foreground="#7F8C8D", spacing3=4)
    text.tag_configure("img_missing", font=("Segoe UI", 10, "italic"), foreground="#95A5A6", spacing3=6)


def _load_manual_image(path: Path, *, max_width: int = MANUAL_IMAGE_MAX_WIDTH) -> tk.PhotoImage | None:
    if not path.is_file():
        return None
    try:
        from PIL import Image, ImageTk

        im = Image.open(path)
        if im.width > max_width:
            ratio = max_width / float(im.width)
            new_h = max(1, int(im.height * ratio))
            im = im.resize((max_width, new_h), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(im)
    except Exception:
        pass
    try:
        img = tk.PhotoImage(file=str(path))
        while img.width() > max_width:
            factor = max(2, img.width() // max_width)
            img = img.subsample(factor, factor)
        return img
    except Exception:
        return None


def _insert_image(
    text: tk.Text,
    md_base_dir: Path,
    alt: str,
    rel_path: str,
) -> None:
    full = (md_base_dir / rel_path.strip()).resolve()
    img = _load_manual_image(full)
    if img is None:
        text.insert("end", f"[Captura pendiente: {alt or rel_path}]\n\n", ("img_missing",))
        return
    if not hasattr(text, "_manual_images"):
        text._manual_images = []
    text._manual_images.append(img)
    if alt.strip():
        text.insert("end", alt.strip() + "\n", ("img_caption",))
    text.image_create("end", image=img, padx=4, pady=6)
    text.insert("end", "\n\n", ("body",))


def _insert_with_inline(text: tk.Text, line: str, base_tag: str) -> None:
    pos = 0
    segments: list[tuple[str, Optional[str]]] = []
    while pos < len(line):
        bold = _INLINE_BOLD_RE.search(line, pos)
        code = _INLINE_CODE_RE.search(line, pos)
        candidates = [(m, "bold") for m in [bold] if m] + [(m, "code") for m in [code] if m]
        if not candidates:
            segments.append((line[pos:], None))
            break
        candidates.sort(key=lambda item: item[0].start())
        match, kind = candidates[0]
        if match.start() > pos:
            segments.append((line[pos : match.start()], None))
        segments.append((match.group(1), kind))
        pos = match.end()
    for chunk, kind in segments:
        if not chunk:
            continue
        if kind:
            text.insert("end", chunk, (base_tag, kind))
        else:
            text.insert("end", chunk, (base_tag,))


def render_markdown(
    text: tk.Text,
    md_content: str,
    *,
    colors: Optional[dict] = None,
    md_base_dir: Optional[Path] = None,
) -> None:
    """Pinta Markdown (subset) en un widget Text ya creado."""
    colors = colors or {}
    base_dir = md_base_dir or DEFAULT_MANUAL_PATH.parent
    _configure_tags(text, colors)
    text.config(state="normal")
    text.delete("1.0", "end")

    lines = md_content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    in_code = False
    code_lang = ""
    code_lines: list[str] = []
    table_rows: list[str] = []
    numbered_idx = 0

    def flush_table() -> None:
        nonlocal table_rows
        if len(table_rows) < 2:
            for row in table_rows:
                _insert_with_inline(text, row, "body")
                text.insert("end", "\n", ("body",))
            table_rows = []
            return
        header_cells = [c.strip() for c in table_rows[0].strip("|").split("|")]
        for row in table_rows[2:]:
            cells = [c.strip() for c in row.strip("|").split("|")]
            if not any(cells):
                continue
            line_txt = "  |  ".join(
                f"{header_cells[i]}: {cells[i]}" if i < len(cells) else ""
                for i in range(max(len(header_cells), len(cells)))
            )
            _insert_with_inline(text, line_txt, "table")
            text.insert("end", "\n", ("table",))
        text.insert("end", "\n", ("body",))
        table_rows = []

    def flush_code_block() -> None:
        nonlocal code_lines, code_lang, in_code
        content = "\n".join(code_lines)
        if code_lang.lower() == "mermaid":
            text.insert("end", "Diagrama\n", ("diagram_title",))
            text.insert("end", content + "\n\n", ("diagram",))
        else:
            text.insert("end", content + "\n\n", ("code_block",))
        code_lines = []
        code_lang = ""
        in_code = False

    for raw in lines:
        line = raw.rstrip()

        if in_code:
            if line.strip().startswith("```"):
                flush_code_block()
            else:
                code_lines.append(line)
            continue

        if line.strip().startswith("```"):
            fence = line.strip()[3:].strip()
            in_code = True
            code_lang = fence
            code_lines = []
            continue

        if line.strip().startswith("|") and "|" in line.strip()[1:]:
            if table_rows and not line.strip().startswith("|"):
                flush_table()
            table_rows.append(line)
            if len(table_rows) >= 2 and _TABLE_SEP_RE.match(table_rows[1]):
                continue
            if len(table_rows) > 2 and not line.strip().startswith("|"):
                flush_table()
            continue
        if table_rows:
            flush_table()

        if not line.strip():
            text.insert("end", "\n", ("body",))
            numbered_idx = 0
            continue

        if line.strip() == "---":
            text.insert("end", "─" * 48 + "\n", ("hr",))
            continue

        img_match = _IMAGE_LINE_RE.match(line.strip())
        if img_match:
            _insert_image(text, base_dir, img_match.group(1), img_match.group(2))
            continue

        if line.startswith("# "):
            text.insert("end", line[2:].strip() + "\n\n", ("h1",))
            numbered_idx = 0
            continue
        if line.startswith("## "):
            text.insert("end", line[3:].strip() + "\n\n", ("h2",))
            numbered_idx = 0
            continue
        if line.startswith("### "):
            text.insert("end", line[4:].strip() + "\n\n", ("h3",))
            numbered_idx = 0
            continue

        if line.startswith("> "):
            _insert_with_inline(text, line[2:].strip(), "quote")
            text.insert("end", "\n\n", ("quote",))
            continue

        bullet_match = re.match(r"^(\s*)[-*]\s+(.*)$", line)
        if bullet_match:
            _insert_with_inline(text, "• " + bullet_match.group(2).strip(), "bullet")
            text.insert("end", "\n", ("bullet",))
            continue

        num_match = re.match(r"^(\d+)\.\s+(.*)$", line)
        if num_match:
            numbered_idx = int(num_match.group(1))
            _insert_with_inline(text, f"{numbered_idx}. {num_match.group(2).strip()}", "numbered")
            text.insert("end", "\n", ("numbered",))
            continue

        _insert_with_inline(text, line, "body")
        text.insert("end", "\n\n", ("body",))

    if in_code:
        flush_code_block()
    if table_rows:
        flush_table()

    text.config(state="disabled")


def open_manual_window(
    root: tk.Tk,
    *,
    colors: dict,
    fonts: dict,
    on_close: Optional[Callable[[], None]] = None,
    md_path: Optional[Path] = None,
) -> tk.Toplevel:
    win = tk.Toplevel(root)
    win.title("Manual de usuario")
    win.configure(bg=colors.get("bg", "#F4F7F6"))
    win.geometry("860x680")
    win.minsize(640, 480)
    win.transient(root)

    header = tk.Frame(win, bg=colors.get("card", "#FFFFFF"), padx=16, pady=12)
    header.pack(fill="x")
    tk.Label(
        header,
        text="Manual de usuario",
        font=fonts.get("h2", ("Segoe UI", 18, "bold")),
        bg=colors.get("card", "#FFFFFF"),
        fg=colors.get("text", "#34495E"),
    ).pack(anchor="w")
    tk.Label(
        header,
        text="Guía paso a paso para cajeros",
        font=("Segoe UI", 10),
        bg=colors.get("card", "#FFFFFF"),
        fg="#7F8C8D",
    ).pack(anchor="w", pady=(4, 0))

    body = tk.Frame(win, bg=colors.get("bg", "#F4F7F6"))
    body.pack(fill="both", expand=True, padx=16, pady=(8, 12))

    scrollbar = tk.Scrollbar(body)
    scrollbar.pack(side="right", fill="y")

    text = tk.Text(
        body,
        wrap="word",
        bg="#FFFFFF",
        fg=colors.get("text", "#34495E"),
        padx=16,
        pady=14,
        relief="flat",
        borderwidth=0,
        highlightthickness=1,
        highlightbackground="#E0E0E0",
        yscrollcommand=scrollbar.set,
        cursor="arrow",
    )
    text.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=text.yview)

    md_file = md_path or DEFAULT_MANUAL_PATH
    render_markdown(
        text,
        load_manual_markdown(md_file),
        colors=colors,
        md_base_dir=md_file.parent,
    )

    footer = tk.Frame(win, bg=colors.get("bg", "#F4F7F6"))
    footer.pack(fill="x", pady=(0, 12))
    tk.Button(
        footer,
        text="Cerrar",
        command=lambda: (_close_manual(win, on_close)),
        bg=colors.get("primary", "#3498DB"),
        fg="white",
        font=("Segoe UI", 10, "bold"),
        bd=0,
        padx=18,
        pady=8,
        cursor="hand2",
    ).pack()

    return win


def _close_manual(win: tk.Toplevel, on_close: Optional[Callable[[], None]]) -> None:
    if callable(on_close):
        on_close()
    win.destroy()
