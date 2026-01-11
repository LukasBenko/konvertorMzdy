# Pokračovať v rozdelení MD a D, tak aby boli samostatné riadky. 
# Spravil by som to ale ako nový súbor. Tento bude slúžiť len na úpravu CSV.

# #!/usr/bin/env python3
"""
clean_csv_header.py
-------------------
Úprava CSV pre konverziu:
1) Odstráni všetky riadky pred hlavičkou.
2) Ponechá iba stĺpce: Názov, Účet MD, Účet Dal, Stred., Zák., Činn.
3) Odstráni medzery z číselných stĺpcov: Účet MD, Účet Dal, Stred., Zák., Činn.
4) Odstráni všetky prázdne riadky.
5) Odstráni časť od riadku „Vypracoval:“ až po koniec.
6) Odstráni sumárne riadky (VAR1/VAR2) a doplní názvy podľa sumárnych skupín.
"""

import csv
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# ---------- Pomocné funkcie ----------

def detect_encoding(path: Path) -> str:
    for enc in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            with path.open("r", encoding=enc) as f:
                f.read(2000)
            return enc
        except Exception:
            continue
    raise RuntimeError("Nepodarilo sa rozpoznať kódovanie súboru.")

def clean_str(s: Optional[str]) -> str:
    """Oreže whitespace a nahradí NBSP (\u00A0) za bežnú medzeru."""
    if s is None:
        return ""
    return s.replace("\u00a0", " ").strip()

def normalize(s: str) -> str:
    return clean_str(s).lower()

def find_header_index(rows: List[List[str]]) -> int:
    for i, row in enumerate(rows):
        joined = ";".join(row)
        if row and clean_str(row[0]) == "Názov" and ("Účet MD" in joined) and ("Účet Dal" in joined):
            return i
    for i, row in enumerate(rows):
        joined = ";".join(row)
        if ("Názov" in joined) and ("Účet MD" in joined) and ("Účet Dal" in joined):
            return i
    raise RuntimeError("Nepodarilo sa nájsť hlavičkový riadok.")

def is_empty_row(row: List[str]) -> bool:
    return not any(clean_str(c) for c in row)

def select_required_columns(rows: List[List[str]]) -> List[List[str]]:
    """
    Ponechá len stĺpce: Názov, Účet MD, Účet Dal, Stred., Zák., Činn.
    Matchuje tolerantne podľa názvov hlavičky (diakritika/skratené tvary).
    Zachová pôvodné poradie.
    """
    if not rows:
        return rows
    header = rows[0]
    norm = [normalize(h) for h in header]

    wanted_patterns = {
        "Názov": ("názov", "nazov"),
        "Účet MD": ("účet md", "ucet md", "md"),
        "Účet Dal": ("účet dal", "ucet dal", "dal"),
        "Stred.": ("stred", "stred."),
        "Zák.": ("zák", "zak", "zák.", "zak."),
        "Činn.": ("činn", "cinn", "činn.", "cinn."),
    }

    keep_indices: List[int] = []
    for idx, name in enumerate(norm):
        for patterns in wanted_patterns.values():
            if any(p in name for p in patterns):
                keep_indices.append(idx)
                break

    if not keep_indices:
        return rows

    trimmed: List[List[str]] = []
    for r in rows:
        trimmed.append([(r[i] if i < len(r) else "") for i in keep_indices])
    return trimmed

def strip_spaces_in_numeric_cols(rows: List[List[str]], header_names: List[str]) -> List[List[str]]:
    """
    V stĺpcoch Účet MD, Účet Dal, Stred., Zák., Činn. odstráni všetky medzery a NBSP.
    """
    if not rows:
        return rows
    header = [normalize(h) for h in rows[0]]
    target_patterns = ("účet md", "ucet md", "účet dal", "ucet dal", "stred", "zák", "zak", "činn", "cinn")

    numeric_indices = [
        i for i, h in enumerate(header)
        if any(p in h for p in target_patterns)
    ]

    cleaned = [rows[0]]
    for row in rows[1:]:
        new_row = list(row)
        for i in numeric_indices:
            if i < len(new_row):
                val = new_row[i].replace("\u00a0", " ").replace(" ", "")
                new_row[i] = val
        cleaned.append(new_row)
    return cleaned

def find_cinn_col_index(header_row: List[str]) -> int:
    norm = [normalize(x) for x in header_row]
    for i, name in enumerate(norm):
        if "činn" in name or "cinn" in name:
            return i
    return len(header_row) - 1 if header_row else 0

def is_summary_variant1(row: List[str], cinn_idx: int) -> bool:
    nonempty = [j for j, c in enumerate(row) if clean_str(c)]
    return set(nonempty) == {0, cinn_idx} if nonempty else False

def is_summary_variant2(row: List[str], cinn_idx: int) -> bool:
    nonempty = [j for j, c in enumerate(row) if clean_str(c)]
    return set(nonempty) == {cinn_idx} if nonempty else False

def forward_fill_from_summary(rows: List[List[str]], cinn_idx: int) -> Tuple[List[List[str]], int, int]:
    if not rows:
        return rows, 0, 0
    out = [rows[0]]
    current_group_name = None
    filled = 0
    removed = 0

    for row in rows[1:]:
        if is_summary_variant1(row, cinn_idx):
            current_group_name = clean_str(row[0])
            removed += 1
            continue
        if is_summary_variant2(row, cinn_idx):
            removed += 1
            continue

        first_clean = clean_str(row[0]) if row else ""
        if not first_clean and current_group_name:
            row = list(row)
            row[0] = current_group_name
            filled += 1

        if first_clean:
            current_group_name = None

        out.append(row)
    return out, filled, removed

# ---------- Hlavná logika ----------

def clean_csv(input_path: Path, output_path: Path):
    enc = detect_encoding(input_path)

    with input_path.open("r", encoding=enc, newline="") as f:
        reader = csv.reader(f, delimiter=';')
        rows = list(reader)

    # 1) Nájdeme hlavičku
    header_index = find_header_index(rows)
    clean_rows = rows[header_index:]

    # 2) Ponecháme len vybrané stĺpce
    clean_rows = select_required_columns(clean_rows)

    # 3) Odstránime medzery v číselných stĺpcoch
    clean_rows = strip_spaces_in_numeric_cols(clean_rows, clean_rows[0])

    # 4) Vyhodíme prázdne riadky
    clean_rows = [row for row in clean_rows if not is_empty_row(row)]

    # 5) Odstránime časť od "Vypracoval:" po koniec
    end_index = None
    for i, row in enumerate(clean_rows):
        first = row[0] if row else ""
        if clean_str(first).startswith("Vypracoval:"):
            end_index = i
            break
    if end_index is not None:
        clean_rows = clean_rows[:end_index]

    if not clean_rows:
        with output_path.open("w", encoding=enc, newline="") as f:
            csv.writer(f, delimiter=';').writerows(clean_rows)
        print(f"✅ Vyčistené CSV uložené: {output_path}\n- Výsledný počet riadkov: 0")
        return

    # 6) Odstránime sumárne riadky a doplníme názvy
    header = clean_rows[0]
    cinn_idx = find_cinn_col_index(header)
    clean_rows, filled_count, removed_summaries = forward_fill_from_summary(clean_rows, cinn_idx)

    # 7) Odstránime posledný sumárny riadok, ak ostal
    removed_last = False
    if len(clean_rows) > 1 and (is_summary_variant1(clean_rows[-1], cinn_idx) or is_summary_variant2(clean_rows[-1], cinn_idx)):
        clean_rows = clean_rows[:-1]
        removed_last = True
        removed_summaries += 1

    # 7b) Odstránime riadky, kde názov položky je „Výplata v hotovosti“
    header = clean_rows[0]
    name_idx = 0  # predpokladáme, že prvý stĺpec = Názov
    before = len(clean_rows)
    clean_rows = [
        row for row in clean_rows
        if not (len(row) > name_idx and clean_str(row[name_idx]).lower() == "výplata v hotovosti")
    ]
    removed_hotovost = before - len(clean_rows)
    if removed_hotovost:
        print(f"- Odstránené riadky s názvom 'Výplata v hotovosti': {removed_hotovost}")

    # 8) Zápis
    with output_path.open("w", encoding=enc, newline="") as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerows(clean_rows)

    # 9) Výpis
    print(f"✅ Vyčistené CSV uložené: {output_path}")
    print(f"- Kódovanie: {enc}")
    print(f"- Odstránené riadky pred hlavičkou: {header_index}")
    print(f"- Ponechané stĺpce: Názov, Účet MD, Účet Dal, Stred., Zák., Činn.")
    print(f"- Odstránené medzery v číselných stĺpcoch (Účet MD–Činn.)")
    if end_index is not None:
        print(f"- Od 'Vypracoval:' po koniec odstránené (riadok {end_index + 1})")
    print(f"- Doplnené názvy: {filled_count}")
    print(f"- Odstránené sumárne riadky: {removed_summaries}" + (" (vrátane posledného)" if removed_last else ""))
    print(f"- Výsledný počet riadkov: {len(clean_rows)}")

# ---------- CLI ----------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Použitie: python3 clean_csv_header.py vstup.csv [vystup.csv]")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else input_path.with_name(f"cleaned__{input_path.name}")
    clean_csv(input_path, output_path)
