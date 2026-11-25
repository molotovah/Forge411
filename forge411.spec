# -*- mode: python ; coding: utf-8 -*-
# Compilation : pyinstaller forge411.spec  →  dist/Forge411.exe
from PyInstaller.utils.hooks import collect_dynamic_libs

a = Analysis(
    ["Forge411.pyw"],
    pathex=[],
    binaries=collect_dynamic_libs("pymediainfo"),
    datas=[("forge411/assets", "forge411/assets"), ("LICENSE", "."), ("NOTICE", ".")],
    hiddenimports=["PIL._tkinter_finder"],
    excludes=["numpy", "matplotlib", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="Forge411",
    icon="forge411/assets/forge411.ico",
    console=False,
    upx=False,
    version="version_info.txt",
)
