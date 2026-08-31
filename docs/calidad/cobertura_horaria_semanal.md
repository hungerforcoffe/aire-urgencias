# Cobertura mínima para que una semana entre en el análisis

- **Fecha:** 2026-08-27
- **Aplica a:** SINCA horario (MP2.5, temperatura, humedad, velocidad del
  viento) al agregarse a `analitico_ciudad_semana`
- **Implementada en:** `src/procesamiento/analitico.py`, constantes
  `HORAS_MINIMAS_DIA` y `DIAS_MINIMOS_SEMANA`, función `_agregar_parametro`
- **Decidida por:** criterio estándar de calidad del aire (75 %), verificado
  contra el efecto real que tiene sobre estos datos

## La regla

Tres escalones, y en cada uno se descarta **antes** de promediar:

| Escalón | Umbral | Por qué |
|---|---|---|
| hora → **día de estación** | ≥ **18 de 24 horas** (75 %) | un día con seis horas no representa el día; si además esas horas caen de madrugada, el promedio queda sesgado hacia el mínimo |
| día → **semana de estación** | ≥ **5 de 7 días** válidos (71 %) | una semana de dos días no describe la semana, y la exposición del estudio es semanal |
| semana de estación → **semana de ciudad** | ≥ **1 estación** válida | la ciudad se representa con las estaciones que cumplieron; ninguna, no hay dato |

El orden importa. Promediar primero y filtrar después dejaría entrar un día de
tres horas con el mismo peso que uno completo.

## Qué descarta de verdad

Medido sobre las 450 semanas epidemiológicas completas de la ventana
(2018-W02 → 2026-W33) y las tres ciudades:

| | estación-día | estación-semana | ciudad-semana con dato |
|---|---|---|---|
| **MP2.5** | 45.351 de 46.048 (**98,5 %**) | 6.504 de 6.632 (98,1 %) | **1.350 de 1.350** |
| **Temperatura** | 28.399 de 28.708 (98,9 %) | 4.060 de 4.137 (98,1 %) | 1.292 de 1.350 |

**El umbral no cuesta ni una semana de MP2.5.** Las 1.350 filas ciudad-semana
tienen exposición: 450 en cada ciudad, con un mínimo de 6 días válidos y de 2
estaciones (Coyhaique) en la peor semana. Eso es lo que se quería saber antes de
fijarlo: un umbral que descartara semanas enteras de la variable de exposición
habría que discutirlo; este no descarta ninguna.

En temperatura el umbral sí muerde, pero poco: **58 semanas-ciudad sin dato
frente a 49 sin aplicar ningún umbral.** Las 9 semanas adicionales son semanas
que tenían medición pero no la suficiente, y aceptarlas habría significado
describir una semana con menos de cinco días.

## Dónde caen las 58 semanas sin temperatura

| Ciudad | Semanas | En invierno | Rango |
|---|---|---|---|
| Santiago | 21 | 12 | 2021-W46 … 2025-W34 |
| Talcahuano | 37 | 12 | 2018-W02 … 2026-W02 |
| Coyhaique | 0 | — | — |

No es ruido repartido: el grueso de Santiago es un bloque corrido desde
**2025-W20**, cuando toda la red meteorológica de la Región Metropolitana dejó
de publicar el **8 de mayo de 2025 a las 11:00** —seis estaciones, el mismo
minuto, con el MP2.5 de esas mismas estaciones sin interrumpirse—; y el de
Talcahuano es enero-agosto de 2018, antes de que su única estación con
termómetro empezara a medir.

**Consecuencia para el análisis:** la temperatura falta en el 4,3 % de las filas
y no falta al azar. Un modelo que controle por temperatura y descarte las filas
incompletas pierde el invierno 2025 de Santiago y el 2018 de Talcahuano, que son
tramos de señal alta. La decisión de rellenar con reanálisis, descartar o
recortar la ventana **queda abierta**; esta regla solo establece qué cuenta como
dato suficiente.

## Lo que la regla no hace

No descarta por estado de validación: los tres estados de SINCA entran como
dato válido, y eso está decidido y documentado aparte en
[`estados_validacion_sinca.md`](estados_validacion_sinca.md).

No rellena huecos. Una ciudad-semana sin dato queda como fila presente con valor
nulo, nunca ausente. Si la fila desapareciera, el hueco sería invisible y una
media sobre 1.292 filas se leería como si fuera sobre 1.350.
