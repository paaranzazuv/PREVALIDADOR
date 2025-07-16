@echo off
setlocal

REM ------------------------------------------------------
REM Script completo de despliegue para Prevalidador
REM - Verifica Git y Python (instala silenciosamente si faltan)
REM - Clona o actualiza el repositorio
REM - Crea/activa virtualenv
REM - Instala el paquete en editable
REM - Ejecuta validaciones con logging incremental y notificación
REM ------------------------------------------------------

REM 1) Ruta raíz donde está este .bat
set "ROOT=%~dp0"

REM 2) Definir carpetas internas
set "INBOX=%ROOT%Archivos"
set "HISTORICO=%ROOT%Historico"
set "RESULTADOS=%ROOT%Resultados"
set "REPO=%ROOT%prevalidador"
set "LOGDIR=%ROOT%Logs"

REM 3) Verificar e instalar Git si no existe
where git >nul 2>&1
if errorlevel 1 (
    echo [%DATE% %TIME%] Git no encontrado. Instalando Git...
    winget install --silent --accept-package-agreements --accept-source-agreements Git.Git
)

REM 4) Verificar e instalar Python si no existe
where python >nul 2>&1
if errorlevel 1 (
    echo [%DATE% %TIME%] Python no encontrado. Instalando Python...
    winget install --silent --accept-package-agreements --accept-source-agreements Python.Python.3
)

REM 5) Crear carpeta Logs oculta si no existe
if not exist "%LOGDIR%" (
    mkdir "%LOGDIR%"
    attrib +h "%LOGDIR%"
)

REM 6) Generar timestamp para el log
for /f "tokens=2-4 delims=/" %%a in ("%date%") do (
    set "DAY=%%a" & set "MONTH=%%b" & set "YEAR=%%c"
)
for /f "tokens=1-2 delims=:." %%a in ("%time%") do (
    set "HOUR=%%a" & set "MIN=%%b"
)
set "TIMESTAMP=%YEAR%-%MONTH%-%DAY%_%HOUR%-%MIN%"
set "LOGFILE=%LOGDIR%\run_validador_%TIMESTAMP%.log"

REM 7) Ejecutar todo capturando stdout/stderr en log
(
    echo [%DATE% %TIME%] Inicio del proceso

    REM Clonar o actualizar repositorio
    if exist "%REPO%\" (
        echo [%DATE% %TIME%] Actualizando repositorio...
        pushd "%REPO%"
        git pull
        popd
    ) else (
        echo [%DATE% %TIME%] Clonando repositorio...
        git clone https://github.com/tu_usuario/prevalidador.git "%REPO%"
    )

    REM Crear entorno virtual
    if not exist "%REPO%\.venv\" (
        echo [%DATE% %TIME%] Creando entorno virtual...
        python -m venv "%REPO%\.venv"
    )

    REM Activar entorno virtual
    call "%REPO%\.venv\Scripts\activate"

    REM Instalar el paquete
    echo [%DATE% %TIME%] Instalando dependencias...
    python -m pip install --upgrade pip
    pip install -e "%REPO%"

    REM Ejecutar el Prevalidador
    echo [%DATE% %TIME%] Ejecutando validaciones...
    prevalidar "%INBOX%" "%REPO%\config\rules\reglas_nph.json" "%REPO%\config\catalogs\catalog_nph.xlsx" "%HISTORICO%" "%RESULTADOS%"

    echo [%DATE% %TIME%] Proceso completado
) > "%LOGFILE%" 2>&1

REM 8) Notificar al usuario
mshta "javascript:var sh=new ActiveXObject('WScript.Shell'); sh.Popup('Proceso completado satisfactoriamente!',10,'Prevalidador',64);close()"

echo Log generado en: %LOGFILE%

REM 9) Cerrar sin interacción
exit /b
