#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
"""
Konvektor XML – desktopová aplikácia (Tkinter)

Funkcie:
- GUI na zadanie atribútov <uctovny_doklad>: cislo_ud, datum_ud, mandant_id, druh_ud, typ_ud, text_ud
- Výber CSV (aj „špinavého“) → najprv spustí clean_csv_header.py, potom create_xml_file.py
- Uloženie XML cez „Uložiť ako…“
- Pripravené na zabalenie do .exe / .app (PyInstaller)
"""

# ===== Pomocné pre „frozen“ spustenie (.exe / .app) =====
import sys, runpy
from pathlib import Path

def resource_path(name: str) -> Path:
    """Vracia správnu cestu k pribaleným súborom (funguje aj v .exe/.app)"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / name
    return Path(__file__).with_name(name)

def run_script(script_path: Path, argv: list[str]) -> int:
    """Spustí iný .py skript priamo v tom istom procese"""
    old_argv = sys.argv
    try:
        sys.argv = [str(script_path)] + argv
        runpy.run_path(str(script_path), run_name="__main__")
        return 0
    except SystemExit as e:
        return int(getattr(e, "code", 1))
    finally:
        sys.argv = old_argv

# ===== Aplikácia =====
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import tempfile, csv, unicodedata
from typing import Dict

DOC_ATTRS = ["cislo_ud","datum_ud","mandant_id","druh_ud","typ_ud","text_ud"]
REQUIRED_HEADERS = ["Názov","Účet MD","Účet Dal","Stred.","Zák.","Činn."]

def normalize_header(h: str) -> str:
    h = (h or "").strip().lower()
    h = unicodedata.normalize("NFKD", h).encode("ascii", "ignore").decode("ascii")
    return h

def try_find_header_and_write_subset(src: Path, dst: Path) -> bool:
    """Fallback čistenia: nájde riadok hlavičky a zapíše CSV odtiaľ po koniec."""
    raw = src.read_bytes()
    for enc in ("utf-8-sig","utf-8","cp1250"):
        try:
            text = raw.decode(enc)
            break
        except Exception:
            text = None
    if text is None:
        text = raw.decode("utf-8", errors="replace")

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=[",",";","\t","|"])
    except Exception:
        class Simple(csv.Dialect):
            delimiter = ";"
            quotechar = '"'
            doublequote = True
            skipinitialspace = True
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL
        dialect = Simple()

    lines = text.splitlines()
    reader = csv.reader(lines, dialect=dialect)
    needed = {normalize_header(h) for h in REQUIRED_HEADERS}
    header_idx = None
    for i, row in enumerate(reader):
        seen = {normalize_header(c) for c in row if c is not None}
        if needed.issubset(seen):
            header_idx = i
            break
    if header_idx is None:
        return False
    out_text = "\n".join(lines[header_idx:]) + "\n"
    dst.write_text(out_text, encoding="utf-8")
    return True

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CSV → XML konvertor")
        self.geometry("760x560")
        self.minsize(680, 520)

        self.doc_vars: Dict[str, tk.StringVar] = {k: tk.StringVar() for k in DOC_ATTRS}

        # 🔽 PREDVYPLNENÉ HODNOTY
        self.doc_vars["mandant_id"].set("1")
        self.doc_vars["druh_ud"].set("ID mzdy")
        self.doc_vars["typ_ud"].set("I")

        self.csv_path: Path | None = None
        self._build_ui()

    def _build_ui(self):
        pad = 10
        frm = ttk.Frame(self)
        frm.pack(fill=tk.BOTH, expand=True, padx=pad, pady=pad)

        box = ttk.LabelFrame(frm, text="Atribúty <uctovny_doklad>")
        box.pack(fill=tk.X, padx=pad, pady=(0, pad))
        grid = ttk.Frame(box)
        grid.pack(fill=tk.X, padx=pad, pady=pad)
        for i, k in enumerate(DOC_ATTRS):
            ttk.Label(grid, text=k+":", width=14).grid(row=i, column=0, sticky=tk.W, pady=3)
            ttk.Entry(grid, textvariable=self.doc_vars[k]).grid(row=i, column=1, sticky=tk.EW, pady=3)
        grid.columnconfigure(1, weight=1)

        pick = ttk.LabelFrame(frm, text="Vstupný CSV súbor (môže byť nevyčistený)")
        pick.pack(fill=tk.X, padx=pad, pady=(0, pad))
        row = ttk.Frame(pick)
        row.pack(fill=tk.X, padx=pad, pady=pad)
        self.csv_label = ttk.Label(row, text="(nevybraný)")
        self.csv_label.pack(side=tk.LEFT)
        ttk.Button(row, text="Vybrať CSV…", command=self.choose_csv).pack(side=tk.RIGHT)

        actions = ttk.Frame(frm)
        actions.pack(fill=tk.X, padx=pad, pady=pad)
        ttk.Button(actions, text="Konvertovať a uložiť XML…", command=self.run_conversion).pack(side=tk.RIGHT)

        self.status = ttk.Label(frm, text="Pripravené", anchor=tk.W)
        self.status.pack(fill=tk.X, padx=pad, pady=(0, pad))

    def choose_csv(self):
        path = filedialog.askopenfilename(
            title="Vyber CSV súbor",
            filetypes=[("CSV súbory", "*.csv"), ("Všetky súbory", "*.*")]
        )
        if not path:
            return
        self.csv_path = Path(path)
        self.csv_label.config(text=str(self.csv_path))
        self.status.config(text=f"Vybrané CSV: {self.csv_path.name}")

    def run_conversion(self):
        try:
            if not self.csv_path:
                messagebox.showwarning("Chýba vstup", "Vyber najprv CSV súbor.")
                return

            doc_attrs = {k: v.get() for k, v in self.doc_vars.items()}

            with tempfile.TemporaryDirectory() as td:
                td = Path(td)
                cleaned_csv = td / "cleaned.csv"
                out_xml = td / "out.xml"

                # 1) clean_csv_header.py
                cleaner = resource_path("clean_csv_header.py")
                ran_cleaner = False
                if cleaner.exists():
                    ret = run_script(cleaner, [str(self.csv_path), str(cleaned_csv)])
                    if ret == 0 and cleaned_csv.exists() and cleaned_csv.stat().st_size > 0:
                        ran_cleaner = True
                    else:
                        self.status.config(text="Externé čistenie zlyhalo – skúšam interné čistenie…")

                if not ran_cleaner:
                    ok = try_find_header_and_write_subset(self.csv_path, cleaned_csv)
                    if not ok:
                        raise SystemExit("Nepodarilo sa nájsť hlavičku CSV (Názov, Účet MD, Účet Dal, Stred., Zák., Činn.).")

                # 2) create_xml_file.py
                converter = resource_path("create_xml_file.py")
                if not converter.exists():
                    raise SystemExit("Nenájdený create_xml_file.py v tom istom priečinku.")

                args = [str(cleaned_csv), str(out_xml), "--no-interactive"]
                for k in DOC_ATTRS:
                    args.extend([f"--{k}", doc_attrs.get(k, "")])

                ret = run_script(converter, args)
                if ret != 0 or not out_xml.exists():
                    raise SystemExit("Konverzia zlyhala – create_xml_file.py vrátil chybu.")

                out_path = filedialog.asksaveasfilename(
                    title="Ulož XML ako",
                    defaultextension=".xml",
                    filetypes=[("XML súbory", "*.xml"), ("Všetky súbory", "*.*")]
                )
                if not out_path:
                    return
                Path(out_path).write_bytes(out_xml.read_bytes())

            self.status.config(text=f"Uložené: {out_path}")
            messagebox.showinfo("Hotovo", f"XML bolo uložené do:\n{out_path}")

        except SystemExit as e:
            messagebox.showerror("Chyba", str(e))
        except Exception as e:
            messagebox.showerror("Neočekávaná chyba", str(e))

if __name__ == "__main__":
    App().mainloop()
