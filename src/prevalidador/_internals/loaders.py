# src/prevalidador/_internals/loaders.py

"""
Carga de catálogos externos (XLSX o CSV) con caching para optimizar accesos.
Soporta:
  - Modo single-file: precarga TODAS las hojas de un único Excel (.xlsx/.xlsm/.xls).
  - Modo carpeta: carga archivo a archivo (.xlsx/.csv) en la carpeta especificada.
Devuelve siempre una lista limpia de valores (List[str]).
"""
import os
from typing import List, Dict, Tuple, Optional

import pandas as pd

from ..errors import ValidationError


class CargaCatalogos:
    """
    Clase responsable de leer y cachear listas de valores de catálogos.

    Args:
        base_path: Ruta a un archivo Excel o a una carpeta de catálogos.
    """

    def __init__(self, base_path: str = "config/catalogs"):
        self._cache: Dict[Tuple[str, str], List[str]] = {}
        self.base_path = base_path
        self._single_file = False
        self._all_sheets: Dict[str, pd.DataFrame] = {}

        if base_path and os.path.isfile(base_path):
            # Single-file: precargar todas las hojas sin header
            self._single_file = True
            self._single_file_path = base_path
            raw = pd.read_excel(
                base_path,
                sheet_name=None,
                dtype=str,
                header=None
            )
            for name, df in raw.items():
                if df.shape[1] >= 1:
                    # Renombrar la primera columna al nombre de la hoja si es único
                    if df.shape[1] == 1:
                        df.columns = [name]
                    self._all_sheets[name] = df

    def cargar_catalogo(self, archivo: str, hoja: str) -> List[str]:
        """
        Obtiene la lista de valores del catálogo especificado.

        Args:
            archivo: Nombre del archivo (modo carpeta) o ignorado en single-file.
            hoja: Nombre de la hoja en el Excel.

        Returns:
            Lista de valores (str) sin duplicados, sin NaN ni espacios.

        Raises:
            ValidationError: Si el archivo o la hoja no existen.
        """
        key = (archivo, hoja)
        if key in self._cache:
            return self._cache[key]

        # Cargar DataFrame según modo
        if self._single_file:
            df = self._all_sheets.get(hoja)
            if df is None:
                raise ValidationError(
                    sheet=None, row=None, col=None,
                    message=f"Catálogo: hoja '{hoja}' no encontrada en '{self._single_file_path}'"
                )
        else:
            path = os.path.join(self.base_path, archivo)
            if not os.path.isfile(path):
                raise ValidationError(
                    sheet=None, row=None, col=None,
                    message=f"Catálogo: archivo '{archivo}' no existe en '{self.base_path}'"
                )
            ext = os.path.splitext(path)[1].lower()
            try:
                if ext in (".xls", ".xlsx", ".xlsm"):
                    df = pd.read_excel(path, sheet_name=hoja, dtype=str)
                elif ext == ".csv":
                    df = pd.read_csv(path, dtype=str)
                else:
                    raise ValidationError(
                        sheet=None, row=None, col=None,
                        message=f"Formato de catálogo no soportado: '{ext}'"
                    )
            except Exception as e:
                raise ValidationError(
                    sheet=None, row=None, col=None,
                    message=f"Error cargando catálogo '{archivo}:{hoja}': {e}"
                )

        # Extraer valores de la primera columna
        values = df.iloc[:, 0].dropna().astype(str).str.strip().tolist()
        # Eliminar duplicados y mantener orden de aparición
        unique_vals = list(dict.fromkeys(values))

        self._cache[key] = unique_vals
        return unique_vals


def cargar_catalogo(
    archivo: str,
    hoja: str,
    base_path: Optional[str] = None
) -> List[str]:
    """
    Función helper para cargar un catálogo sin instanciar CargaCatalogos manualmente.
    """
    loader = CargaCatalogos(base_path) if base_path else CargaCatalogos()
    return loader.cargar_catalogo(archivo, hoja)
