# Anexo · Historial de Athena: el DDL que construyó la base

- **Base de datos:** `aire_urgencias`  ·  **workgroup:** `primary`  ·  **región:** us-east-1
- **Extraído de:** el historial de consultas de Athena (652 ejecuciones registradas)
- **Generado:** 2026-09-12 19:57 con `python -m src.nube.historial ddl`

De cada objeto se anexa **la última ejecución con éxito**, que es el DDL vigente. El catálogo se reconstruyó varias veces durante el proyecto; las versiones intermedias no se incluyen porque ya no describen lo que hay en la base.

## Las tres capas

| Capa | Qué es | Dónde vive |
|---|---|---|
| **Bronce** | Los archivos tal como los entregó cada organismo | `data/raw/`, inmutable. No pasa por Athena |
| **Plata** | El modelo en estrella: hechos, dimensiones, denominador y vigilancia viral (reservada) | Parquet en S3, catalogado en Glue |
| **Oro** | La tabla analítica, ya recortada a las tres ciudades | Parquet en S3, catalogado en Glue |

Hoy la base tiene **14 tablas**: las 12 del modelo (11 de plata y 1 de oro) y 2 restos de consultas `CREATE TABLE AS SELECT` que no forman parte del modelo.

## La base de datos

### `DATABASE aire_urgencias`

Ejecutada el 2026-08-26 22:37 · 0 kB escaneados

```sql
CREATE DATABASE IF NOT EXISTS aire_urgencias COMMENT 'Modelo estrella MP2.5 x urgencias respiratorias 2018 - 2026'
LOCATION 's3://aire-urgencias-2026-pr/processed/'
```

## Capa plata · el modelo en estrella

### `hecho_medicion`

Ejecutada el 2026-09-06 03:04 · 0 kB escaneados

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS aire_urgencias.hecho_medicion (
    estacion_id int,
    ciudad_id string,
    fecha date,
    hora tinyint,
    parametro_id string,
    valor double,
    estado_validacion string )
PARTITIONED BY (anio int)
STORED AS PARQUET
LOCATION 's3://aire-urgencias-2026-pr/processed/hecho_medicion/'
TBLPROPERTIES ('parquet.compression'='SNAPPY')
```

### `hecho_urgencia`

Ejecutada el 2026-09-06 03:04 · 0 kB escaneados

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS aire_urgencias.hecho_urgencia (
    establecimiento_id string,
    fecha date,
    semana_deis tinyint,
    causa_id smallint,
    tipo_atencion string,
    tipo_campana string,
    total int,
    menores_1 int,
    de_1_a_4 int,
    de_5_a_14 int,
    de_15_a_64 int,
    de_65_y_mas int )
PARTITIONED BY (anio int)
STORED AS PARQUET
LOCATION 's3://aire-urgencias-2026-pr/processed/hecho_urgencia/'
TBLPROPERTIES ('parquet.compression'='SNAPPY')
```

### `dim_tiempo`

Ejecutada el 2026-09-06 03:04 · 0 kB escaneados

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS aire_urgencias.dim_tiempo (
    fecha date,
    anio bigint,
    mes bigint,
    dia bigint,
    dia_semana bigint,
    nombre_dia string,
    anio_epi bigint,
    semana_epi bigint,
    semana_id string,
    inicio_semana date,
    fin_semana date,
    semana_completa boolean,
    estacion_anio string,
    es_invierno boolean,
    periodo_pandemia string )
STORED AS PARQUET
LOCATION 's3://aire-urgencias-2026-pr/processed/dim_tiempo/'
TBLPROPERTIES ('parquet.compression'='SNAPPY')
```

### `dim_estacion`

Ejecutada el 2026-09-06 03:04 · 0 kB escaneados

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS aire_urgencias.dim_estacion (
    estacion_id bigint,
    nombre_sinca string,
    clave_cruce string,
    ciudad_id string,
    region string,
    comuna string,
    latitud double,
    longitud double,
    tiene_datos boolean,
    corregida boolean,
    nota string,
    primer_dato date,
    ultimo_dato date,
    horas_ventana bigint,
    horas_validadas_ventana bigint,
    pct_validado double,
    cobertura_pct double )
STORED AS PARQUET
LOCATION 's3://aire-urgencias-2026-pr/processed/dim_estacion/'
TBLPROPERTIES ('parquet.compression'='SNAPPY')
```

### `dim_ciudad`

Ejecutada el 2026-09-06 03:04 · 0 kB escaneados

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS aire_urgencias.dim_ciudad (
    ciudad_id string,
    nombre string,
    region_codigo bigint,
    region string,
    n_comunas bigint,
    comunas string,
    n_estaciones bigint,
    poblacion bigint,
    fuente_poblacion string,
    pct_lena_casen double,
    auditoria_ok boolean,
    n_estaciones_excluidas bigint,
    poblacion_anio bigint )
STORED AS PARQUET
LOCATION 's3://aire-urgencias-2026-pr/processed/dim_ciudad/'
TBLPROPERTIES ('parquet.compression'='SNAPPY')
```

### `dim_causa`

Ejecutada el 2026-09-06 03:04 · 0 kB escaneados

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS aire_urgencias.dim_causa (
    causa_id bigint,
    glosa string,
    es_agregado boolean,
    es_respiratoria_detalle boolean )
STORED AS PARQUET
LOCATION 's3://aire-urgencias-2026-pr/processed/dim_causa/'
TBLPROPERTIES ('parquet.compression'='SNAPPY')
```

### `dim_establecimiento`

Ejecutada el 2026-09-06 03:04 · 0 kB escaneados

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS aire_urgencias.dim_establecimiento (
    establecimiento_id string,
    nombre string,
    tipo string,
    region_codigo bigint,
    region string,
    comuna_codigo bigint,
    comuna string )
STORED AS PARQUET
LOCATION 's3://aire-urgencias-2026-pr/processed/dim_establecimiento/'
TBLPROPERTIES ('parquet.compression'='SNAPPY')
```

### `poblacion_comuna_anio`

Ejecutada el 2026-09-06 03:04 · 0 kB escaneados

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS aire_urgencias.poblacion_comuna_anio (
    comuna_codigo bigint,
    comuna string,
    anio bigint,
    menores_1 bigint,
    de_1_a_4 bigint,
    de_5_a_14 bigint,
    de_15_a_64 bigint,
    de_65_y_mas bigint,
    total bigint )
STORED AS PARQUET
LOCATION 's3://aire-urgencias-2026-pr/processed/poblacion_comuna_anio/'
TBLPROPERTIES ('parquet.compression'='SNAPPY')
```

### `poblacion_ciudad_anio`

Ejecutada el 2026-09-06 03:04 · 0 kB escaneados

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS aire_urgencias.poblacion_ciudad_anio (
    ciudad_id string,
    anio bigint,
    total bigint,
    menores_1 bigint,
    de_1_a_4 bigint,
    de_5_a_14 bigint,
    de_15_a_64 bigint,
    de_65_y_mas bigint )
STORED AS PARQUET
LOCATION 's3://aire-urgencias-2026-pr/processed/poblacion_ciudad_anio/'
TBLPROPERTIES ('parquet.compression'='SNAPPY')
```

### Vigilancia viral · reservada

2 tablas de la capa plata con la serie de vigilancia de virus respiratorios. La base la construyó una integrante del equipo y se publica primero en su propio repositorio, así que su DDL no se anexa hasta entonces.

## Capa oro · la tabla analítica

### `analitico_ciudad_semana`

Ejecutada el 2026-09-06 03:04 · 0 kB escaneados

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS aire_urgencias.analitico_ciudad_semana (
    ciudad_id string,
    ciudad string,
    semana_id string,
    anio_epi bigint,
    semana_epi bigint,
    inicio_semana date,
    fin_semana date,
    estacion_anio string,
    es_invierno boolean,
    periodo_pandemia string,
    mp25_media double,
    mp25_mediana double,
    mp25_max_dia double,
    mp25_media_pool double,
    mp25_media_lag1 double,
    mp25_media_lag2 double,
    mp25_estaciones bigint,
    mp25_dias bigint,
    temp_media double,
    temp_min_dia double,
    temp_estaciones double,
    humedad_media double,
    viento_media double,
    urg_resp bigint,
    urg_resp_menores_1 bigint,
    urg_resp_de_1_a_4 bigint,
    urg_resp_de_5_a_14 bigint,
    urg_resp_de_15_a_64 bigint,
    urg_resp_de_65_y_mas bigint,
    urg_ira_alta bigint,
    urg_bronquitis bigint,
    urg_influenza bigint,
    urg_neumonia bigint,
    urg_obstructiva bigint,
    urg_resp_otras bigint,
    urg_totales bigint,
    urg_diarrea bigint,
    urg_covid bigint,
    poblacion bigint,
    poblacion_menores_1 bigint,
    poblacion_de_1_a_4 bigint,
    poblacion_de_5_a_14 bigint,
    poblacion_de_15_a_64 bigint,
    poblacion_de_65_y_mas bigint,
    tasa_resp_100k double,
    tasa_menores_1_100k double,
    tasa_de_65_y_mas_100k double,
    prop_resp double,
    temp_completa boolean,
    cobertura_ok boolean )
STORED AS PARQUET
LOCATION 's3://aire-urgencias-2026-pr/processed/analitico_ciudad_semana/'
TBLPROPERTIES ('parquet.compression'='SNAPPY')
```

## Fuera del modelo

Tablas materializadas con `CREATE TABLE AS SELECT` durante el análisis. Se dejan registradas por transparencia: **no forman parte del modelo del proyecto** y su ubicación en S3 es el directorio de resultados de Athena, no la zona `processed/`.

### `hecho_medicion_temp`

_Sin DDL en el historial: la tabla se creó fuera del workgroup o el historial ya la rotó._

### `panel_diario_mp25`

Ejecutada el 2026-09-05 20:35 · 21031 kB escaneados

```sql
CREATE TABLE aire_urgencias.panel_diario_mp25 WITH (
    format = 'PARQUET',
    parquet_compression = 'SNAPPY' ) AS WITH horario AS ( SELECT estacion_id,
    ciudad_id,
    fecha,
    hora,
    max(CASE WHEN parametro_id = 'mp25' AND valor > 0 AND valor <= 1000 THEN valor END) AS mp25,
    max(CASE WHEN parametro_id = 'mp25' AND valor = 0 THEN 1 ELSE 0 END) AS mp25_cero,
    max(CASE WHEN parametro_id = 'mp25' AND estado_validacion = 'validado' THEN 1 ELSE 0 END) AS mp25_val,
    max(CASE WHEN parametro_id = 'temperatura' AND valor BETWEEN -25 AND 40 THEN valor END) AS temp,
    max(CASE WHEN parametro_id = 'vel_viento' THEN valor END) AS viento,
    max(CASE WHEN parametro_id = 'dir_viento' THEN valor END) AS dir_viento,
    max(CASE WHEN parametro_id = 'humedad' AND valor BETWEEN 0 AND 100 THEN valor END) AS humedad
FROM aire_urgencias.hecho_medicion
WHERE anio BETWEEN 2018 AND 2026 AND parametro_id IN ('mp25','temperatura','vel_viento','dir_viento','humedad')
GROUP BY 1,
    2,
    3,
    4 ),
    vectorial AS ( SELECT h.*,
    h.viento * sin(radians(h.dir_viento)) AS viento_u,
    h.viento * cos(radians(h.dir_viento)) AS viento_v
FROM horario h ) SELECT v.fecha,
    v.estacion_id,
    v.ciudad_id,
    e.nombre_sinca,
    e.comuna,
    e.region, -- MP2.5 avg(v.mp25) AS mp25_prom,
    max(v.mp25) AS mp25_max,
    count(v.mp25) AS horas_mp25,
    sum(v.mp25_cero) AS horas_mp25_cero,
    sum(v.mp25_val) AS horas_validadas, -- Meteorología avg(v.temp) AS temp_prom,
    min(v.temp) AS temp_min,
    max(v.temp) AS temp_max,
    count(v.temp) AS horas_temp,
    avg(v.viento) AS viento_prom,
    avg(v.viento_u) AS viento_u,
    avg(v.viento_v) AS viento_v,
    avg(v.humedad) AS humedad_prom,
    count(v.humedad) AS horas_humedad, -- Calendario (derivado de fecha,
    sin depender de dim_tiempo) year(v.fecha) AS anio,
    month(v.fecha) AS mes,
    day_of_week(v.fecha) AS dia_semana,
    day_of_year(v.fecha) AS dia_anio, -- Contexto del DEIS t.semana_epi,
    t.anio_epi,
    t.es_invierno,
    t.periodo_pandemia
FROM vectorial v LEFT JOIN aire_urgencias.dim_estacion e ON e.estacion_id = v.estacion_id LEFT JOIN aire_urgencias.dim_tiempo t ON t.fecha = v.fecha
GROUP BY v.fecha,
    v.estacion_id,
    v.ciudad_id,
    e.nombre_sinca,
    e.comuna,
    e.region,
    t.semana_epi,
    t.anio_epi,
    t.es_invierno,
    t.periodo_pandemia
```
