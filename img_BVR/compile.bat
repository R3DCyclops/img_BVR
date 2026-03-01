@echo off
setlocal

set PYTHON=python
set SCRIPT_NAME=main
set APP_NAME=img_BVR
set VERSION=1.0

if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "%SCRIPT_NAME%.spec" del /q "%SCRIPT_NAME%.spec"

echo [1/4] Installing dependencies...
%PYTHON% -m pip install pyinstaller --upgrade --quiet
%PYTHON% -m pip install -r requirements.txt --quiet 2>nul

echo [2/4] Building EXE...
%PYTHON% -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "%APP_NAME%" ^
    --icon="assets\ico.ico" ^
    --add-data="assets\ico.ico;assets" ^
    --add-data="assets\avatar.gif;assets" ^
    --add-data="assets\logo.png;assets" ^
    --add-data="assets\util.mp3;assets" ^
    --add-data="assets\presets_view;assets\presets_view" ^
    --add-data="src\gtalib;src\gtalib" ^
    --add-data="src\gtalib\data;src\gtalib\data" ^
    --add-data="src\gtalib\pyffi;src\gtalib\pyffi" ^
    --hidden-import=pygame ^
    --hidden-import=pygame.locals ^
    --hidden-import=pygame.mixer ^
    --hidden-import=moderngl ^
    --hidden-import=PIL ^
    --hidden-import=PIL.Image ^
    --hidden-import=PIL.ImageTk ^
    --hidden-import=PIL.ImageSequence ^
    --hidden-import=tkinter ^
    --hidden-import=tkinter.ttk ^
    --hidden-import=src.extractor ^
    --hidden-import=src.renderer ^
    --hidden-import=src.view ^
    --hidden-import=src.gtalib ^
    --hidden-import=src.gtalib.dff ^
    --hidden-import=src.gtalib.txd ^
    --hidden-import=src.gtalib.img ^
    --hidden-import=src.gtalib.col ^
    --hidden-import=src.gtalib.map ^
    --exclude-module=torch ^
    --exclude-module=torchvision ^
    --exclude-module=torchaudio ^
    --exclude-module=test ^
    --exclude-module=unittest ^
    "%SCRIPT_NAME%.py"

echo.
if exist "dist\%APP_NAME%.exe" (
    echo [3/4] Build successful!
    echo [4/4] EXE located in: dist\%APP_NAME%.exe
    echo.
    echo   %APP_NAME% v%VERSION% ready to use!
) else (
    echo [3/4] XXX Build failed! Check errors above.
    echo [4/4] No EXE file created.
)

pause