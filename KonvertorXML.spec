# -*- mode: python ; coding: utf-8 -*-

hidden = [
    "tkinter",
    "tkinter.font",
    "xml",
    "xml.etree",
    "xml.etree.ElementTree",
]

block_cipher = None

a = Analysis(
    ['konvertor_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('clean_csv_header.py', '.'),
        ('create_xml_file.py', '.'),
        ('logo.ico', '.'),  # aby bola ikonka dostupná aj runtime (ak ju budeš používať v appke)
    ],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='KonvertorXML',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='logo.ico'  # ak nemáš logo.ico, tento riadok vymaž
)
