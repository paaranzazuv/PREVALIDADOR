"""
Script principal para ejecutar el prevalidador en masa:
  1. Recorre todos los archivos Excel (.xlsx) en la carpeta de entrada (inbox).
  2. Detecta automáticamente si corresponde a RPH o NPH según la hoja 'FichasPrediales'.
  3. Ejecuta las validaciones definidas en JSON (reglas_rph.json o reglas_nph.json).
  4. Guarda resultados en la carpeta Resultados/rph o Resultados/nph.
  5. Mueve el archivo original a Historico/rph o Historico/nph.
"""

import argparse
import logging
import warnings
import shutil
from pathlib import Path
import pandas as pd

from prevalidador._internals.rules_engine import ejecutar_validaciones

# Silenciar warnings de validación de datos de openpyxl
warnings.filterwarnings(
    "ignore",
    message="Data Validation extension is not supported and will be removed"
)

# Configuración de logging
logging.basicConfig(
    format="%(asctime)s %(levelname)s: %(message)s",
    level=logging.INFO
)

def detectar_tipo_archivo(file_path: Path) -> str:
    """
    Detecta si el archivo corresponde a RPH o NPH:
    - Si existe la hoja 'FichasPrediales' es RPH
    - Si no, se asume NPH
    """
    try:
        hojas = pd.ExcelFile(file_path).sheet_names
        return "rph" if "FichasPrediales" in hojas else "nph"
    except Exception as e:
        logging.error(f"No se pudo leer {file_path.name} para detectar tipo: {e}")
        return "nph"  # fallback por defecto

def main():
    """
    Función principal para la prevalidación de cargas masivas.
    - Detecta automáticamente RPH o NPH según la hoja FichasPrediales.
    - Ejecuta validaciones con el JSON correspondiente.
    - Clasifica resultados y originales en carpetas separadas.
    """
    parser = argparse.ArgumentParser(
        description="Prevalidador masivo de Excel con clasificación RPH/NPH, histórico y resultados"
    )
    parser.add_argument('inbox_dir',      type=Path, help='Carpeta con archivos a validar (Archivos)')
    parser.add_argument('rules_json',     type=Path, help='Ruta base de JSON de reglas (para ubicar la carpeta)')
    parser.add_argument('catalogs_path',  type=Path, help='Carpeta con catálogos (.xlsx/.csv)')
    parser.add_argument('historico_dir',  type=Path, help='Carpeta para archivos procesados (Historico)')
    parser.add_argument('resultados_dir', type=Path, help='Carpeta para archivos de salida (Resultados)')
    args = parser.parse_args()

    # Asignar rutas de argumentos
    inbox_dir = args.inbox_dir
    catalogs_path = args.catalogs_path
    historico_dir = args.historico_dir
    resultados_dir = args.resultados_dir

    # Carpeta donde están los JSON de reglas (usamos parent del argumento)
    reglas_folder = args.rules_json

    logging.info(f"Ejecutando validaciones masivas...")

    # Validar y crear las carpetas base si no existen
    for folder in (inbox_dir, historico_dir, resultados_dir):
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)

    # Buscar archivos Excel en la bandeja de entrada
    files = [f for f in inbox_dir.glob("*.xlsx") if not f.stem.endswith("_validacion")]
    if not files:
        logging.info(f"No se encontraron archivos .xlsx en '{inbox_dir}'.")
        return

    # Procesar cada archivo Excel encontrado
    for input_file in files:
        logging.info(f"Procesando: {input_file.name}")

        # 1️⃣ Detectar tipo (RPH o NPH) según la hoja FichasPrediales
        tipo = detectar_tipo_archivo(input_file)
        logging.info(f"Tipo detectado: {tipo.upper()}")

        # Seleccionar automáticamente el JSON correcto según tipo
        if tipo == "rph":
            rules_path = reglas_folder / "reglas_rph.json"
        else:
            rules_path = reglas_folder / "reglas_nph.json"

        # 2️⃣ Ejecutar las validaciones con las reglas detectadas
        errores = ejecutar_validaciones(
            file_path=str(input_file),
            path_rules=str(rules_path),
            catalogs_path=str(catalogs_path)
        )

        # Agrupar errores por hoja para reportarlos
        errores_por_hoja = {}
        for err in errores:
            errores_por_hoja.setdefault(err.sheet, []).append(err)

        # Leer todas las hojas originales y limpiar filas completamente vacías
        try:
            xls = pd.read_excel(str(input_file), sheet_name=None, dtype=str)

            # Limpiar cada hoja: eliminar filas en blanco totales
            for hoja, df in xls.items():
                xls[hoja] = df.dropna(how="all").reset_index(drop=True)

        except Exception as e:
            logging.error(f"Error al leer '{input_file.name}': {e}")
            continue


        # 3️⃣ Guardar archivo validado en subcarpeta según tipo detectado
        output_subdir = resultados_dir / tipo
        output_subdir.mkdir(parents=True, exist_ok=True)
        output_file = output_subdir / f"{input_file.stem}_validacion.xlsx"

        try:
            with pd.ExcelWriter(str(output_file), engine="openpyxl") as writer:
                # Escribir cada hoja con columna 'Errores'
                for hoja, df in xls.items():
                    df_out = df.copy()
                    # Compilar errores por fila
                    records = []
                    for err in errores_por_hoja.get(hoja, []):
                        if err.row is not None:
                            idx = err.row  # índice de la fila
                            if 0 <= idx < len(df_out):
                                records.append({'idx': idx, 'msg': err.message})
                    # Agrupar mensajes por índice de fila
                    if records:
                        err_df = pd.DataFrame(records)
                        agg = err_df.groupby('idx')['msg'].apply(lambda msgs: '; '.join(msgs))
                    else:
                        agg = pd.Series(dtype=str)
                    df_out['Errores'] = df_out.index.map(agg).fillna('')
                    df_out.to_excel(writer, sheet_name=hoja, index=False)

                # Crear hoja Resumen con totales por hoja
                resumen = []
                for hoja in xls.keys():
                    errs = errores_por_hoja.get(hoja, [])
                    total = len(errs)
                    struct_msgs = [e.message for e in errs if e.row is None]
                    resumen.append({
                        'Hoja': hoja,
                        'TotalErrores': total,
                        'Error': '; '.join(struct_msgs)
                    })
                pd.DataFrame(resumen).to_excel(writer, sheet_name='Resumen', index=False)

            logging.info(f"✅ Validación completada: {output_file.name}")
        except Exception as e:
            logging.error(f"Error al escribir '{output_file.name}': {e}")
            continue

        # 4️⃣ Mover original a subcarpeta del histórico según tipo detectado
        try:
            historico_subdir = historico_dir / tipo
            historico_subdir.mkdir(parents=True, exist_ok=True)
            dest = historico_subdir / input_file.name
            shutil.move(str(input_file), str(dest))
            logging.info(f"Original movido a: {dest}")
        except Exception as e:
            logging.warning(f"No se pudo mover '{input_file.name}' a Historico/{tipo}/: {e}")

    logging.info("Proceso completado.")


if __name__ == '__main__':
    main()
