"""Reproducible PyInstaller onedir build: pyinstaller ProjectLensAI.spec."""

from PyInstaller.utils.hooks import collect_all, collect_data_files

streamlit_data, streamlit_bins, streamlit_hidden = collect_all("streamlit")
datas = streamlit_data + collect_data_files("altair") + [
    ("app.py", "."), ("prompts", "prompts"),
]
datas = [item for item in datas if ".env" not in item[0] and "__pycache__" not in item[0]]

a = Analysis(
    ["launcher.py"], pathex=["."], binaries=streamlit_bins, datas=datas,
    hiddenimports=streamlit_hidden + ["app", "core.html_renderer", "markdown.extensions.tables",
                                   "markdown.extensions.sane_lists"],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=["pytest", "PyInstaller"],
    noarchive=False,
)
# The pyarrow hook includes upstream test samples that the app never uses.
a.datas = [item for item in a.datas if not item[0].replace("\\", "/").startswith("pyarrow/tests/")]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ProjectLensAI",
          debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
          console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name="ProjectLensAI")
