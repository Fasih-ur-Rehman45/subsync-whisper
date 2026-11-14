# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe for the Linux build: a portable folder with `subsync`
# (window, or command line with --cli) and `subsync-cmd` (command line).
# Debugging data is removed from wxPython and the engine after packaging (see
# the workflow); stripping every library breaks NumPy's bundled OpenBLAS.

from PyInstaller.utils.hooks import collect_all

# faster-whisper (speech recognition), the translation model runtime and their
# native parts, as in windows.spec
extra_datas, extra_binaries, extra_hiddenimports = [], [], []
for package in ('faster_whisper', 'ctranslate2', 'onnxruntime', 'av', 'tokenizers', 'sentencepiece'):
    datas, binaries, hiddenimports = collect_all(package)
    extra_datas += datas
    extra_binaries += binaries
    extra_hiddenimports += hiddenimports


main_a = Analysis(['bin/subsync'],
        pathex=['.'],
        binaries=extra_binaries,
        datas=[
            ('LICENSE', '.'),
            ('subsync/key.pub', '.'),
            ('subsync/img', 'img'),
            ('subsync/locale', 'locale'),
            ] + extra_datas,
        hiddenimports=extra_hiddenimports,
        hookspath=[],
        runtime_hooks=[],
        excludes=[],
        cipher=None,
        noarchive=False)

main_pyz = PYZ(main_a.pure, main_a.zipped_data, cipher=None)

main_exe = EXE(main_pyz,
        main_a.scripts,
        [],
        exclude_binaries=True,
        name='subsync',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True)

# same program, starts in command line mode (see subsync/__main__.py)
main_cmd = EXE(main_pyz,
        main_a.scripts,
        [],
        exclude_binaries=True,
        name='subsync-cmd',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True)

main_coll = COLLECT(main_exe,
        main_cmd,
        main_a.binaries,
        main_a.zipfiles,
        main_a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name='subsync')
