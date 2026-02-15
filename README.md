# Ecuador: Pronósticos del FMI vs Datos Reales

Análisis interactivo que compara los pronósticos macroeconómicos del FMI para Ecuador con los datos reales observados, utilizando 6 ediciones distintas de los *IMF Staff Reports* (2019–2025).

## Demo

**[Ver página interactiva en GitHub Pages](https://jp1309.github.io/imf/)**

El usuario selecciona una variable macroeconómica y puede activar/desactivar cada *vintage* de pronóstico para compararlo con la serie real.

## Variables incluidas

- PIB Real (crecimiento %)
- Balance Fiscal Global (% del PIB)
- Deuda Pública (% del PIB)
- Cuenta Corriente (% del PIB)
- Precio del Petróleo (USD/barril)
- Reservas Internacionales (USD miles de millones)

## Fuentes

Los datos provienen de la **Table 1: Ecuador: Selected Economic and Financial Indicators** de cada *Country Report*:

| Vintage | Documento | Fecha aprox. |
|---------|-----------|-------------|
| 2019 | IMF Country Report No. 19/79 | Marzo 2019 |
| 2020 | IMF Country Report No. 20/325 | Diciembre 2020 |
| 2021 | IMF Country Report No. 21/228 | Octubre 2021 |
| 2022 | IMF Country Report No. 22/378 | Noviembre 2022 |
| 2024 | IMF Country Report No. 24/357 | Diciembre 2024 |
| 2025 | IMF Country Report No. 25/341 | Diciembre 2025 |

## Metodología

La **serie de datos reales** se construye priorizando siempre el documento más reciente como fuente de los datos históricos:

1. Doc 2025 → datos 2023–2024
2. Doc 2024 → dato 2022
3. Doc 2022 → datos 2020–2021
4. Doc 2021 → datos 2018–2019
5. Doc 2019 → datos 2014–2017

Las **series de pronóstico** corresponden a las columnas marcadas como *Projections* en la Table 1 de cada documento.

## Estructura del repositorio

```
├── index.html                              # Página interactiva (GitHub Pages)
├── README.md
├── .gitignore
├── data/
│   ├── 1ecuea2019001.pdf                   # CR 19/79
│   ├── 1ecuea2020003.pdf                   # CR 20/325
│   ├── 1ecuea2021001.pdf                   # CR 21/228
│   ├── 1ecuea2022002.pdf                   # CR 22/378
│   ├── 1ecuea2024002.pdf                   # CR 24/357
│   ├── 1ecuea2025003.pdf                   # CR 25/341
│   └── IMF_Ecuador_Real_vs_Pronosticos.xlsx  # Datos compilados
├── charts/
│   ├── IMF_Ecuador_Real_vs_Pronosticos.png # Gráfico comparativo
│   └── IMF_Ecuador_Error_Pronostico.png    # Gráfico de errores
```

## Uso local

Simplemente abre `index.html` en cualquier navegador. No requiere servidor ni dependencias — toda la data y la librería Chart.js se cargan desde CDN.

## Tecnologías

- **Chart.js 4.4.1** para visualización interactiva
- **HTML/CSS/JS** en un solo archivo (zero build step)
- Datos extraídos con `pdfplumber` y `pdf2image` (Python)

## Autor

Juan Pablo — jp1309@gmail.com

## Licencia

Los datos originales son propiedad del Fondo Monetario Internacional (IMF). Este repositorio es un ejercicio de análisis con fines educativos.
