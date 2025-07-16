"""
Definición de la clase de error que encapsula los detalles de cada validación fallida.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class ValidationError(Exception):
    """
    Representa un error de validación.

    Atributos:
        sheet: Nombre de la hoja de Excel donde ocurrió el error.
        row: Número de fila en el archivo Excel (1-based). None si el error no está atado a una fila.
        col: Nombre de la columna. None si el error no está atado a una columna.
        message: Mensaje descriptivo del error.
    """
    sheet: Optional[str]
    row: Optional[int]
    col: Optional[str]
    message: str

    def __post_init__(self):
        # Inicializar Exception con el mensaje para heredar correctamente
        super().__init__(self.message)

    def __str__(self) -> str:
        parts = []
        if self.sheet:
            parts.append(f"Hoja='{self.sheet}'")
        if self.row is not None:
            parts.append(f"fila={self.row}")
        if self.col:
            parts.append(f"columna='{self.col}'")
        loc = ", ".join(parts)
        return f"{loc}: {self.message}" if loc else self.message

    def to_dict(self) -> Dict[str, Any]:
        """
        Serializa el error a un diccionario.
        """
        return {
            "sheet": self.sheet,
            "row": self.row,
            "col": self.col,
            "message": self.message,
        }
