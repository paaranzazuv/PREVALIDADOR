# src/prevalidador/_internals/rules_engine.py
"""
Motor de validación:
  - Carga reglas desde JSON.
  - Ejecuta validaciones de estructura y de datos por hoja.
"""
import json
from typing import List, Tuple

import pandas as pd

from ..errors import ValidationError
from .model import Rule, Condition
from .loaders import CargaCatalogos
from .structure import validar_estructura_hoja
from .validators import get_validator, ValidatorFunc


def parse_conditions(raw_conds: List[dict]) -> List[Condition]:
    """
    Transforma lista de dicts en instancias de Condition.
    """
    conditions: List[Condition] = []
    for c in raw_conds:
        columna = c.get("columna")
        for op, val in c.items():
            if op != "columna":
                conditions.append(Condition(columna=columna, operador=op, valor=val))
    return conditions


def infer_validator_and_params(raw_rule: dict) -> Tuple[str, dict]:
    """
    Determina el nombre del validador y sus parámetros según claves del JSON.
    """
    # Soporte catálogo en forma string 'archivo.xlsx:Hoja'
    if isinstance(raw_rule.get("catalogo"), str):
        archivo, hoja = raw_rule["catalogo"].split(":", 1)
        return "catalog", {"archivo": archivo, "hoja": hoja}
    
    # en infer_validator_and_params(...)
    if raw_rule.get("tipo") == "numero" or raw_rule.get("type_number") is True:
        return "type_number", {}

        # ————————— Validación de referencia a otra hoja —————————
    if raw_rule.get("referencia_hoja") and raw_rule.get("referencia_columna"):
        return "ref_sheet", {
            "sheet": raw_rule["referencia_hoja"],
            "column": raw_rule["referencia_columna"]
        }
    # ————————————————————————————————————————————————

    

     # Validación de suma agrupada antes de cualquier otro chequeo de fila
    if raw_rule.get("agrupado_por") and raw_rule.get("suma_igual_a") is not None:
        return "group_sum_equal", {
            "group_by": raw_rule["agrupado_por"],
            "target": raw_rule["suma_igual_a"]
        }


    # Reglas directas de regex
    if "regex" in raw_rule:
        return "regex", {"regex": raw_rule["regex"]}

    # Solo condiciones
    keys = set(raw_rule.keys())
    if keys <= {"condiciones", "mensaje_error"} and "condiciones" in raw_rule:
        return "condition", {}

    # Fecha con rango o formato
    if "formato" in raw_rule:
        fmt = raw_rule["formato"]
        rango = {k: raw_rule[k] for k in raw_rule if k.startswith(("mayor_", "menor_"))}
        if rango:
            params = {"formato": fmt, **rango}
            return "date_range", params
        return "date_format", {"formato": fmt}
        # Igual estricto (nuevo validador)
    if "igual_exacto" in raw_rule:
        return "igual_exacto", {"valor": raw_rule["igual_exacto"]}


    # Igual exacto (alias a regex)
    # Igual exacto (alias a regex)
    # Igual exacto (alias a regex literal)
    if "igual_a" in raw_rule:
        import re
        pattern = "^" + re.escape(str(raw_rule["igual_a"])) + "$"
        return "regex", {"regex": pattern}



    # In / not_in list
    if "in" in raw_rule:
        return "in_list", {"values": raw_rule["in"]}
    notin = raw_rule.get("not_in") or raw_rule.get("not_in_list")
    if notin:
        return "not_in_list", {"values": notin}

    # Contiene / no contiene
    if "contiene" in raw_rule:
        return "contains", {"substring": raw_rule["contiene"]}
    if "no_contiene" in raw_rule:
        return "not_contains", {"substring": raw_rule["no_contiene"]}

    # Longitud
    if "longitud_igual_a" in raw_rule:
        return "length_equal", {"length": raw_rule["longitud_igual_a"]}
    if "longitud_max" in raw_rule:
        return "length_max", {"max": raw_rule["longitud_max"]}

    # Posición
    if raw_rule.get("posicion") is not None:
        return "position", {"posicion": raw_rule["posicion"], "esperado": raw_rule.get("esperado")}

    # Vacío
    if raw_rule.get("vacia") is True:
        return "vacia", {}

    # Requerido
    if raw_rule.get("requerido"):
        return "required", {}


    # Tipo numérico
    if raw_rule.get("tipo") == "numero":
        return "type_number", {}

    # Tipo texto
    if raw_rule.get("tipo") == "texto":
        return "type_text", {}

    # Rangos numéricos
    numeric_keys = {k: raw_rule[k] for k in raw_rule if k.startswith(("mayor_", "menor_"))}
    if numeric_keys:
        return "range", numeric_keys

    # Suma de columnas
    if "suma_igual_a" in raw_rule:
        return "sum_equal", {"columns": raw_rule.get("columns", []), "target": raw_rule["suma_igual_a"]}

    # Referencia columna o hoja
    if raw_rule.get("referencia_columna"):
        return "ref_column", {"other_column": raw_rule["referencia_columna"]}
    if raw_rule.get("referencia_hoja") and raw_rule.get("referencia_columna"):
        return "ref_sheet", {"sheet": raw_rule["referencia_hoja"], "column": raw_rule["referencia_columna"]}

    # Unicidad
    if raw_rule.get("unico"):
        return "unique", {}

    raise ValueError(f"Regla no mapeable: {raw_rule}")


def load_rules(path_rules: str) -> List[Rule]:
    """
    Lee JSON de reglas y construye lista de Rule.
    Ignora claves especiales (_estructura, __max_filas, __min_filas)
    y reglas realmente globales que se procesan en validar_globales_por_hoja.
    """
    import json  # por si no está importado arriba

    with open(path_rules, encoding="utf-8") as f:
        raw = json.load(f)

    rules: List[Rule] = []

    for sheet, definitions in raw.items():
        # ✅ Validación de estructura esperada de columnas
        cols = definitions.get("_estructura")
        if cols:
            rules.append(
                Rule(
                    sheet=sheet,
                    columna="_estructura",
                    validator="estructura",
                    params={},
                    valor=cols
                )
            )

        # ✅ Reglas por columna
        for col, raw_rules in definitions.items():
            if col in ("_estructura", "__max_filas", "__min_filas"):
                continue

            rr_list = raw_rules if isinstance(raw_rules, list) else [raw_rules]
            for rr in rr_list:
                if not isinstance(rr, dict):
                    raise ValueError(f"[ERROR] En hoja {sheet}, columna {col} la regla no es un dict válido: {rr}")

                # ✅ Suma global (no agrupada) => column_sum_equal
                if "suma_igual_a" in rr and "agrupado_por" not in rr and "group_by" not in rr:
                    mensaje = rr.get("mensaje_error", f"Error {sheet}.{col}")
                    rules.append(
                        Rule(
                            sheet=sheet,
                            columna=col,
                            validator="column_sum_equal",
                            params={"target": rr.get("suma_igual_a")},
                            mensaje=mensaje,
                            conditions=parse_conditions(rr.get("condiciones", [])),
                            valor=None,
                        )
                    )
                    continue


                # ✅ Regla de suma agrupada => group_sum_equal
                if ("agrupado_por" in rr or "group_by" in rr) and ("suma_igual_a" in rr or "target" in rr):
                    group_by = rr.get("group_by") or rr.get("agrupado_por")
                    target = rr.get("target", rr.get("suma_igual_a"))
                    mensaje = rr.get("mensaje_error", f"Error {sheet}.{col}")

                    rules.append(
                        Rule(
                            sheet=sheet,
                            columna=col,
                            validator="group_sum_equal",
                            params={
                                "group_by": group_by,
                                "target": target
                            },
                            mensaje=mensaje,
                            conditions=parse_conditions(rr.get("condiciones", [])),
                            valor=None
                        )
                    )
                    continue

                # ✅ Regla de valores requeridos por grupo => group_contains_values
                if ("agrupado_por" in rr or "group_by" in rr) and ("valores_requeridos" in rr or "required_values" in rr):
                    group_by = rr.get("group_by") or rr.get("agrupado_por")
                    required_values = rr.get("required_values") or rr.get("valores_requeridos")
                    # Flags opcionales (default: requerido=True, normalizar_acentos=False)
                    requerido = rr.get("requerido", rr.get("required", True))
                    normalizar_acentos = rr.get("normalizar_acentos", rr.get("normalize_accents", False))
                    mensaje = rr.get("mensaje_error") or rr.get("message") or f"Error {sheet}.{col}"

                    rules.append(
                        Rule(
                            sheet=sheet,
                            columna=col,
                            validator="group_contains_values",
                            params={
                                "group_by": group_by,
                                "required_values": required_values,
                                "required": requerido,
                                "normalize_accents": normalizar_acentos
                            },
                            mensaje=mensaje,
                            conditions=parse_conditions(rr.get("condiciones", [])),
                            valor=None
                        )
                    )
                    continue

                # ✅ Unicidad por grupo => group_unique
                if ("agrupado_por" in rr or "group_by" in rr) and rr.get("unico"):
                    group_by = rr.get("group_by") or rr.get("agrupado_por")
                    mensaje = rr.get("mensaje_error", f"Error {sheet}.{col}")
                    rules.append(
                        Rule(
                            sheet=sheet,
                            columna=col,
                            validator="group_unique",
                            params={
                                "group_by": group_by,
                                "case_sensitive": rr.get("case_sensitive", False),
                                "as_integer": rr.get("as_integer", False),
                                "ignore_empty": rr.get("ignore_empty", True),
                            },
                            mensaje=mensaje,
                            conditions=parse_conditions(rr.get("condiciones", [])),
                            valor=None
                        )
                    )
                    continue


                # ✅ Reglas fila a fila estándar
                val_name, params = infer_validator_and_params(rr)
                mensaje = rr.get("mensaje_error", f"Error {sheet}.{col}")
                rules.append(
                    Rule(
                        sheet=sheet,
                        columna=col,
                        validator=val_name,
                        params=params,
                        mensaje=mensaje,
                        conditions=parse_conditions(rr.get("condiciones", [])),
                        valor=None
                    )
                )

    return rules



def ejecutar_validaciones(
    file_path: str,
    path_rules: str,
    catalogs_path: str = None
) -> List[ValidationError]:
    """
    Ejecuta todas las validaciones:
      - Estructura
      - Reglas por columna
    """
    rules = load_rules(path_rules)
    dfs = pd.read_excel(file_path, sheet_name=None, dtype=str)
    loader = CargaCatalogos(catalogs_path) if catalogs_path else CargaCatalogos()
    errors: List[ValidationError] = []

    # Validar por hoja
    for sheet in sorted({r.sheet for r in rules}):
        df = dfs.get(sheet)
        if df is None:
            errors.append(ValidationError(sheet, None, None, f"Hoja '{sheet}' no encontrada."))
            continue

        # Estructura
        struct_rules = [r for r in rules if r.sheet == sheet and r.validator == "estructura"]
        if struct_rules:
            err_str = validar_estructura_hoja(df, struct_rules[0].valor, sheet)
            if err_str:
                errors.extend(err_str)
                continue

        # Otras reglas
                # Otras reglas fila por fila y de dataframe
        for rule in [r for r in rules if r.sheet == sheet and r.validator != "estructura"]:
            validator: ValidatorFunc = get_validator(rule.validator)
            subset = df
            if rule.conditions:
                mask = df.apply(lambda row: all(_match_condition(row, c) for c in rule.conditions), axis=1)
                subset = df[mask]

            if rule.validator in ("unique", "group_sum_equal", "ref_sheet",
                      "column_sum_equal", "group_contains_values",
                      "group_unique"):
                errs = validator(None, None, None, rule, loaders=loader, dfs=dfs, df=df)
            else:
   

                errs = []
                for idx, row in subset.iterrows():
                    val = row.get(rule.columna)
                    new_errs = validator(val, row, idx, rule, loaders=loader, dfs=dfs, df=df)
                    for e in new_errs:
                        if e.row is None:
                            e.row = idx
                    errs.extend(new_errs)
            errors.extend(errs)

        # ✅ NUEVO: validaciones globales de hoja
        # Cargar el JSON crudo para extraer __max_filas, suma_igual_a, agrupado_por
        with open(path_rules, encoding="utf-8") as f:
            reglas_json = json.load(f)
        errores_globales = validar_globales_por_hoja(sheet, df, reglas_json)
        errors.extend(errores_globales)

    return errors


def _match_condition(row: pd.Series, condition: Condition) -> bool:
    """
    Evalúa una condición sobre la fila.
    """
    val = row.get(condition.columna)
    op, target = condition.operador, condition.valor
    from pandas import isna
    import re

    # Igual y distinto
    if op == "igual_a":
        return str(val) == str(target)
    if op in ("distinto_a", "diferente_a"):
        return str(val) != str(target)
    

    # Regex
    if op == "regex":
        return re.search(str(target), str(val or "")) is not None
    if op in ("no_regex", "not_regex"):
        return re.search(str(target), str(val or "")) is None

    # Vacia
    if op == "vacia":
        empty = isna(val) or str(val).strip() == ""
        return empty == bool(target)

    # In y not_in
    if op == "in":
        return str(val) in map(str, target)
    if op in ("not_in", "not_in_list"):
        return str(val) not in map(str, target)

    # Contains
    if op == "contiene":
        return str(target) in str(val or "")
    if op == "no_contiene":
        return str(target) not in str(val or "")

    # Referencias
    if op == "igual_a_columna":
        return str(val) == str(row.get(target))
    if op == "mayor_a_columna":
        try:
            return float(val) > float(row.get(target))
        except Exception:
            return False


    # Numérico general
    try:
        v, t = float(val), float(target)
    except Exception:
        return False
    if op == "mayor_a":
        return v > t
    if op in ("mayor_igual_a", "mayor_o_igual_a"):
        return v >= t
    if op == "menor_a":
        return v < t
    if op in ("menor_o_igual_a", "menor_igual_a"):
        return v <= t

    return False

def validar_globales_por_hoja(sheet_name, df, reglas_json):
    """
    Valida reglas globales a nivel hoja:
    - __max_filas / __min_filas
    - agrupado_por + valores_requeridos (por grupo)
    """
    errores = []
    reglas_hoja = reglas_json.get(sheet_name, {})

    # 1️⃣ __max_filas y __min_filas
    max_filas = reglas_hoja.get("__max_filas")
    min_filas = reglas_hoja.get("__min_filas")
    total_filas = len(df)

    if max_filas is not None and total_filas > max_filas:
        errores.append(ValidationError(
            sheet_name,
            None,
            None,
            f"La hoja {sheet_name} permite máximo {max_filas} filas, pero tiene {total_filas}."
        ))
    if min_filas is not None and total_filas < min_filas:
        errores.append(ValidationError(
            sheet_name,
            None,
            None,
            f"La hoja {sheet_name} requiere al menos {min_filas} filas, pero tiene {total_filas}."
        ))

    # 2️⃣ agrupado_por + valores_requeridos
    for col, reglas_columna in reglas_hoja.items():
        if col.startswith("_") or col not in df.columns:
            continue
        for regla in reglas_columna if isinstance(reglas_columna, list) else [reglas_columna]:
            if "agrupado_por" in regla and "valores_requeridos" in regla:
                agrupador = regla["agrupado_por"]
                obligatorios = set(regla["valores_requeridos"])
                if agrupador not in df.columns:
                    continue
                for group_val, grupo in df.groupby(agrupador):
                    encontrados = set(grupo[col].dropna().unique())
                    faltantes = obligatorios - encontrados
                    if faltantes:
                        errores.append(ValidationError(
                            sheet_name,
                            None,
                            col,
                            regla.get("mensaje_error",
                                f"En {sheet_name} la ficha {group_val} no tiene todos los valores requeridos. Faltan: {', '.join(faltantes)}")
                        ))

    return errores
