import json
import pandas as pd
import pytest
from pathlib import Path

def extract_catalog_sheets_from_rules(rules: dict) -> set[str]:
    """
    Recorre recursivamente el JSON de reglas y extrae todos los nombres de hojas referenciadas en la clave 'catalogo'.
    """
    catalog_refs = set()
    def _extract(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == 'catalogo' and isinstance(v, str):
                    try:
                        _, sheet = v.split(':', 1)
                        catalog_refs.add(sheet)
                    except ValueError:
                        pass
                else:
                    _extract(v)
        elif isinstance(obj, list):
            for item in obj:
                _extract(item)
    _extract(rules)
    return catalog_refs


def test_catalog_sheets_exist():
    # Ajustar rutas según estructura del proyecto
    base = Path(__file__).parent
    rules_path = base / 'src' / 'prevalidador' / 'config' / 'rules' / 'reglas_nph.json'
    catalogs_path = base / 'src' / 'prevalidador' / 'config' / 'catalogs' / 'catalog_nph.xlsx'

    # Verificar que existen los archivos
    assert rules_path.exists(), f"No se encontró el archivo de reglas en: {rules_path}"
    assert catalogs_path.exists(), f"No se encontró el catálogo en: {catalogs_path}"

    # Cargar reglas
    with open(rules_path, 'r', encoding='utf-8') as f:
        reglas = json.load(f)

    # Extraer referencias de hojas desde el JSON
    catalog_refs = extract_catalog_sheets_from_rules(reglas)

    # Leer hojas disponibles en el Excel de catálogo
    xl = pd.ExcelFile(str(catalogs_path))
    available_sheets = set(xl.sheet_names)

    # Comparar y reportar faltantes
    missing = catalog_refs - available_sheets
    assert not missing, f"Hojas faltantes en el catálogo: {', '.join(sorted(missing))}"
