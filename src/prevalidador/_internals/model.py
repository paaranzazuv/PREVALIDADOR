# src/prevalidador/_internals/model.py

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass(frozen=True)
class Condition:
    """
    Representa una condición de filtrado para aplicar una validación.

    Atributos:
      - columna: nombre de la columna sobre la que se evalúa la condición.
      - operador: tipo de comparación ('igual_a', 'distinto_a', 'vacia', etc.).
      - valor: valor contra el cual comparar.
    """
    columna: str
    operador: str
    valor: Any

@dataclass
class Rule:
    """
    Representa una regla de validación extraída del JSON.

    Atributos:
      - sheet: nombre de la hoja a la que aplica.
      - columna: nombre de la columna a validar.
      - validator: clave para buscar la función validadora en el registry.
      - params: parámetros específicos del validador (e.g. formatos, rangos).
      - mensaje: mensaje de error si falla la validación.
      - conditions: lista de Condition para filtrar filas.
      - valor: valor extra asociado a la regla (e.g. columnas esperadas para estructura).
    """
    sheet: str
    columna: str
    validator: str
    params: Dict[str, Any]
    mensaje: str = ""
    conditions: List[Condition] = field(default_factory=list)
    valor: Optional[Any] = None
