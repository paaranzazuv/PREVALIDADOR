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
# --- helper de normalización numérica ---
def _to_number_series(s: pd.Series) -> pd.Series:
    """
    Limpia y convierte series de texto a número:
    - quita espacios (incl. NBSP) y chars no numéricos
    - soporta coma como decimal y miles
    - soporta porcentajes '12.3%' -> 0.123
    """
    s = s.astype("string").str.strip()
    s = s.str.replace("\u00A0", "", regex=False).str.replace(r"\s+", "", regex=True)
    s = s.str.replace(r"[^\d\-\.,%]", "", regex=True)

    # coma decimal si NO hay punto
    coma_decimal = s.str.contains(",") & ~s.str.contains(r"\.")
    s = s.where(~coma_decimal, s.str.replace(",", ".", regex=False))
    # cualquier coma restante -> separador de miles
    s = s.str.replace(",", "", regex=False)

    pct = s.str.endswith("%")
    s = s.str.rstrip("%")

    out = pd.to_numeric(s, errors="coerce")
    out = out.where(~pct, out / 100.0)
    return out


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




@register("ref_column")
def validate_ref_column(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    other = row.get(rule.params.get('other_column'))
    if str(value) != str(other):
        return [ValidationError(rule.sheet, idx, rule.columna, rule.mensaje)]
    return []

@register("contains")
def validate_contains(value, row, idx, rule, **kwargs):
    import pandas as pd
    txt = "" if pd.isna(value) else str(value)
    sub = str(rule.params.get("substring", ""))
    # case-insensitive por defecto
    if not rule.params.get("case_sensitive", False):
        txt, sub = txt.casefold(), sub.casefold()
    if sub and sub not in txt:
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


@register("suma_columnas")
def validar_suma_columnas(value, row, idx, rule, **kwargs):
    """
    Valida que el valor de la columna actual sea igual
    a la suma de otras columnas especificadas en 'suma_columnas'.
    """
    columnas_sumar = rule.get("suma_columnas", [])
    suma = 0
    for col in columnas_sumar:
        try:
            suma += float(row.get(col, 0) or 0)
        except ValueError:
            pass  # si hay texto lo ignora
    
    if value != suma:
        return [ValidationError(
            sheet=kwargs.get("sheet_name"),
            row=idx,
            col=row.name,
            message=rule.get("mensaje_error", f"El valor {value} debe ser igual a la suma {suma}")
        )]
    return []


@register("mayor_a_columna")
def validate_mayor_a_columna(value: Any, row: pd.Series, idx: int, rule: Rule, **kwargs) -> List[ValidationError]:
    """
    Valida que el valor sea mayor que el de otra columna en la misma fila.
    Soporta números y fechas en formato dd/mm/yyyy.
    """
    col_ref = rule.params.get("mayor_a_columna")
    val_ref = row.get(col_ref)

    # Si ambos valores están vacíos, no hay validación
    if pd.isna(value) or pd.isna(val_ref):
        return []

    # Helper para parsear fechas
    def parse_fecha(v):
        try:
            return datetime.strptime(str(v).strip(), "%d/%m/%Y")
        except Exception:
            return None

    # Intentar comparar como fechas primero
    v_actual_fecha = parse_fecha(value)
    v_ref_fecha = parse_fecha(val_ref)

    if v_actual_fecha and v_ref_fecha:
        if v_actual_fecha <= v_ref_fecha:
            return [ValidationError(
                rule.sheet,
                idx,
                rule.columna,
                rule.mensaje or f"La fecha debe ser posterior a {col_ref}"
            )]
        return []

    # Si no son fechas válidas, intentar comparar como números
    try:
        v_actual_num = float(value)
        v_ref_num = float(val_ref)
        if v_actual_num <= v_ref_num:
            return [ValidationError(
                rule.sheet,
                idx,
                rule.columna,
                rule.mensaje or f"El valor debe ser mayor al de {col_ref}"
            )]
    except (ValueError, TypeError):
        return [ValidationError(
            rule.sheet,
            idx,
            rule.columna,
            rule.mensaje or f"No se puede comparar con la columna {col_ref}"
        )]

    return []

@register("group_sum_equal")
def group_sum_equal_validator(_, __, ___, rule: Rule, **kwargs) -> List[ValidationError]:
    df = kwargs.get("df")
    errores = []

    group_col = rule.params.get("group_by")
    target = rule.params.get("target")

    if df is None or group_col not in df.columns or rule.columna not in df.columns:
        return []

    try:
        df[rule.columna] = pd.to_numeric(df[rule.columna], errors="coerce")
    except Exception:
        return []

    grouped = df.groupby(group_col)
    for group_val, grupo_df in grouped:
        suma = grupo_df[rule.columna].dropna().sum()
        if suma != target:
            # Mensaje personalizado por grupo
            mensaje = rule.mensaje or f"La suma de '{rule.columna}' agrupada por '{group_col}' debe ser igual a {target}"
            mensaje = mensaje.replace(f"'{group_col}'", f"{group_val}")
            errores.append(ValidationError(
                sheet=rule.sheet,
                row=None,
                col=rule.columna,
                message=mensaje
            ))

    return errores

@register("group_contains_values")
def group_contains_values_validator(_value, _row, _idx, rule: Rule, **kwargs) -> List[ValidationError]:
    import pandas as pd

    df = kwargs.get("df")
    if df is None:
        return []

    p = rule.params or {}
    group_col = p.get("group_by") or p.get("agrupado_por")
    req_vals = p.get("required_values") or p.get("valores_requeridos")
    case_sensitive = bool(p.get("case_sensitive", False))

    # Validaciones básicas de esquema
    if (
        group_col is None
        or req_vals is None
        or rule.columna not in df.columns
        or group_col not in df.columns
        or not isinstance(req_vals, (list, tuple, set))
        or len(req_vals) == 0
    ):
        return []

    # Normalización observada (columna a validar)
    col_vals = df[rule.columna].astype("string").str.strip()
    if not case_sensitive:
        col_vals = col_vals.str.upper()

    # Normalización requerida y mapeo para mostrar con el “casing” original
    if case_sensitive:
        req_norm = [str(v).strip() for v in req_vals if pd.notna(v)]
        norm = lambda x: x
    else:
        req_norm = [str(v).strip().upper() for v in req_vals if pd.notna(v)]
        norm = lambda x: str(x).strip().upper()

    # Mapa normalizado → valor original para un mensaje más “bonito”
    display_map = {norm(v): str(v) for v in req_vals if pd.notna(v)}
    req_set = set(req_norm)

    errores: List[ValidationError] = []
    default_msg = "En 'NroFicha' falta(n) orientación(es): {faltantes}"

    # Recorremos por grupo igual que un group_* “clásico”
    for group_val, idx in df.groupby(group_col).groups.items():
        presentes = set(col_vals.iloc[idx].dropna().unique())
        faltantes_norm = sorted(req_set - presentes)
        if faltantes_norm:
            # Lista a mostrar con el formato original
            faltantes_disp = ", ".join(display_map[x] for x in faltantes_norm if x in display_map)

            # Mensaje tipo "suma 100": reemplaza 'NroFicha' → valor del grupo
            base = rule.mensaje or default_msg
            msg = (base
                   .replace(f"'{group_col}'", str(group_val))   # estilo: "En 'NroFicha' ..." → "En 12141626 ..."
                   .replace("{grupo_col}", str(group_col))
                   .replace("{grupo_val}", str(group_val))
                   .replace("{faltantes}", faltantes_disp))

            errores.append(ValidationError(
                sheet=rule.sheet,
                row=None,                 # error por grupo, no por fila
                col=rule.columna,
                message=msg
            ))

    return errores


@register("column_sum_equal")
def column_sum_equal_validator(_value, _row, _idx, rule: Rule, **kwargs):
    import pandas as pd
    df = kwargs.get("df")
    if df is None or rule.columna not in df.columns:
        return []

    p = rule.params or {}
    decimales  = int(p.get("decimales", 6))
    tol        = float(p.get("tolerancia", 1e-6))
    target     = float(p.get("target", p.get("suma_igual_a", 0)))
    porcentaje = bool(p.get("porcentaje", False))  # si quieres validar contra 100 y tus datos están en fracción

    serie = _to_number_series(df[rule.columna]).round(decimales)
    if porcentaje:
        serie = serie * 100

    total = round(serie.sum(min_count=1), decimales)

    if pd.isna(total) or abs(total - target) > tol:
        idx_row = serie.last_valid_index()
        if idx_row is None:
            idx_row = df.index[-1]
        msg = rule.mensaje or f"La suma de '{rule.columna}' debe ser {target} ±{tol}"
        return [ValidationError(rule.sheet, idx_row, rule.columna, msg)]
    return []


@register("unique")
def validate_unique(value, row, idx, rule, **kwargs):
    import pandas as pd
    df: pd.DataFrame = kwargs.get('df')
    if df is None or rule.columna not in df.columns:
        return []

    # 1) Normaliza a string y quita espacios
    s = df[rule.columna].astype("string").str.strip()

    # 2) Conviértelo a número cuando se pueda
    s_num = pd.to_numeric(s, errors="coerce")

    # 3) Si es entero exacto (p.ej. 3662476.0), represéntalo sin decimales
    s_norm = s.copy()
    int_mask = s_num.notna() & (s_num % 1 == 0)
    s_norm[int_mask] = s_num[int_mask].astype("Int64").astype("string")

    # 4) Excluye vacíos/NaN del chequeo
    valid = s_norm.notna() & (s_norm != "")

    s_for_dups = s_norm[valid]
    dup_idx = s_for_dups[s_for_dups.duplicated(keep=False)].index

    return [ValidationError(rule.sheet, i, rule.columna, rule.mensaje) for i in dup_idx]

@register("group_unique")
def group_unique_validator(_value, _row, _idx, rule: Rule, **kwargs) -> List[ValidationError]:
    import pandas as pd

    df = kwargs.get("df")
    if df is None:
        return []

    p = rule.params or {}
    group_col = p.get("group_by") or p.get("agrupado_por")
    case_sensitive = bool(p.get("case_sensitive", False))
    as_integer = bool(p.get("as_integer", False))      # normaliza 10, "10", 10.0 → "10"
    ignore_empty = bool(p.get("ignore_empty", True))   # no marca vacíos

    if group_col is None or group_col not in df.columns or rule.columna not in df.columns:
        return []

    # Serie original (para mostrar el valor tal cual)
    s_raw = df[rule.columna].astype("string")

    # Normalización base para comparar
    s = s_raw.str.strip()
    if not case_sensitive:
        s = s.str.upper()

    # Normalización numérica opcional (enteros sin .0)
    if as_integer:
        s_num = pd.to_numeric(s, errors="coerce")
        int_mask = s_num.notna() & (s_num % 1 == 0)
        s = s.copy()
        s[int_mask] = s_num[int_mask].astype("Int64").astype("string")

    # Excluir vacíos del chequeo si corresponde
    valid_mask = s.notna()
    if ignore_empty:
        valid_mask &= (s != "")

    errores: List[ValidationError] = []
    default_msg = "El valor de '{col}' debe ser único dentro de '{group_col}' {grupo_val} (repetido: {valor})"

    for grupo_val, idxs in df.groupby(group_col).groups.items():
        idxs = list(idxs)
        s_sub = s.loc[idxs]
        vmask_sub = valid_mask.loc[idxs]
        s_valid = s_sub[vmask_sub]

        # índices duplicados dentro del grupo
        dup_idx = s_valid[s_valid.duplicated(keep=False)].index
        if len(dup_idx) == 0:
            continue

        for i in dup_idx:
            valor_mostrar = s_raw.loc[i]
            base = rule.mensaje or default_msg
            msg = (base
                   .replace("{col}", str(rule.columna))
                   .replace(f"'{group_col}'", str(grupo_val))     # estilo “como suma 100”
                   .replace("{group_col}", str(group_col))
                   .replace("{grupo_col}", str(group_col))        # alias por si usas este placeholder
                   .replace("{grupo_val}", str(grupo_val))
                   .replace("{valor}", str(valor_mostrar)))
            errores.append(ValidationError(
                sheet=rule.sheet, row=i, col=rule.columna, message=msg
            ))

    return errores




# Alias
_registry['distinto_a'] = _registry.get('not_in_list')
_registry['diferente_a'] = _registry.get('not_in_list')
_registry['mayor_igual'] = _registry.get('range')
_registry['mayor_igual_a'] = _registry.get('range')
# Alias para sinónimos
_registry['not_in_list'] = _registry.get('not_in_list')
_registry['en_lista'] = _registry.get('in_list')
_registry['not_in_list'] = _registry.get('not_in_list')  # redundante
_registry['en_lista'] = _registry.get('in_list')
_registry['unico'] = _registry.get('unique')    