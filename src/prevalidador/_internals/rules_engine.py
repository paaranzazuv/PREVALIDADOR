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

    # Igual exacto (alias a regex)
    if "igual_a" in raw_rule:
        pattern = f"^{raw_rule['igual_a']}$"
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
    """
    with open(path_rules, encoding="utf-8") as f:
        raw = json.load(f)

    rules: List[Rule] = []
    for sheet, definitions in raw.items():
        # Estructura
        cols = definitions.get("_estructura")
        if cols:
            rules.append(Rule(sheet=sheet, columna="_estructura", validator="estructura", params={}, valor=cols))
        # Otras reglas
        for col, raw_rules in definitions.items():
            if col == "_estructura":
                continue
            rr_list = raw_rules if isinstance(raw_rules, list) else [raw_rules]
            for rr in rr_list:
                val_name, params = infer_validator_and_params(rr)
                conds = parse_conditions(rr.get("condiciones", []))
                mensaje = rr.get("mensaje_error", f"Error {sheet}.{col}")
                rules.append(
                    Rule(
                        sheet=sheet,
                        columna=col,
                        validator=val_name,
                        params=params,
                        mensaje=mensaje,
                        conditions=conds,
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
        for rule in [r for r in rules if r.sheet == sheet and r.validator != "estructura"]:
            validator: ValidatorFunc = get_validator(rule.validator)
            subset = df
            if rule.conditions:
                mask = df.apply(lambda row: all(_match_condition(row, c) for c in rule.conditions), axis=1)
                subset = df[mask]

            if rule.validator in ("unique", "group_sum_equal", "ref_sheet"):
                # Para validadores que operan a nivel de DataFrame completo
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

    return errors


def _match_condition(row: pd.Series, condition: Condition) -> bool:
    """
    Evalúa una condición sobre la fila.
    """
    val = row.get(condition.columna)
    op, target = condition.operador, condition.valor
    from pandas import isna

    # Igual y distinto
    if op == "igual_a":
        return str(val) == str(target)
    if op in ("distinto_a", "diferente_a"):
        return str(val) != str(target)

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
        return str(target) in str(val or '')
    if op == "no_contiene":
        return str(target) not in str(val or '')

    # Referencias
    if op == "igual_a_columna":
        return str(val) == str(row.get(target))
    if op == "mayor_a_columna":
        try:
            return float(val) > float(row.get(target))
        except:
            return False

    # Numérico general
    try:
        v, t = float(val), float(target)
    except:
        return False
    if op == "mayor_a":
        return v > t
    if op in ("mayor_igual_a", "mayor_o_igual_a"):
        return v >= t
    if op == "menor_a":
        return v < t
    if op == "menor_o_igual_a":
        return v <= t
    return False
