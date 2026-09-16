# PatientHistoryAnalyzer.spec
# build with:  pyinstaller PatientHistoryAnalyzer.spec --noconfirm
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("matplotlib")            # matplotlib data / fonts
datas += [("resources/ctcae_v5.yaml", "resources"), ("resources/reference_ranges.csv","resources"),]

a = Analysis(
    ["main.py"],
    datas=datas,
    excludes=["PyQt5", "PyQt6", "tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PatientHistoryAnalyzer",
    console=False,
    icon="resources/app.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="PatientHistoryAnalyzer",
)
