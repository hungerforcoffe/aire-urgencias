# SatPM2.5 — MP2.5 estimado por satélite (ACAG / Washington University)

**Fecha de consulta:** 13 de agosto de 2026
**Reconocido con:** `src/ingesta/reconocer_satpm.py`
**Estado:** cerrado para el uso previsto (marco espacial y contraste). No se ha
descargado la serie completa.

## 0. Qué es y qué papel tiene

Estimación de MP2.5 en superficie derivada de profundidad óptica de aerosoles
(MODIS, MISR, SeaWiFS, VIIRS), combinada con el modelo de transporte GEOS-Chem y
calibrada con una red neuronal convolucional contra monitores en tierra.
Producida por el Atmospheric Composition Analysis Group.

**Su papel aquí es espacial, no temporal.** La resolución es mensual, de modo que
no puede ser la variable de exposición de un análisis con rezagos de 0 a 2
semanas. Lo que aporta:

1. MP2.5 sobre el área poblada de Talcahuano sin depender de la única estación
   con datos validados (ver `hallazgos.md:801-807`).
2. Un contraste independiente contra SINCA.
3. El marco internacional, en un CSV de 0,6 MB en vez de los 16,2 millones de
   objetos de OpenAQ.

## 1. Acceso

```
s3://satpmdata/     us-west-2     público, sin credenciales
```

Firma `UNSIGNED` (`Config(signature_version=UNSIGNED)`), igual que OpenAQ.
Responde **HTTP 200 sin credenciales**; el CGNAT no lo bloquea.

> **Trampa 1 — el bucket que citan las fuentes web no existe.**
> Varias páginas, incluida la ficha del Registry of Open Data, mencionan
> `s3://v6.gl.02.04`. Devuelve `NoSuchBucket`. El bueno es `satpmdata`.

## 2. Partición

```
V6GL03/
  FineResolution/   0,01° × 0,01°
  CoarseResolution/ 0,1° × 0,1°
    {GL, SA, NA, EU, AF, AS}/
      Monthly/<anio>/V6GL03.CNNPM25.<region>.<AAAAMM>-<AAAAMM>.nc
      Annual/        V6GL03.CNNPM25.<region>.<AAAA>01-<AAAA>12.nc
  RegionSummaries/  CSV por país
```

> **Trampa 2 — el árbol es asimétrico.**
> `Monthly/` reparte los archivos en subcarpetas por año; **`Annual/` los deja
> sueltos**. Construir la clave de uno por analogía con el otro devuelve
> `NoSuchKey`. Peor: listar `Monthly/` sin `Delimiter` devuelve los nombres de
> archivo y **oculta que existe el nivel `<anio>/`**, así que el patrón parece
> plano cuando no lo es.

## 3. Volumen — medido, no estimado

| Prefijo | Archivos válidos | Bytes | Descartados `._` |
|---|---|---|---|
| `FineResolution/SA/Monthly/` | **324** | 16.185.170.293 (16,19 GB) | 0 |
| `FineResolution/SA/Annual/` | **27** | 1.312.432.879 (1,31 GB) | **1** |

Cobertura: **1998-2024**, completa. 27 años × 12 = 324 meses, sin huecos.

> **Trampa 3 — restos AppleDouble de macOS.**
> El árbol contiene entradas `._V6GL03....nc` de **0 bytes**. Llevan extensión
> `.nc` y **no son NetCDF**. Están en `Annual/` y en `RegionSummaries/`, no en
> `Monthly/`. Un lector que confíe en la extensión falla o devuelve vacío en
> silencio. `reconocer_satpm.py` los descarta por nombre y los reporta aparte.

## 4. Formato y esquema

**NetCDF-4 sobre HDF5** — firma `\x89HDF\r\n\x1a\n`. No es NetCDF clásico:
`scipy.io.netcdf_file` no sirve. Se añadió `netCDF4>=1.7` a las dependencias.

Archivo `SA` mensual, verificado sobre 2023-07:

| Dimensión | Tamaño |
|---|---|
| `lat` | 7.001 (de −56,995 a 13,005, paso 0,01) |
| `lon` | 5.101 (de −84,995 a −33,995, paso 0,01) |

| Variable | Tipo | Dimensiones | Unidades |
|---|---|---|---|
| `PM25` | float32 | (`lat`, `lon`) | `ug/m3` |

35.712.101 celdas por archivo.

## 5. Faltantes y centinelas

> **Trampa 4 — la más peligrosa de las cuatro.**
> `PM25` **no declara `_FillValue` ni `missing_value`**. El «sin dato» viene como
> **`-999.9` crudo y sin enmascarar**. `numpy.ma.count_masked` devuelve **0**.
>
> Consecuencia: un `mean()` ingenuo sobre una ventana que toque mar devuelve un
> número enorme y negativo **sin avisar de nada**. Es exactamente el fallo
> silencioso que la regla 5 obliga a atrapar.
>
> **Regla adoptada:** toda lectura filtra `PM25 > -999` antes de agregar.
> Implementada en `reconocer_satpm.py` (constante `SENTINELA`).

Sobre el archivo `SA` de 2023-07: **51,95%** de las celdas tienen dato
(18.551.190 de 35.712.101). El resto es océano.

## 6. Metadatos que mienten

Dos atributos no se pueden usar tal cual:

- **`SPATIALCOVERAGE = GL`** en un archivo que es el recorte `SA`. El atributo
  `history` lo delata: el archivo se cortó con `ncks -d lon,9500,14600 -d
  lat,300,7300` desde el archivo global. La región real hay que tomarla del
  nombre de la clave, no del atributo.
- **`lat` declara `axis = X` y `lon` declara `axis = Y`**, al revés de la
  convención. El orden fiable es el de las dimensiones de `PM25`: `(lat, lon)`.

## 7. Contraste contra SINCA — julio 2023

La prueba que decide si esta fuente sirve. Media horaria de SINCA (registros
validados) contra la celda satelital del mismo mes, sobre las muestras que ya
estaban en `data/raw/sinca/`.

| Ciudad | Estación | SINCA (µg/m³) | Satélite celda | Satélite 11×11 | Desvío |
|---|---|---|---|---|---|
| Santiago | D14 | 38,55 | 37,94 | 38,37 | **−1,6%** |
| Coyhaique | B04 | 98,73 | 81,41 | 77,38 | **−17,5%** |

**Interpretación.** El satélite reproduce Santiago casi exactamente y subestima
Coyhaique en un sexto. No es un defecto del dato: es lo que cabe esperar. La
celda promedia ~1,1 km, mientras que la estación mide en un punto. Donde la
fuente es difusa y de escala urbana —Santiago— ambas cosas coinciden. Donde la
fuente es intensamente local —humo de leña en el valle de Coyhaique, con mediana
horaria de 79 y máximo de 664 µg/m³ en el mes— la estación está dentro de la
pluma y la celda no.

Esto **confirma el papel espacial y descarta el temporal**: una media mensual no
puede representar una exposición cuyo interés está en los picos.

Que Santiago calce a 1,6% también es una validación indirecta de SINCA: dos
mediciones independientes, uno en tierra y otra desde órbita, coinciden.

## 8. Marco internacional

`V6GL03/RegionSummaries/GlobalPM25-V6GL03-Annual-1998-2024-wThresFrac.csv`
— 608.122 bytes, 6.642 filas, **246 países**, 1998-2024.

Columnas: MP2.5 ponderado por población, media geográfica, cobertura, población
total, y **fracción de población sobre cada umbral** (5, 10, 15, 25, 30, 35, 40,
45, 50, 55, 60 µg/m³), ya calculada.

Chile:

| Año | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|
| MP2.5 ponderado por población | 18,6 | 17,7 | **16,1** | 19,1 | 19,4 | **20,3** | 18,9 |
| % población ≥ 15 µg/m³ | 70,3 | 62,8 | 52,0 | 76,4 | 80,9 | 82,0 | 73,0 |
| % población ≥ 25 µg/m³ | 17,7 | 7,0 | 0,4 | 21,9 | 20,9 | 25,0 | 20,9 |

El mínimo de la serie cae en **2020**, el año de pandemia, que ya es variable de
control del diseño. La fracción sobre 25 µg/m³ pasa de 17,7% a 0,4% y vuelve a
21,9% en 2021. Es una comprobación externa e independiente de que el período de
pandemia hay que tratarlo explícitamente (riesgo D9, `hallazgos.md:748`).

## 9. Qué queda pendiente

1. **Descargar la serie 2018-2024** (84 meses, ~4,4 GB de los 16,19 GB del
   prefijo `SA/Monthly/`).
2. **Recortar a caja envolvente de Chile** y guardar en Parquet. Una rejilla
   0,01° sobre Chile son ~3,9 M celdas/mes; en float32, ~1,3 GB para los 84
   meses. No hace falta copiar los 16 GB al bucket propio.
3. **Contrastar las 19 estaciones**, no tres puntos aproximados. Las
   coordenadas exactas salen de `sinca_cliente.py:catalogo_region`; las de este
   documento son de referencia y están escritas a mano.
4. **Decidir si el satélite resuelve la decisión 9.2** (ámbito de Talcahuano).
   La estación 802 da 26,17 µg/m³ de celda y la ventana 11×11 va de 17,69 a
   32,07: casi el doble entre extremos. Habrá que ver si la 802 queda arriba o
   abajo de la mediana de su comuna.

## 10. Preguntas abiertas

- ¿Qué monitores de tierra usó la calibración de la CNN en Chile? Si usó SINCA,
  el contraste de §7 no es del todo independiente y hay que decirlo.
- ¿Por qué el archivo `SA` cubre hasta 13° de latitud norte, muy por encima de
  Sudamérica? Probablemente el recorte con `ncks` es generoso; no afecta, pero
  explica el peso.
- La versión `V6GL03` no coincide con la `V6.GL.02.04` que anuncia el sitio web.
  Conviene fijar la versión en el documento y no seguir la última sin avisar.
