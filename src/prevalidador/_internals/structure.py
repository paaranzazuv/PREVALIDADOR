# src/prevalidador/_internals/structure.py

"""
Validación de la estructura de columnas de una hoja de Excel.
"""
from typing import List
import pandas as pd

from ..errors import ValidationError


def validar_estructura_hoja(
    df: pd.DataFrame,
    expected_cols: List[str],
    sheet_name: str
) -> List[ValidationError]:
    """
    Verifica que las columnas de la hoja coincidan exactamente con las esperadas:
      1) Número de columnas.
      2) Columnas faltantes.
      3) Columnas inesperadas.
      4) Desajustes de nombre o posición.

    Args:
        df: DataFrame de la hoja.
        expected_cols: Lista de nombres de columnas esperadas.
        sheet_name: Nombre de la hoja para reportar errores.

    Returns:
        Lista de ValidationError con los detalles de cada discrepancia.
    """
    errores: List[ValidationError] = []
    actual_cols = list(df.columns)

    # 1) Verificar número de columnas
    if len(actual_cols) != len(expected_cols):
        errores.append(ValidationError(
            sheet=sheet_name,
            row=None,
            col=None,
            message=(
                f"Estructura inválida: {len(actual_cols)} columnas encontradas, "
                f"se esperaban {len(expected_cols)}."
            )
        ))

    # 2) Columnas faltantes
    faltantes = [c for c in expected_cols if c not in actual_cols]
    if faltantes:
        msg = "Columnas faltantes: " + ", ".join(f"'{c}'" for c in faltantes)
        errores.append(ValidationError(
            sheet=sheet_name,
            row=None,
            col=None,
            message=msg
        ))

    # 3) Columnas inesperadas
    sobrantes = [c for c in actual_cols if c not in expected_cols]
    if sobrantes:
        msg = "Columnas inesperadas: " + ", ".join(f"'{c}'" for c in sobrantes)
        errores.append(ValidationError(
            sheet=sheet_name,
            row=None,
            col=None,
            message=msg
        ))

    # 4) Desajustes de nombre o posición
    for idx, (real, esperado) in enumerate(zip(actual_cols, expected_cols), start=1):
        if real != esperado:
            errores.append(ValidationError(
                sheet=sheet_name,
                row=None,
                col=real,
                message=f"Columna #{idx}: esperado '{esperado}', encontrado '{real}'."
            ))

    return errores
