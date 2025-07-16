# tests/snippet_test_nph.py

from prevalidador._internals.rules_engine import ejecutar_validaciones

def test_reglas_nph():
    errores = ejecutar_validaciones(
        file_path="data/inbox/nph/ESTRUCTURA_NPH.xlsx",
        path_rules="src/prevalidador/config/rules/reglas_nph.json",
        catalogs_path="src/prevalidador/config/catalogs"
    )

    if not errores:
        print("✅ No se encontraron errores. Todas las reglas pasaron correctamente.")
    else:
        print(f"❌ Se encontraron {len(errores)} errores:")
        for err in errores:
            print("  -", err)

if __name__ == "__main__":
    test_reglas_nph()
