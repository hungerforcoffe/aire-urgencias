# Segunda entrega del modelo de asociación

- **Fecha:** 2026-09-08
- **Aplica a:** `data/raw/modelo_viz/visualizaciones/`, `modelo.json` y las
  preguntas 1, 3, 4 y 5 de `analisis.html`
- **Implementada en:** `src/sitio/exportar_modelo.py`
- **Verificable con:** `python -m src.sitio.exportar_modelo --verificar`
- **Documento anterior:** [`resultados_modelo.md`](resultados_modelo.md)

## Qué llegó

Una segunda entrega de la misma persona que produjo el modelo diario: nueve CSV,
ocho SVG de referencia, un manifiesto y un README de handoff. Es la continuación
que la primera entrega dejó anunciada en su `00_README_HANDOFF.md`, sección «Qué
todavía puede cambiar o agregarse»:

> análisis por diagnóstico respiratorio; comparación territorial dentro de la
> Región Metropolitana; eventual experimento natural; posible expansión a otras
> ciudades.

Llegaron las dos primeras.

## Lo primero que se comprobó: que las dos entregas concuerden

Antes de sumar nada se contrastaron los valores que aparecen en ambas. **Coinciden
dígito a dígito**, no redondeados:

| Valor | Entrega 1 | Entrega 2 |
|---|---|---|
| RR Coyhaique | 1,004705343389609 | 1,004705343389609 |
| RR menores de 1 año | 1,0060337865538986 | 1,0060337865538986 |
| RR rezago 0 | 1,0066468544375224 | 1,0066468544375224 |
| RR ajustado completo | 1,008080497000528 | 1,008080497000528 (fila 4 de `01_modelos_ajuste`) |
| RR acumulado 0–7 | 1,019212 | 1,0192 (`02_rezagos`, fila acumulado) |

Esto es lo que permite **sumar sin revisar todo de nuevo**: la segunda entrega
amplía, no corrige. Si hubieran diferido, la pregunta previa habría sido cuál de
las dos publicar, y no se habría podido responder sin volver al cuaderno.

## Qué se publica y qué no

Se agregan cinco bloques a `modelo.json`:

| CSV | Clave | Filas | Aporte |
|---|---|---|---|
| `01_modelos_ajuste.csv` | `ajuste` | 4 | La escalera Base → Temperatura → +Humedad → +Virus |
| `04_zonas_rm.csv` | `zonas_rm` | 12 | 6 zonas de Santiago × 2 ventanas temporales |
| `06_diagnosticos.csv` | `diagnosticos` | 6 | Las seis causas respiratorias por separado |
| `07_sensibilidades.csv` | `sensibilidades` | 8 | Reemplaza al `08_` de la entrega 1 |
| `08_cobertura_rm.csv` | `cobertura_rm` | 54 | 6 zonas × 9 años de cobertura de medición |

**No se publican**, y no por olvido:

- `02_rezagos.csv` — sus ocho filas individuales son **idénticas** a
  `05_resultados_lags.csv` de la entrega 1, y su novena fila (el acumulado 0–7)
  ya viaja en `02_resultado_principal.csv` como «Asociación acumulada». No aporta
  nada; incorporarlo habría duplicado los mismos ocho puntos en el JSON.
- `03_ciudades.csv` y `05_edad.csv` — idénticos a los ya publicados.
- `00_manifest_visualizaciones.csv` — es índice de la entrega, no un resultado.
- `09_series_temporales.csv` — 9.468 filas diarias con medias móviles centradas
  de 28 días. El sitio ya publica la serie semanal en `semanal.json` y la dibuja
  `analisis.js`; la diaria no responde una pregunta nueva. Queda disponible en la
  zona cruda si el bloque «Explorar los datos» crece.
- **Los ocho SVG.** Ver más abajo.

### Por qué `07_sensibilidades` reemplaza al `08_` de la entrega 1

El nuevo trae **ocho filas contra seis**: las mismas cuatro de forma funcional de
la humedad y dos de validación SINCA, más dos de **ponderación territorial**
(modelo combinado original contra promedio equiponderado por ciudad) que no
existían.

Pierde `n_dias`, `escala` y `convergio`, y gana `etiqueta`, una versión abreviada
de `especificacion` que su autora creó explícitamente para que quepa en el eje de
un gráfico. Como el sitio dibuja `especificacion` y ninguna de las columnas
perdidas se mostraba, el cambio es una ganancia neta de dos estimaciones.

### Por qué no se publican los SVG

El sitio no tiene un solo `<img>` ni un `.svg` servido: el 100 % de sus gráficos
son cadenas de SVG construidas en JavaScript, con `viewBox` fijo y los colores
escritos como `var(--s2)`, `var(--senal)`, etc. Eso es lo que hace que el modo
oscuro funcione sin repintar nada.

Un SVG de matplotlib llega con colores literales (`#1f77b4`), sus propias
tipografías y su propio `viewBox`: en el tema oscuro quedaría un rectángulo claro
con texto negro, y no se adaptaría al ancho de la tarjeta. Los ocho se conservan
en la zona cruda como referencia de qué quiso mostrar cada figura, y los gráficos
se redibujan desde el CSV con las primitivas que ya existían (`bosque`, `curva`).

Seis de los ocho son forest plots, que es exactamente lo que `bosque()` dibuja.

## Validaciones nuevas

Las cinco de `validar()` ya cubrían los CSV nuevos (rango de RR, intervalo que
contiene a su estimación, número exacto de filas, convergencia, set de ciudades).
Se sumaron dos:

| Comprobación | Umbral | Por qué |
|---|---|---|
| `cobertura_pct` cuadra con `dias_con_mp25 / dias` | desvío ≤ 0,01 pp | Es la cifra que justifica que la ventana principal termine en 2024. Si el porcentaje no se deriva de su propio numerador, el argumento se apoya en un número inventado |
| Las dos ventanas de `zonas_rm` traen las mismas 6 zonas | exacto | Un selector que cambie de período **y** de zonas no compara nada |

## Lo que la página no puede decir

El README de la entrega repite una advertencia en cada sección, y es vinculante
para el texto del sitio:

> Diferencias descriptivas; no equivalen a una prueba formal de interacción.

Vale para las tres desagregaciones nuevas y para las que ya estaban. La página
**no puede afirmar** que la asociación sea mayor en Oriente que en Occidente, ni
en influenza que en «otras causas», ni en mayores de 65 que en lactantes. Puede
mostrar las estimaciones y decir cuáles cruzan el cero. El texto de los paneles
«Dentro de Santiago» y «Por diagnóstico respiratorio» lo dice explícitamente.

Además, `04_zonas_rm.csv` **no trae `casos` ni `n_estratos`** a propósito: son
los campos disponibles en las dos ventanas temporales, y omitirlos es lo que las
hace comparables entre sí.

## Efecto en la página

`modelo.json` pasó de 10 kB a 18,5 kB (150 filas). La página se reorganizó de dos
mitades —modelo diario arriba, exploración semanal abajo— a **siete capítulos y
un anexo**, ordenados de lo más digerible a lo más técnico:

| | Capítulo | Figuras |
|---|---|---|
| 01 | Las dos series suben juntas cada invierno | serie temporal MP2.5 + urgencias |
| 02 | Las dos siguen el calendario | climatología con temperatura |
| 03 | Casi toda la correlación era el calendario | bruto vs. anomalía, precedencia semanal |
| 04 | Con días, y descontando clima y virus | escalera de ajuste, rezagos 0–7 |
| 05 | Dónde | ciudades, zonas RM, cobertura, distancias, viento |
| 06 | En quién | edad, diagnóstico |
| 07 | Lo que no salió limpio | sensibilidades, controles negativos, placebo |
| — | Anexo | proyección (fuera del alcance declarado) |

El orden por autor obligaba a recorrer las tres ciudades dos veces, y arrancar
por el modelo dejaba lo más difícil de leer en primer lugar. Ahora la página abre
con el gráfico que cualquiera entiende —dos líneas que suben juntas— y solo
después explica por qué eso no basta. Ver
[`analisis_semanal.md`](analisis_semanal.md) y
[`figuras_sitio.md`](figuras_sitio.md).

## Pendientes

Los tres que [`resultados_modelo.md`](resultados_modelo.md) dejó abiertos siguen
abiertos: la curva de rezagos de los controles negativos, las cinco columnas sin
definir en el diccionario (`escala`, `n_estratos`, `casos`, `convergio`,
`significativo`), y probar `actividad_viral_clasica_100` como spline. Esta
entrega no los toca.
