"""
Script principal para ejecutar el prevalidador en masa:
  1. Recorre todos los archivos Excel (.xlsx) en la carpeta de entrada (inbox).
  2. Para cada archivo:
      a. Ejecuta las validaciones definidas en JSON.
      b. Genera un nuevo archivo con sufijo '_validacion' en la carpeta Resultados.
      c. Agrega columna 'Errores' en cada hoja y hoja 'Resumen'.
      d. Mueve el archivo original a la carpeta Histórico.
"""

import argparse
import logging
import warnings
import shutil
from pathlib import Path

import pandas as pd
from openpyxl import utils # Importado pero no usado en el snippet, se mantiene por si es usado en otras partes del código original.

from prevalidador._internals.rules_engine import ejecutar_validaciones
from prevalidador.errors import ValidationError # Importado pero no usado en el snippet, se mantiene por si es usado en otras partes del código original.

# Silenciar warnings de validación de datos de openpyxl
warnings.filterwarnings(
    "ignore",
    message="Data Validation extension is not supported and will be removed"
)

# Configuración de logging
# Nota: La variable 'typing' no es necesaria aquí; basicConfig ya configura el logger raíz.
logging.basicConfig(
    format="%(asctime)s %(levelname)s: %(message)s",
    level=logging.INFO
)


def main():
    """
    Función principal para la prevalidación de cargas masivas.
    Parsea los argumentos de línea de comandos y ejecuta el proceso de validación.
    """
    parser = argparse.ArgumentParser(
        description="Prevalidador masivo de Excel con histórico y resultados"
    )
    parser.add_argument('inbox_dir',      type=Path, help='Carpeta con archivos a validar (Archivos)')
    parser.add_argument('rules_json',     type=Path, help='JSON de reglas')
    parser.add_argument('catalogs_path',  type=Path, help='Catálogos (.xlsx/.csv)')
    parser.add_argument('historico_dir',  type=Path, help='Carpeta para archivos procesados (Historico)')
    parser.add_argument('resultados_dir', type=Path, help='Carpeta para archivos de salida (Resultados)')
    args = parser.parse_args()

    # Asignar los argumentos parseados a variables locales para mayor claridad
    inbox_dir = args.inbox_dir
    rules_path = args.rules_json # Renombrado para coincidir con el uso interno de la función
    catalogs_path = args.catalogs_path
    historico_dir = args.historico_dir
    resultados_dir = args.resultados_dir

    logging.info(f"Ejecutando validaciones con los siguientes parámetros:")
    logging.info(f"  Directorio de entrada (Inbox): {inbox_dir}")
    logging.info(f"  Ruta de reglas: {rules_path}")
    logging.info(f"  Ruta de catálogos: {catalogs_path}")
    logging.info(f"  Directorio histórico: {historico_dir}")
    logging.info(f"  Directorio de resultados: {resultados_dir}")

    # Validar carpetas
    for folder in (inbox_dir, historico_dir, resultados_dir):
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
        if not folder.is_dir():
            logging.error(f"'{folder}' no es una carpeta válida.")
            return

    # Encontrar archivos a procesar
    files = [
        f for f in inbox_dir.glob("*.xlsx")
        if not f.stem.endswith("_validacion")
    ]
    if not files:
        logging.info(f"No se encontraron archivos .xlsx en '{inbox_dir}'.")
        return

    for input_file in files:
        logging.info(f"Procesando: {input_file.name}")
        # Ruta de salida en carpeta Resultados
        output_file = resultados_dir / f"{input_file.stem}_validacion{input_file.suffix}"

        # Ejecutar validaciones
        # Asegúrate de que ejecutar_validaciones acepte rutas como strings si es necesario
        errores = ejecutar_validaciones(
            file_path=str(input_file),
            path_rules=str(rules_path),
            catalogs_path=str(catalogs_path)
        )

        # Agrupar errores por hoja
        errores_por_hoja = {}
        for err in errores:
            errores_por_hoja.setdefault(err.sheet, []).append(err)

        # Leer todas las hojas originales
        try:
            xls = pd.read_excel(str(input_file), sheet_name=None, dtype=str)
        except Exception as e:
            logging.error(f"Error al leer '{input_file.name}': {e}")
            continue

        # Escribir archivo validado en Resultados
        try:
            with pd.ExcelWriter(str(output_file), engine="openpyxl") as writer:
                # Hojas individuales con columna 'Errores'
                for hoja, df in xls.items():
                    df_out = df.copy()
                    # Compilar errores por fila
                    records = []
                    for err in errores_por_hoja.get(hoja, []):
                        if err.row is not None:
                            idx = err.row - 2  # 1-header + cero-based
                            if 0 <= idx < len(df_out):
                                records.append({'idx': idx, 'msg': err.message})
                    if records:
                        err_df = pd.DataFrame(records)
                        agg = err_df.groupby('idx')['msg'].apply(lambda msgs: '; '.join(msgs))
                    else:
                        agg = pd.Series(dtype=str)
                    df_out['Errores'] = df_out.index.map(agg).fillna('')
                    df_out.to_excel(writer, sheet_name=hoja, index=False)

                # Hoja Resumen
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
        except Exception as e:
            logging.error(f"Error al escribir '{output_file.name}': {e}")
            continue

        logging.info(f"Salida generada: {output_file.name}")

        # Mover original a Histórico
        try:
            dest = historico_dir / input_file.name
            shutil.move(str(input_file), str(dest))
            logging.info(f"Original movido a: {dest}")
        except Exception as e:
            logging.warning(f"No pudo mover '{input_file.name}' a Historico/: {e}")

    logging.info("Proceso completado.")


if __name__ == '__main__':
    # Este bloque solo se ejecuta si el script se corre directamente (e.g., python main.py)
    # y no es estrictamente necesario para el entry point de setuptools,
    # ya que la función main() ahora maneja el parsing de argumentos.
    # Sin embargo, se puede mantener para pruebas directas del script.
    main()