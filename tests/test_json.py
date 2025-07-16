import json

with open("src/prevalidador/config/rules/reglas_nph.json", encoding="utf-8") as f:
    raw = json.load(f)

print("\n[DEBUG JSON RAW] =====================")

for hoja, definiciones in raw.items():
    print(f"Hoja detectada: '{hoja}' (tipo: {type(definiciones)})")
    print(f"  Claves que ve Python: {[repr(k) for k in definiciones.keys()]}")
    print("")

print("======================================\n")
