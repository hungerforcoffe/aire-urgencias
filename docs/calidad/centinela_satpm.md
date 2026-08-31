# Centinela −999.9 en la rejilla satelital SatPM2.5

- **Fecha:** 2026-08-13
- **Aplica a:** SatPM2.5 (ACAG), variable `PM25` de los NetCDF de
  `s3://satpmdata/V6GL03/`, en toda etapa que agregue celdas
- **Implementada en:** `src/ingesta/reconocer_satpm.py`, constante `SENTINELA` y
  funciones `_validar_netcdf` y `cmd_ciudades`

## Qué se observó

La variable `PM25` **no declara `_FillValue` ni `missing_value`**. El valor de
«sin dato» —océano, principalmente— viene como **`-999.9` crudo y sin
enmascarar**.

Comprobado sobre `V6GL03.CNNPM25.SA.202307-202307.nc`:

| | |
|---|---|
| Celdas totales | 35.712.101 |
| Celdas con dato | 18.551.190 (**51,95%**) |
| Celdas centinela | 17.160.911 (48,05%) |
| `numpy.ma.count_masked` | **0** |
| Mínimo crudo del archivo | **−999,90** |

Es decir: **casi la mitad del archivo es relleno, y ninguna capa del formato lo
señala.** El atributo que debería marcarlo no existe, y numpy no enmascara nada
porque no tiene con qué.

Un `mean()` sobre una ventana costera —Talcahuano es el caso literal de este
proyecto— devuelve un número enorme y negativo sin lanzar excepción ni emitir
aviso. Sería un fallo silencioso indistinguible de una medición baja.

## Regla adoptada

**Toda lectura de `PM25` filtra `PM25 > -999` antes de cualquier agregación.**

El umbral se aplica sobre el valor crudo, no sobre una máscara, y se aplica
*antes* de promediar, contar o comparar. Ninguna función puede recibir el arreglo
sin filtrar.

Además, la cadena de validación de descarga **rechaza** un archivo si tras el
filtro no queda ninguna celda con dato: eso significaría que el recorte cayó
entero sobre relleno, y ese archivo va a la cola de errores en vez de a la zona
cruda.

## Por qué ese umbral

`-999` y no `-999.9` exacto: el dato es `float32` y la comparación por igualdad
con un decimal en coma flotante es frágil. Cualquier medición física de MP2.5 es
≥ 0, de modo que **cualquier** negativo es relleno; el corte en −999 es
deliberadamente holgado y separa sin ambigüedad. No proviene de ninguna norma: es
una convención de este equipo, derivada del valor que publica la fuente.

## Qué se pierde

Nada de interés. Las celdas descartadas son océano y bordes del recorte. Las tres
ciudades del estudio están en tierra y las tres devuelven dato:

| Ciudad | `PM25` celda, 2023-07 | Ventana 11×11 |
|---|---|---|
| Santiago | 37,94 | 36,61 – 41,61 |
| Talcahuano | 26,17 | 17,69 – 32,07 |
| Coyhaique | 81,41 | 61,08 – 85,41 |

**Atención con Talcahuano.** Es la única de las tres con costa dentro de una
ventana de radio moderado. Al ampliar el radio, parte de la ventana caerá en mar
y el conteo de celdas válidas bajará. Eso no es pérdida de dato: es que la comuna
tiene mar. Pero obliga a **reportar siempre cuántas celdas válidas entraron en
cada promedio**, porque un promedio sobre 40 celdas y otro sobre 121 no son
comparables aunque salgan parecidos.

## Alternativas descartadas

- **Declarar `_FillValue` al abrir el archivo** (`Dataset(..., mask_and_scale)`
  o asignar el atributo). Funcionaría, pero deja la corrección en el momento de
  la apertura: cualquier lectura que se salte ese paso vuelve a estar expuesta.
  Filtrar en el punto de uso es más redundante y más difícil de olvidar.
- **Reescribir los NetCDF con la máscara puesta.** Rompe la regla 3: la zona
  cruda es inmutable y se guarda tal como la publica la fuente.
- **Filtrar por `>= 0`.** Correcto en la práctica, pero borra la distinción entre
  «relleno» y «un negativo inesperado que sería un problema del dato». Con el
  corte en −999, un valor de −3 no se colaría como cero: saltaría a la vista.
