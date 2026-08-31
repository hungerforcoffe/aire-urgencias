# Dirección del viento: magnitud circular y centinela en San Vicente

- **Fecha:** 2026-08-26
- **Aplica a:** SINCA, parámetro `Dirección del viento`. Afecta a `dim_parametro`,
  a `agg_aire_dia` y a cualquier consulta que agregue esa variable
- **Implementada en:** el lector de SINCA (`src/procesamiento/`, pendiente) y en
  la bandera `es_circular` de `dim_parametro`
- **Origen:** comentario de revisión del modelo, 2026-08-26

## Qué se observó

### El dominio

Las 14 series de dirección del bucket están en **grados meteorológicos 0–360**,
con 0 = norte y sentido horario (90 = este, 180 = sur, 270 = oeste). Es la
convención estándar de «dirección desde la que sopla el viento». Verificado:
mínimo 0 y máximo 360 en las 14, sin excepción.

El dominio **se cierra sobre sí mismo**, y eso está en los datos, no solo en la
teoría: la estación Coyhaique registra **91 horas con `0` y 217 con `360`**, que
son la misma dirección escrita de dos maneras.

### La consecuencia

`agg_aire_dia` calculaba `valor_medio` como media aritmética para todos los
parámetros. Sobre grados eso es incorrecto:

| Horas del día | Media aritmética | Media circular |
|---|---|---|
| 350°, 10° | **180°** (viento del sur) | **0°** (viento del norte) |

El error no rompe nada. Produce un número válido, dentro de rango, que se
grafica igual de bien que uno correcto. Es el mismo tipo de falla silenciosa que
la semana MMWR (`docs/calidad/` y obstáculo 10 del modelo).

### El centinela

En **Consultorio San Vicente** hay 222 horas con dirección exactamente `0`.
Contrastadas contra la velocidad del viento de la misma estación y hora:

| | |
|---|---|
| Horas con las dos variables | 69.244 |
| Dirección = 0 | 222 |
| De esas, velocidad = `0.1` exacto | **222 (100%)** |
| Rango de fechas | 2024-05-14 a 2026-07-19, en 87 fechas |

`0.1` no es el piso del instrumento: la serie de velocidad tiene mínimo
`0.000575969` y sus valores llevan de seis a nueve cifras significativas
(`0.00522797`, `0.0065229`, `0.00793874`…). Un valor redondo repetido exactamente
222 veces, en coincidencia perfecta con un cero en otra columna, y apareciendo de
golpe en mayo de 2024, no es meteorología.

Nota: hay 245 horas con velocidad `0.1` en total, de las cuales 222 traen
dirección 0. La implicación va en un sentido: **toda dirección 0 viene con
velocidad 0.1**, no al revés.

## Regla adoptada

**1. `dim_parametro` gana la bandera `es_circular`.** Hoy la lleva solo
`Dirección del viento`. Temperatura, humedad, velocidad del viento y MP2.5 son
lineales.

**2. Para parámetros circulares, `agg_aire_dia` no usa media aritmética.** Usa
media circular:

```
media = atan2( Σ sin(θ_i) , Σ cos(θ_i) )  → normalizada a [0, 360)
```

**3. `valor_max` y `valor_p95` quedan en `NULL` para parámetros circulares.** El
máximo y el percentil 95 de una dirección no significan nada: dependen de dónde
se ponga el corte del círculo.

**4. Se añade `vector_r`**, la longitud del vector resultante:

```
r = sqrt( (Σ sin θ)² + (Σ cos θ)² ) / n        r ∈ [0, 1]
```

Con `r` cerca de 1 el viento del día tuvo dirección dominante; cerca de 0, giró
y la media no representa nada. Sin ese número, una media circular sobre un día
de viento variable engaña igual que la aritmética.

**5. El par `(dirección = 0, velocidad = 0.1)` se marca como sin dato.** No entra
como medición. Afecta a 222 horas de Consultorio San Vicente, un 0,32% de su
serie.

**6. Normalización con módulo 360, no rechazo por dominio.** El valor `360` se
normaliza a `0` antes de agregar.

## Por qué no un chequeo de dominio estricto

Parque O'Higgins tiene dos horas —2018-07-10 14:00 y 15:00— con valor
`360.001`. Es ruido de coma flotante, no un error de medición. Un chequeo
`0 ≤ x ≤ 360` descartaría dos filas buenas. El lector normaliza con módulo y
solo rechaza fuera de una tolerancia amplia (`< -1` o `> 361`).

## Qué se pierde

222 horas de dirección en Consultorio San Vicente, sobre 69.244: **0,32%**.
Concentrado en 2024-2026 y en 87 fechas. La pérdida es despreciable y evita
inyectar una dirección inventada en la única estación validada de Talcahuano.

Ninguna hora de MP2.5 se pierde: la regla no toca esa variable.

## Alcance

**La rosa de vientos queda fuera de alcance** por decisión del equipo. El
archivo `Estación Nueva Libertad_Dirección del viento_datos_091022_260825.csv`
(399 bytes, 16 sectores con su frecuencia) no se usa.

Pero el archivo **sigue en la zona cruda**, que es inmutable, y cualquier ingesta
que recorra `*.csv` lo va a encontrar. El quinto chequeo de la regla 5 —la
primera columna tiene que parsear como `YYMMDD`— se mantiene, y no para
aprovechar el archivo sino para que no entre. Verificado: devuelve 0 filas
utilizables mientras los otros 80 archivos devuelven entre 8.903 y 233.591.

La serie temporal de dirección de Nueva Libertad, la de 147.647 filas, sí se
usa, y le aplican las seis reglas de arriba.

## Alternativas descartadas

- **Dejar la media aritmética y avisar en el informe.** El número queda en la
  tabla y alguien lo usa. Un agregado incorrecto no se arregla con una nota al
  pie.
- **Descomponer en seno y coseno como dos parámetros del hecho.** Correcto pero
  invasivo: duplica filas en `hecho_medicion` y obliga a recomponer en cada
  consulta. La descomposición vive dentro del cálculo del agregado, no en el
  esquema.
- **Convertir a los 16 sectores cardinales.** Pierde resolución y no resuelve el
  problema: la moda de sectores tiene el mismo defecto en el borde N.
- **Tratar dirección 0 como norte.** Es lo que hace un lector ingenuo, y en San
  Vicente mete 222 direcciones falsas.
