# Ecuador: pronósticos del FMI frente a la historia revisada

Aplicación web y paquete reproducible de datos para comparar cómo cambiaron los pronósticos macroeconómicos del FMI para Ecuador entre siete ediciones de sus *Country Reports* (2019–2026). El proyecto separa explícitamente:

- la **historia revisada**, es decir, la estimación más reciente disponible para cada año; y
- cada **vintage de pronóstico**, preservado tal como fue publicado en su momento.

**Demo:** [jp1309.github.io/imf](https://jp1309.github.io/imf/)

> La serie histórica incluye estimaciones del FMI y puede cambiar en informes posteriores. “Real” no significa dato definitivo ni observado en tiempo real.

## Qué permite explorar

- Ocho variables: PIB real, inflación, balance fiscal del NFPS, deuda pública, cuenta corriente, precio del petróleo, PIB nominal y reservas internacionales.
- Siete vintages: Mar-2019, Dic-2020, Oct-2021, Nov-2022, Dic-2024, Dic-2025 y Abr-2026.
- Revisión del primer año proyectado entre el último y el penúltimo informe.
- Error histórico por vintage con MAE, RMSE, sesgo y tamaño de muestra.
- Descarga de la vista seleccionada en CSV, exportación del gráfico a PNG y enlace compartible mediante el estado guardado en la URL.

## Fuente, metodología y trazabilidad

La fuente primaria es la **Table 1: Ecuador: Selected Economic and Financial Indicators** de cada *IMF Country Report*. Los archivos originales están versionados en [`data/`](data/) y sus hashes SHA-256, fechas y páginas relevantes están registrados en [`data/source_manifest.json`](data/source_manifest.json).

La regla de consolidación es:

1. Cada vintage conserva únicamente las columnas publicadas como proyección en ese informe.
2. Para la historia se usa, año por año, la estimación más reciente disponible entre los informes seleccionados.
3. Cuando una Table 1 muestra una columna comparativa de un informe anterior junto a una columna corriente, la historia usa la **columna corriente**. La columna anterior permanece solo dentro de su vintage original.
4. Los valores de 2023–2025 y el horizonte Abr-2026 se verifican directamente contra la Table 1 del IMF Country Report No. 26/84.

Esta distinción evita evaluar un pronóstico contra una cifra antigua que el propio FMI ya revisó.

### Informes incorporados

| Vintage | Informe | Publicación | Archivo |
|---|---|---:|---|
| Mar-2019 | IMF Country Report No. 19/79 | 2019-03 | `1ecuea2019001.pdf` |
| Dic-2020 | IMF Country Report No. 20/325 | 2020-12 | `1ecuea2020003.pdf` |
| Oct-2021 | IMF Country Report No. 21/228 | 2021-10 | `1ecuea2021001.pdf` |
| Nov-2022 | IMF Country Report No. 22/378 | 2022-11 | `1ecuea2022002.pdf` |
| Dic-2024 | IMF Country Report No. 24/357 | 2024-12 | `1ecuea2024002.pdf` |
| Dic-2025 | IMF Country Report No. 25/341 | 2025-12 | `1ecuea2025003.pdf` |
| Abr-2026 | IMF Country Report No. 26/84 | 2026-04 | `1ecuea2026001.pdf` |

## Ejecución local

Requiere Python 3.10 o superior.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts\validate_data.py
python -m http.server 8000
```

Abre `http://localhost:8000`. El servidor local es necesario porque el navegador carga `forecasts.json` y `data/source_manifest.json` mediante `fetch`.

Para regenerar el informe PDF y sus gráficos:

```powershell
python generate_pdf.py
```

El generador ejecuta primero la validación estricta y solo después escribe:

- `IMF_Ecuador_Vintages.pdf`
- `charts/IMF_Ecuador_Real_vs_Pronosticos.png`
- `charts/IMF_Ecuador_Error_Pronostico.png`

## Actualización de datos

1. Descarga el nuevo Country Report oficial a `data/`.
2. Calcula su SHA-256 e incorpora el documento a `data/source_manifest.json`.
3. Añade el vintage y, cuando corresponda, actualiza la historia revisada en `forecasts.json`.
4. Ejecuta `python scripts\validate_data.py`. La validación comprueba esquema, años, variables, tipos, continuidad, hashes y la Table 1 del informe más reciente.
5. Regenera los artefactos con `python generate_pdf.py` y actualiza el libro Excel desde la misma fuente canónica.
6. Ejecuta las pruebas y revisa visualmente la web, el Excel y todas las páginas del PDF antes de publicar.

Si la validación falla, no publiques: corrige primero el manifiesto o la transcripción. Para recuperar una versión estable, restaura conjuntamente `forecasts.json`, `data/source_manifest.json` y los artefactos generados desde un mismo commit; mezclar versiones rompe la trazabilidad.

## Arquitectura

```text
Country Reports PDF
        │
        ├── data/source_manifest.json  (identidad, fecha, hash, página)
        └── forecasts.json             (fuente canónica estructurada)
                    │
          ┌─────────┼──────────┐
          │         │          │
       app.js  generate_pdf.py Excel publicado
          │         │
     index.html  PDF + PNG
     styles.css
```

- [`forecasts.json`](forecasts.json): única fuente de valores consumida por la aplicación y los generadores.
- [`index.html`](index.html): estructura semántica y accesible.
- [`styles.css`](styles.css): sistema visual y diseño adaptable.
- [`app.js`](app.js): estado, métricas, tablas, gráficos y exportaciones; no contiene valores macroeconómicos incrustados.
- [`scripts/validate_data.py`](scripts/validate_data.py): contrato automatizado de calidad y cotejo con la fuente primaria.
- [`generate_pdf.py`](generate_pdf.py): informe estático reproducible.

GitHub Pages publica directamente la raíz de la rama `main`; no existe un paso de compilación de frontend.

## Diccionario de datos

### `forecasts.json`

| Campo | Tipo | Descripción |
|---|---|---|
| `meta` | objeto | Versión de esquema, cobertura, metodología y metadatos por variable. |
| `actual` | objeto | Serie histórica/estimada revisada: variable → año → valor. |
| `vintages` | objeto | Edición del informe → metadatos → variable → año → pronóstico. |
| `projStart` | entero | Primer año que el informe identifica como proyección. |
| `color` | texto | Color hexadecimal estable usado por la interfaz. |

Los nombres de variables son claves estables. La unidad y los decimales de presentación viven en `meta.variables`; no deben inferirse del nombre.

### Métricas de error

Para los años en los que ya existe una estimación histórica revisada:

- **Error:** pronóstico − histórico/estimado.
- **MAE:** promedio del error absoluto.
- **RMSE:** raíz del promedio de los errores al cuadrado.
- **Sesgo:** promedio del error con signo; positivo implica sobreestimación.

Estas métricas evalúan vintages con distinto número de observaciones, por lo que siempre se muestra `N`.

## Control de calidad

```powershell
python scripts\validate_data.py
python -m unittest discover -s tests -v
node --check app.js
git diff --check
```

La revisión de publicación debe confirmar además: ausencia de errores de consola, navegación por teclado, diseño móvil sin desplazamiento horizontal, exportaciones funcionales, cero errores de fórmula en Excel y render correcto de todas las páginas del PDF.

## Licencia y atribución

El código del proyecto se distribuye bajo la [Licencia MIT](LICENSE). Los documentos y datos originales pertenecen al Fondo Monetario Internacional y conservan sus propios términos de uso. Este repositorio no está afiliado ni respaldado por el FMI.

Autor: Juan Pablo — jp1309@gmail.com
