# src/prevalidador/_internals/validators.py
"""
Definición y registro de validadores puros para el prevalidador.
Cada validador recibe:
  - value: valor de la celda a validar.
  - row: serie de pandas con la fila completa.
  - idx: índice de la fila (0-based).
  - rule: instancia de Rule con params, conditions y mensaje.
  - **kwargs: contexto extra (loaders, df, dfs).
Devuelve siempre una lista de ValidationError (vacía si la validación pasa).
"""
import re
from typing import Any, Callable, Dict, List
from datetime import datetime

import pandas as pd

from ..errors import ValidationError
from .model import Rule
from .loaders import CargaCatalogos

ValidatorFunc = Callable[..., List[ValidationError]]
_registry: Dict[str, ValidatorFunc] = {}

def register(name: str):
    """
    Decorador para registrar funciones validadoras.
    """
    def decorator(fn: ValidatorFunc):
        _registry[name] = fn
        return fn
    return decorator

def get_validator(name: str) -> ValidatorFunc:
    """
    Retorna el validador registrado por nombre.
    """
    try:
        return _registry[name]
    except KeyError:
        raise ValueError(f"No existe validador para '{name}'")

def _to_strptime_format(formato: str) -> str:
    """
    Convierte un patrón 'dd/mm/yyyy' a '%d/%m/%Y' para datetime.strptime.
    """
    return formato.replace("dd", "%d").replace("mm", "%m").replace("yyyy", "%Y")

@register("required")
def validate_required(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    if pd.isna(value) or str(value).strip() == "":
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []

@register("type_number")
def validate_type_number(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    try:
        float(value)
    except Exception:
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []

@register("type_text")
def validate_type_text(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    if not pd.isna(value) and not isinstance(value, str):
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []

@register("length_equal")
def validate_length_equal(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    length = rule.params.get('length')
    if length is not None and len(str(value or '')) != length:
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []

@register("length_max")
def validate_length_max(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    max_len = rule.params.get('max')
    if max_len is not None and len(str(value or '')) > max_len:
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []

@register("regex")
def validate_regex(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    pattern = rule.params.get('regex')
    if pattern and not re.match(pattern, str(value or '')):
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []

@register("range")
def validate_range(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    try:
        v = float(value)
    except Exception:
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    ops = {
        'mayor_a': lambda a,b: a>b,
        'mayor_o_igual_a': lambda a,b: a>=b,
        'menor_a': lambda a,b: a<b,
        'menor_o_igual_a': lambda a,b: a<=b,
    }
    for key, func in ops.items():
        if key in rule.params and not func(v, rule.params[key]):
            return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []

@register("date_format")
def validate_date_format(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    fmt = rule.params.get('formato')
    if not fmt:
        return []
    try:
        datetime.strptime(str(value).strip(), _to_strptime_format(fmt))
    except Exception:
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []

@register("date_range")
def validate_date_range(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    fmt = rule.params.get('formato')
    try:
        dt = datetime.strptime(str(value).strip(), _to_strptime_format(fmt))
    except Exception:
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    min_s = rule.params.get('mayor_o_igual_a')
    max_s = rule.params.get('menor_o_igual_a')
    if min_s and dt < datetime.strptime(min_s, _to_strptime_format(fmt)):
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    if max_s and dt > datetime.strptime(max_s, _to_strptime_format(fmt)):
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []

@register("position")
def validate_position(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    text = str(value or '')
    pos = rule.params.get('posicion')
    exp = rule.params.get('esperado')
    if pos is None or exp is None or len(text)<pos or text[pos-1]!=exp:
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []

@register("condition")
def validate_condition(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    from .rules_engine import _match_condition
    for cond in rule.conditions:
        if not _match_condition(row, cond):
            return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []

@register("catalog")
def validate_catalog(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    archivo = rule.params.get('archivo')
    hoja = rule.params.get('hoja')
    if not archivo or not hoja:
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    loader: CargaCatalogos = kwargs.get('loaders') or CargaCatalogos()
    try:
        catalog = loader.cargar_catalogo(archivo, hoja)
    except ValidationError as e:
        return [ValidationError(rule.sheet, idx, rule.columna, str(e))]
    val = str(value or '').strip()
    if val not in catalog:
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []

@register("unique")
def validate_unique(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    df: pd.DataFrame = kwargs.get('df')
    if df is None or rule.columna not in df.columns:
        return []
    dup_idx = df[df[rule.columna].duplicated(keep=False)].index
    return [ValidationError(rule.sheet, i, rule.columna, rule.mensaje) for i in dup_idx]

@register("ref_column")
def validate_ref_column(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    other = row.get(rule.params.get('other_column'))
    if str(value) != str(other):
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []


@register("not_contains")
def validate_not_contains(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    """
    Verifica que el valor no contenga la subcadena.
    Param rule.params['substring']: str
    """
    substr = rule.params.get('substring', '')
    if substr in str(value or ''):
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []

@register("in_list")
def validate_in_list(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    """
    Verifica que el valor esté dentro de la lista especificada.
    Param rule.params['values']: List[Any]
    """
    validos = rule.params.get('values', [])
    if str(value) not in [str(v) for v in validos]:
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []


@register("vacia")
def validate_vacia(value, row, idx, rule, **_):
    """
    Verifica que el valor esté vacío (NA o cadena vacía).
    """
    import pandas as pd
    if pd.notna(value) and str(value).strip() != "":
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []

@register("group_sum_equal")
def validate_group_sum_equal(_value, _row, _idx, rule, df=None, **_):
    from prevalidador.errors import ValidationError
    errors = []
    group_by = rule.params["group_by"]
    target = float(rule.params["target"])
    if df is None or group_by not in df.columns:
        return errors
    sums = df.groupby(group_by)[rule.columna].apply(
        lambda s: sum(float(v or 0) for v in s)
    )
    for key, total in sums.items():
        if total != target:
            # reporta error en todas las filas de ese grupo
            idxs = df.index[df[group_by] == key].tolist()
            for idx in idxs:
                errors.append(ValidationError(
                    rule.sheet,
                    idx ,
                    rule.columna,
                    rule.mensaje
                ))
    return errors

@register("ref_sheet")
def validate_ref_sheet(_value, _row, _idx, rule: Rule, loaders=None, dfs=None, df=None, **_):
    errors: list[ValidationError] = []
    # Hoja de referencia
    df_other = dfs.get(rule.params["sheet"], pd.DataFrame())
    col_other = rule.params["column"]
    # Si no existe la hoja o la columna, no marcamos aquí (otro validador debería cubrirlo)
    if df is None or col_other not in df_other.columns:
        return errors

    # Lista de valores válidos
    validos = df_other[col_other].astype(str).tolist()

    # Recorremos cada fila de df principal
    for idx, val in df[rule.columna].astype(str).fillna("").items():
        if val not in validos:
            # idx es el índice de pandas (0-based), +2 => fila de Excel
            errors.append(ValidationError(
                rule.sheet,
                idx ,
                rule.columna,
                rule.mensaje
            ))
    return errors



# Alias
_registry['distinto_a'] = _registry.get('not_in_list')
_registry['diferente_a'] = _registry.get('not_in_list')
_registry['mayor_igual'] = _registry.get('range')
_registry['mayor_igual_a'] = _registry.get('range')
# Alias para sinónimos
_registry['not_in_list'] = _registry.get('not_in_list')
_registry['en_lista'] = _registry.get('in_list')
