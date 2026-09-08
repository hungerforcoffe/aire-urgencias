# Extracción y publicación del análisis semanal

- **Fecha:** 2026-09-08
- **Aplica a:** `data/interim/analisis_semanal/`, `semanal_nt.json`, y los bloques
  de `analisis.html` rotulados «Serie semanal»
- **Implementada en:** `src/procesamiento/analisis_semanal.py` (extracción) y
  `src/sitio/exportar_semanal.py` (publicación)
- **Verificable con:** `python -m src.procesamiento.analisis_semanal verificar` y
  `python -m src.sitio.exportar_semanal --verificar`

## Qué se observó

El segundo cuerpo de análisis del proyecto llegó como **seis notebooks de Colab**
y **dos informes en Markdown**, sin el handoff de CSV que sí acompañó al modelo
diario (`data/raw/modelo/00_README_HANDOFF.md`).

Al contrastar ambos formatos aparecieron **discrepancias sistemáticas**. No son
de redondeo:

| Valor | Informe `.md` | Notebook |
|---|---|---|
| Granger, Santiago, rezago 3 | p = 0,843 | p = 0,9778 |
| Granger, Talcahuano, rezago 1 | p = 0,320 | p = 0,9297 |
| Importancia del MP2.5, Coyhaique | 13,5 % | 5,3 % |
| Importancia del MP2.5, Santiago | 5,9 % | 1,6 % |
| Recall de alerta MP2.5, Santiago | 66,7 % | 0,0 % |
| Médicos de refuerzo, Santiago 2026-2030 | 115–140 | 183–247 |
| Establecimientos de Santiago georreferenciados | 121 | 122 |

La dirección de las conclusiones **no cambia** —Coyhaique es siempre la ciudad
con más señal, y el aporte del MP2.5 es siempre marginal— pero las magnitudes
sí, y en el caso de la dotación asistencial por casi el doble.

El informe se escribió sobre una corrida anterior del análisis. Los notebooks
conservan la salida de la corrida que quedó guardada.

## Regla adoptada

**La fuente son los notebooks, no el informe.** Los CSV se extraen leyendo las
salidas guardadas de las celdas, con `analisis_semanal.py extraer`, y nunca se
transcriben a mano desde las tablas del Markdown.

Cada tabla se localiza por notebook, índice de celda **y un fragmento de su
código** (`FUENTES` en el módulo). Si alguien reordena el notebook, el índice
apunta a otra celda y el ancla lo detecta en vez de extraer la tabla equivocada
en silencio.

## Por qué esa regla

Un número transcrito no se puede auditar: para saber si está bien hay que
volver a mirar el original a ojo. Uno extraído se vuelve a extraer y se compara.
Con dos documentos del mismo autor que no coinciden, publicar el equivocado
habría sido **indetectable después** — exactamente el fallo silencioso que
prohíbe la regla 5 del proyecto.

## Qué se pierde

**La fase 4 completa** (`fase4_analisis_comparativo_ciudades.ipynb`). Tiene siete
celdas de código y **ninguna con salida guardada**. Su «Matriz Maestra de
Indicadores Trienio 2022-2024» —población, MP2.5 promedio y percentil 95,
semanas sobre norma, razón invierno/verano, tasas de urgencia— solo existe en el
informe `.md`, que ya se sabe desincronizado, y sin respaldo ejecutable.

No se publica. Buena parte de esas cifras son derivables de
`analitico_ciudad_semana`, pero calcularlas acá las convertiría en un análisis
nuevo del equipo del sitio, no en la publicación del análisis de su autor.

**La correlación cruzada (CCF).** La celda que la produce solo guarda la figura,
sin tabla. Se podría recalcular replicando su código sobre
`analitico_ciudad_semana`, pero sería un recálculo y no una extracción. El panel
«Lo que se lleva el invierno», que publica los coeficientes crudos y ajustados
del modelo multivariado, transmite el mismo hallazgo con dato extraído.

## Decisiones de tratamiento

### La ablación se publica completa, no resumida

El pivote original tiene cuatro algoritmos por configuración, con huecos. La
tentación es quedarse con el mejor modelo de cada configuración, que es lo que
hace el informe. **No sirve para medir el aporte del MP2.5**: en Coyhaique el
mejor de la configuración A es un Ridge (R² 0,860) y el de la C un Random Forest
(0,820), así que la comparación diría que sumar MP2.5 *empeora* el modelo cuando
lo que cambió fue el algoritmo.

Se publican las 30 filas ajustadas (ciudad × configuración × modelo) y el sitio
compara **a modelo fijo**. Con esa comparación el aporte del MP2.5 es de entre
−0,050 y +0,019 de R², y el máximo está en Coyhaique.

### `NaN` se convierte en nulo, no en `float('nan')`

En el pivote de la ablación un `NaN` marca una combinación que no se ajustó.
Dejarlo como `float('nan')` hacía que `max()` devolviera resultados arbitrarios
sin fallar. Se convierte a `None` y esas filas se descartan.

### El lenguaje se reescribe

El material de origen titula su fase 3 «Modelado Estadístico y Pruebas de
Causalidad» y llama al test de Granger «test de causalidad». Es la nomenclatura
convencional del test, pero la regla 1 del proyecto prohíbe ese lenguaje en
cualquier texto. En el sitio se nombra **prueba de precedencia temporal**, que
además es lo que el test mide: si el pasado de una serie mejora la predicción de
otra.

Reemplazos aplicados:

| En el informe | En el sitio |
|---|---|
| Pruebas de Causalidad | Estacionariedad y precedencia temporal |
| Test de Causalidad de Granger | Prueba de precedencia temporal de Granger |
| el humo de biomasa es un inductor directo medible de urgencias | en Coyhaique el MP2.5 de semanas previas precede a las consultas |
| el MP2.5 predice el colapso hospitalario | aporta información predictiva no redundante |

La sección 6.2 del informe (falacia ecológica, confusión concurrente, atenuación
por agregación temporal) es rigurosa y se aprovecha en la sección de límites.

## Un resultado incómodo que se publica igual

En el modelo multivariado de Coyhaique, el coeficiente del MP2.5 **cambia de
signo** al ajustar por clima e inercia: pasa de +1,548 (p = 0,0001) a −0,621
(p = 0,0088), es decir sigue siendo distinto de cero pero ahora negativo.

Su autor no lo interpreta. La página lo publica y lo señala como indicio de que
el modelo semanal está mal especificado a esa resolución, no como hallazgo.
Esconderlo dejaría una tabla más limpia y una página menos honesta.

## Lo que este análisis no comparte con el modelo diario

**No comparte unidad.** Allá todo es un RR por +10 µg/m³ con su intervalo; acá
hay p-valores, coeficientes de regresión, R², correlaciones y kilómetros. Por eso
viven en JSON distintos y los paneles llevan un rótulo de origen visible: dos
diseños en la misma página, sin decir cuál produjo cada número, obligan al lector
a suponerlo.

**No se contradicen.** El modelo diario encuentra asociación en Santiago; este,
a escala semanal diferenciada, no encuentra precedencia. Son preguntas distintas
a resoluciones distintas, y juntas sostienen lo que
[`resultados_modelo.md`](resultados_modelo.md) ya defendía: la resolución
temporal decide el resultado. Que dos personas lleguen ahí por caminos
independientes es el aporte principal de esta integración, y la página lo dice
en un panel propio en vez de dejar que el lector tropiece con dos números que
parecen pelearse.

## Alternativas descartadas

- **Publicar desde el informe `.md`.** Es lo más rápido y lo que el autor
  entregó redactado. Se descartó al comprobar que sus números no son los de los
  notebooks.
- **Pedirle al autor un handoff de CSV como el del modelo diario.** Es lo
  correcto a futuro y sigue pendiente; no se hizo ahora porque la extracción
  desde los notebooks es reproducible y no bloquea.
- **Recalcular todo desde `analitico_ciudad_semana`.** Daría cifras verificables
  pero sería otro análisis, no la publicación de éste.

## Pendientes con quien produjo los resultados

1. **Confirmar cuál corrida es la buena.** Esta publicación asume que los
   notebooks guardados son posteriores al informe. Si fuera al revés, hay que
   re-ejecutar y volver a extraer.
2. **La fase 4 sin ejecutar.** Si se corre y se guardan las salidas, la síntesis
   cross-city entra sin cambios en el extractor.
3. **La CCF sin tabular.** Basta con guardar `ccf_bruta` y `ccf_diff` en un
   DataFrame para que se pueda extraer como las demás.
4. **El coeficiente negativo de Coyhaique** en el modelo multivariado ajustado.
