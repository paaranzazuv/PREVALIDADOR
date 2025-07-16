# Prevalidador de Cargas Masivas en Excel

**Prevalidador** es un sistema de prevalidación de cargas masivas de datos en Excel, desarrollado bajo principios de programación funcional y buenas prácticas de arquitectura de software. Permite:

* **Validar la estructura** de hojas de Excel contra definiciones externas.
* **Aplicar reglas de negocio** configurables en JSON.
* **Validar campos** mediante catálogos externos (XLSX/CSV).
* **Generar reportes** detallados de errores por fila y por hoja.
* **Organizar outputs** de manera clara (entradas, históricos, resultados, logs).

## Estructura del Proyecto

```
prevalidador/                # Repo raíz
├── .gitignore                # Reglas de exclusión de Git
├── README.md                 # Documentación del proyecto
├── pyproject.toml            # Configuración de build e instalación
├── config/                   # Datos de configuración
│   ├── rules/                # Archivos JSON con definiciones de reglas
│   └── catalogs/             # Hojas de catálogo (XLSX, CSV)
├── src/                      # Código fuente
│   ├── prevalidador/         # Módulo principal
│   │   ├── main.py           # Script de entrada (console_scripts)
│   │   ├── errors.py         # Definición de ValidationError
│   │   └── _internals/       # Lógica interna
│   │       ├── rules_engine.py   # Orquestador de validaciones
│   │       ├── structure.py      # Validación de estructura de hojas
│   │       ├── validators.py     # Validadores puros registrados
│   │       ├── loaders.py        # Carga y caching de catálogos
│   │       └── model.py          # Clases Rule y Condition
│   └── tests/               # Test unitarios (pytest)
└── deploy/                   # Scripts de despliegue y ZIP de producción
    ├── run_validador.bat     # Script para clonar, instalar, ejecutar y loguear
    └── validador.zip         # ZIP con carpetas Archivos, Historico, Resultados, Logs
```

## Instalación

```bash
# Clonar el repositorio
git clone https://github.com/tu_usuario/prevalidador.git
cd prevalidador

# Crear y activar entorno virtual
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows
.venv\Scripts\activate

# Instalar el paquete
pip install --upgrade pip
pip install -e .
```

## Uso

### Línea de comandos

Después de la instalación, dispones del comando `prevalidar`:

```bash
prevalidar <Archivos> <rules.json> <catalogs_path> <Historico> <Resultados>
```

* `<Archivos>`: Carpeta con archivos `.xlsx` a validar.
* `<rules.json>`: Archivo con reglas de negocio en formato JSON.
* `<catalogs_path>`: Carpeta o archivo con catálogos (`.xlsx`/`.csv`).
* `<Historico>`: Carpeta donde se mueven los archivos ya procesados.
* `<Resultados>`: Carpeta donde se escriben los archivos de validación.

### Script de despliegue (Windows)

Dentro de `deploy/run_validador.bat` encontrarás un ejemplo que:

1. Clona o actualiza el repositorio.
2. Crea/activa entorno virtual.
3. Instala el paquete.
4. Ejecuta `prevalidar` con rutas configuradas.
5. Genera logs incrementales en `Logs/`.

## Configuración de Reglas

Las reglas se definen en JSON siguiendo esta estructura:

```json
{
  "HojaNombre": {
    "_estructura": ["Col1", "Col2", "Col3"],
    "Col1": [
      { "requerido": true, "mensaje_error": "Col1 es obligatorio" },
      { "tipo": "numero", "mensaje_error": "Col1 debe ser numérico" }
    ],
    "Col2": {
      "formato": "dd/mm/yyyy",
      "mayor_o_igual_a": "01/01/2000",
      "mensaje_error": "Fecha fuera de rango"
    },
    "Col3": [
      { "catalogo": "catalogs.xlsx:Lista", "mensaje_error": "Valor no está en catálogo" }
    ]
  }
}
```

### Lista de validadores disponibles

* **Estructura y existencia**

  * `estructura`: valida que las columnas coincidan exactamente con las esperadas.
  * `required`: campo obligatorio (no vacío).
  * `vacia`: campo debe estar vacío.
  * `unique`: verifica unicidad de columna en la hoja.
* **Tipos y formato**

  * `type_number`: valor convertible a número.
  * `type_text`: valor de tipo texto.
  * `regex`: expresión regular.
* **Fechas y rangos**

  * `date_format`: valida formato de fecha `dd/mm/yyyy`.
  * `date_range`: valida fecha dentro de un rango.
  * `range`: verifica rango numérico (mayor\_a, menor\_o\_igual\_a, etc.).
* **Listas y catálogos**

  * `in_list`: valor dentro de lista predefinida.
  * `not_in_list`: valor no debe estar en lista.
  * `catalog`: valor debe existir en catálogo externo (hoja Excel/CSV).
* **Contenido de texto**

  * `contains`: texto contiene substring.
  * `not_contains`: texto no contiene substring.
* **Referencias entre hojas**

  * `ref_column`: valor igual a otra columna en la misma fila.
  * `ref_sheet`: valor existe en otra hoja y columna.
* **Agregaciones**

  * `sum_equal`: suma de columnas en la misma fila igual a un target.
  * `group_sum_equal`: suma de columna agrupada por otra debe igualar target.

## Ejemplos Avanzados de Configuración

A continuación algunos ejemplos más complejos de definición de reglas en JSON:

### 1. Condiciones encadenadas

Validar solo cuando se cumplan varias condiciones simultáneas.

```json
"HojaVentas": {
  "PrecioFinal": [
    {
      "condiciones": [
        { "columna": "TipoCliente", "igual_a": "Premium" },
        { "columna": "Cantidad", "mayor_o_igual_a": 10 }
      ],
      "range": { "menor_o_igual_a": 1000 },
      "mensaje_error": "Para clientes Premium con 10+ unidades, PrecioFinal debe ser ≤ 1000"
    }
  ]
}
```

### 2. Referencias entre hojas

Validar que un valor exista en otra hoja y columna.

```json
"Construcciones": {
  "NroFicha": [
    {
      "referencia_hoja": "Fichas",
      "referencia_columna": "NroFicha",
      "mensaje_error": "El valor de NroFicha en Construcciones debe existir en Fichas"
    }
  ]
}
```

### 3. Reglas agrupadas (sumas por grupo)

Validar que la suma de un campo agrupada por otro sea igual a un target.

```json
"Derechos": {
  "Monto": [
    {
      "agrupado_por": "NroFicha",
      "suma_igual_a": 100,
      "mensaje_error": "La suma total de 'Monto' por NroFicha debe ser 100"
    }
  ]
}
```

### 4. Ejemplo mixto

Combinando múltiples tipos de validación en la misma hoja:

```json
"Usuarios": {
  "_estructura": ["ID","Email","FechaReg","Rol","Acceso"],
  "Email": [
    { "regex": "^[^@]+@[^@]+\.[a-zA-Z]{2,}$", "mensaje_error": "Email inválido" }
  ],
  "FechaReg": [
    { "formato": "dd/mm/yyyy", "mensaje_error": "Formato de fecha incorrecto" },
    { "mayor_o_igual_a": "01/01/2020", "menor_o_igual_a": "31/12/2025", "mensaje_error": "Fecha fuera de rango" }
  ],
  "Rol": [
    { "in": ["Admin", "Editor", "Viewer"], "mensaje_error": "Rol desconocido" }
  ],
  "Acceso": [
    { "condiciones": [ { "columna": "Rol", "igual_a": "Admin" } ], "required": true, "mensaje_error": "Admin debe tener un nivel de acceso" }
  ]
}
```

> **Tip**: Si planeas publicar documentación extensa o una referencia de reglas, considera usar **MkDocs** o **Sphinx** para generar un sitio web estático desde estos ejemplos.

## Arquitectura Interna

* **`rules_engine.py`**: Carga reglas, lee Excel, aplica validadores.
* **`structure.py`**: Valida estructura de columnas.
* **`validators.py`**: Define funciones puras registradas por nombre.
* **`loaders.py`**: Carga y cachea catálogos (hoja única o carpeta).
* **`model.py`**: Clases `Rule` y `Condition` con datos de validación.

## Testing

Se incluyen tests con `pytest` en `src/tests`. Para ejecutar:

```bash
pytest
```

## Contribuciones

¡Las contribuciones son bienvenidas! Abre un *issue* o *pull request* en el repositorio.

## Licencia

[MIT](LICENSE)
