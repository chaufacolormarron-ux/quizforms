@echo off
cd /d "%~dp0"
echo ==========================================
echo        QuizForms v0.7 Online Ready
echo ==========================================
echo.
echo Instalando/verificando dependencias...
py -m pip install -r requirements.txt
if errorlevel 1 goto error

echo.
echo Abriendo QuizForms...
py -m streamlit run app.py
goto end

:error
echo.
echo Ocurrio un error. Verifica que Python este instalado.
pause

:end
