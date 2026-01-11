#!/usr/bin/env python3
"""
csv_to_udxml.py — interactive + pevné mapovanie (MD najprv, potom D)

Výstup presne podľa tvojej špecifikácie:

<?xml version="1.0"?>
<uctovne_doklady>
  <uctovny_doklad cislo_ud=... datum_ud=... mandant_id=... druh_ud=... typ_ud=... text_ud=...>
    <polozka_ud suma=... ucet=... strana=... os=... eo=... text_pud=... />
    ...
  </uctovny_doklad>
</uctovne_doklady>

Pravidlá mapovania CSV → XML (fixné podľa inštrukcie):
- text_pud ← Názov
- os       ← Stred.
- eo       ← Zák.
- suma     ← Činn.  (desatinná čiarka sa konvertuje na bodku)
- ucet/strana: pre každý riadok najskôr vytvor položku so stranou "M" a ucet ← Účet MD,
               a potom vytvor položku so stranou "D" a ucet ← Účet Dal.

Skript ťa najskôr interaktívne vyzve na zadanie atribútov <uctovny_doklad>,
potom načíta CSV (automaticky zistí oddeľovač a kódovanie) a vygeneruje XML.

Použitie:
  python csv_to_udxml.py vstup.csv vystup.xml
  python csv_to_udxml.py vstup.csv vystup.xml --delimiter ';'   # ak chceš natvrdo oddeľovač
  python csv_to_udxml.py vstup.csv vystup.xml --keep-empty       # ponechá aj prázdne atribúty
  python csv_to_udxml.py vstup.csv vystup.xml --no-interactive \
    --cislo_ud 250901 --datum_ud 30.09.2025 --mandant_id 1 --druh_ud "ID UCTO" --typ_ud I --text_ud "Zaúčtovanie ucto"
"""
from __future__ import annotations
import argparse
import csv
from pathlib import Path
from tkinter.font import names
from typing import Dict, Iterable, List, Tuple
import unicodedata
import xml.etree.ElementTree as ET
from xml.dom import minidom
import sys

DOC_ATTRS = [
    "cislo_ud",
    "datum_ud",
    "mandant_id",
    "druh_ud",
    "typ_ud",
    "text_ud",
]

# Potrebné hlavičky v CSV (s diakritikou a bodkami presne podľa ukážky)
CSV_HEADERS = {
    "nazov": "Názov",
    "ucet_md": "Účet MD",
    "ucet_dal": "Účet Dal",
    "stred": "Stred.",
    "zak": "Zák.",
    "cinn": "Činn.",
}

ITEM_ATTRS = [
    "suma",
    "ucet",
    "strana",
    "os",
    "eo",
    "text_pud",
]


def detect_encoding(path: Path) -> Tuple[str, bytes]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1250"):
        try:
            raw.decode(enc)
            return enc, raw
        except UnicodeDecodeError:
            continue
    return "utf-8", raw


def sniff_dialect(sample: str) -> Tuple[str, csv.Dialect]:
    sniffer = csv.Sniffer()
    try:
        dialect = sniffer.sniff(sample, delimiters=[",", ";", "	", "|"])
        return dialect.delimiter, dialect
    except Exception:
        class Simple(csv.Dialect):
            delimiter = ","
            quotechar = '"'
            doublequote = True
            skipinitialspace = True
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL
        return ",", Simple()


def read_csv(path: Path, forced_delim: str | None) -> Tuple[List[dict], List[str]]:
    enc, raw = detect_encoding(path)
    text = raw.decode(enc, errors="replace")

    if forced_delim:
        class Forced(csv.Dialect):
            delimiter = forced_delim
            quotechar = '"'
            doublequote = True
            skipinitialspace = True
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL
        dialect = Forced()
    else:
        _, dialect = sniff_dialect(text[:4096])

    reader = csv.DictReader(text.splitlines(), dialect=dialect)
    rows = list(reader)
    headers = reader.fieldnames or []
    return rows, headers


def normalize_header(h: str) -> str:
    """Diakritika/veľkosť písmen nezáleží (iba pre interné kontroly)."""
    h = h.strip().lower()
    h = unicodedata.normalize("NFKD", h).encode("ascii", "ignore").decode("ascii")
    return h


def ensure_required_columns(headers: List[str]) -> Dict[str, str]:
    """Vyhľadá originálne názvy stĺpcov podľa očakávaných hlavičiek.
    Ak niektorý chýba, skončí s chybou a vypíše, čo je prítomné.
    """
    by_norm = {normalize_header(h): h for h in headers}
    needed_norm = {
        "nazov": normalize_header(CSV_HEADERS["nazov"]),
        "ucet_md": normalize_header(CSV_HEADERS["ucet_md"]),
        "ucet_dal": normalize_header(CSV_HEADERS["ucet_dal"]),
        "stred": normalize_header(CSV_HEADERS["stred"]),
        "zak": normalize_header(CSV_HEADERS["zak"]),
        "cinn": normalize_header(CSV_HEADERS["cinn"]),
    }
    missing = [k for k, n in needed_norm.items() if n not in by_norm]
    if missing:
        names = {
            "nazov": CSV_HEADERS["nazov"],
            "ucet_md": CSV_HEADERS["ucet_md"],
            "ucet_dal": CSV_HEADERS["ucet_dal"],
            "stred": CSV_HEADERS["stred"],
            "zak": CSV_HEADERS["zak"],
            "cinn": CSV_HEADERS["cinn"],
        }
        present = ", ".join(sorted(by_norm.keys()))
        expected = ", ".join(names[k] for k in missing)
        raise SystemExit(
            "Chýbajúce stĺpce v CSV: " + expected + "\n" +
            "Prítomné (normalizované) hlavičky: " + present
        )
    return {k: by_norm[n] for k, n in needed_norm.items()}


def prompt_input(prompt_text: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt_text}{suffix}: ").strip()
    return val or (default or "")


def collect_doc_attributes(no_interactive: bool, cli_values: Dict[str, str]) -> Dict[str, str]:
    attrs: Dict[str, str] = {}
    if no_interactive:
        missing = [k for k in DOC_ATTRS if not cli_values.get(k)]
        if missing:
            raise SystemExit("Chýbajú povinné atribúty dokladu: " + ", ".join(missing))
        return {k: cli_values[k] for k in DOC_ATTRS}

    print("Zadaj hodnoty pre <uctovny_doklad> (Enter = prázdne):")
    for k in DOC_ATTRS:
        attrs[k] = prompt_input(k)
    print("Zhrnutie:")
    for k in DOC_ATTRS:
        print(f"  {k} = {attrs[k]}")
    ok = input("Je to v poriadku? [Enter=Áno / n=Nie]: ").strip().lower()
    if ok == 'n':
        return collect_doc_attributes(False, {})
    return attrs


def to_amount(v: str) -> str:
    v = (v or "").strip()
    # zamení iba jednu des. čiarku na bodku, tisícky s medzerou ponechá odstránením medzier
    v = v.replace(" ", "")
    if v.count(",") == 1 and v.count(".") == 0:
        v = v.replace(",", ".")
    return v


def build_xml(doc_attrs: Dict[str, str], rows: Iterable[dict], cols: Dict[str, str], keep_empty: bool) -> ET.Element:
    root = ET.Element("uctovne_doklady")
    doc_el = ET.SubElement(root, "uctovny_doklad")
    for k in DOC_ATTRS:
        v = (doc_attrs.get(k, "") or "").strip()
        if v == "" and not keep_empty:
            continue
        doc_el.set(k, v)

    # Najprv vypíš VŠETKY M položky pre všetky riadky...
    m_buffer = []
    d_buffer = []

    for r in rows:
        text_pud = (r.get(cols["nazov"], "") or "").strip()
        os_val   = (r.get(cols["stred"], "") or "").strip()
        eo_val   = (r.get(cols["zak"], "") or "").strip()
        suma_val = to_amount(r.get(cols["cinn"], ""))
        ucet_m   = (r.get(cols["ucet_md"], "") or "").strip()
        ucet_d   = (r.get(cols["ucet_dal"], "") or "").strip()

        m_attrs = {
            "text_pud": text_pud,
            "os": os_val,
            "eo": eo_val,
            "suma": suma_val,
            "ucet": ucet_m,
            "strana": "M",
        }
        d_attrs = {
            "text_pud": text_pud,
            "os": os_val,
            "eo": eo_val,
            "suma": suma_val,
            "ucet": ucet_d,
            "strana": "D",
        }
        m_buffer.append(m_attrs)
        d_buffer.append(d_attrs)    # ...až potom VŠETKY D položky v rovnakom poradí riadkov.
    # Pri zápise zachováme pevné poradie atribútov: suma, ucet, strana, os, eo, text_pud
    ORDER = ["suma", "ucet", "strana", "os", "eo", "text_pud"]

    def write_item(parent: ET.Element, attrs: Dict[str, str]):
        el = ET.SubElement(parent, "polozka_ud")
        for key in ORDER:
            v = (attrs.get(key, "") or "").strip()
            if v == "" and not keep_empty:
                continue
            el.set(key, v)

    for attrs in m_buffer:
        write_item(doc_el, attrs)

    for attrs in d_buffer:
        write_item(doc_el, attrs)

    return root


def pretty_no_decl(elem: ET.Element) -> str:
    rough = ET.tostring(elem, encoding="utf-8")
    parsed = minidom.parseString(rough)
    pretty = parsed.toprettyxml(indent="  ")
    lines = pretty.splitlines()
    if lines and lines[0].startswith("<?xml"):
        lines = lines[1:]
    # odstráň prázdne riadky, zachovaj odsadenie a vráť s koncovým \n
    return "\n".join(line for line in lines if line.strip() != "") + "\n"


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CSV → uctovne_doklady XML (MD potom D, interaktívne atribúty dokladu)")
    ap.add_argument("input", type=Path, help="Input CSV path")
    ap.add_argument("output", type=Path, help="Output XML path")
    ap.add_argument("--delimiter", dest="delimiter", default=None, help="Force CSV delimiter (napr. ';')")
    ap.add_argument("--keep-empty", action="store_true", help="Nezahadzovať prázdne atribúty")
    ap.add_argument("--no-interactive", action="store_true", help="Bez otázok (použije hodnoty z parametrov nižšie)")
    for k in DOC_ATTRS:
        ap.add_argument(f"--{k}", dest=k)

    args = ap.parse_args(argv)

    # 1) Atribúty dokladu
    cli_values = {k: getattr(args, k) for k in DOC_ATTRS}
    doc_attrs = collect_doc_attributes(args.no_interactive, cli_values)

    # 2) Čítanie CSV + kontrola hlavičiek
    rows, headers = read_csv(args.input, args.delimiter)
    if not headers:
        raise SystemExit("CSV nemá hlavičku.")
    cols = ensure_required_columns(headers)

    # 3) Stavba XML
    root = build_xml(doc_attrs, rows, cols, keep_empty=args.keep_empty)

    # 4) Zápis (presná deklarácia)
    xml_body = pretty_no_decl(root)
    xml_text = "<?xml version=\"1.0\"?>\n" + xml_body
    args.output.write_text(xml_text, encoding="utf-8")
    print(f"Wrote {args.output} ({len(xml_text)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
