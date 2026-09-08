# Vigilancia de virus respiratorios del ISP: recorte y publicación

- **Fecha:** 2026-09-06
- **Aplica a:** `isp_virus_semana` e `isp_virus_dia`. Es el control del confusor
  de circulación viral en el modelo; **no** toca `hecho_medicion` ni
  `hecho_urgencia`.
- **Implementada en:** `src/procesamiento/isp_virus.py`
- **Verificable con:** `python -m src.procesamiento.isp_virus verificar`

## Qué se observó

La extracción desde los informes semanales del ISP (2018-2026) llegó tabulada
desde fuera del repositorio: dos Parquet y un CSV de inventario, con **36
columnas**. De esas, 14 describen la extracción y no el fenómeno.

Dos de ellas eran un problema concreto para el catálogo:

| Columna | Qué pasaba |
|---|---|
| `ruta_pdf` | Ruta absoluta a un Google Drive personal (`/content/drive/MyDrive/…`). El proyecto no admite rutas absolutas, y menos en una tabla que consulta todo el equipo. |
| `codetecciones_reportadas`, `discrepancia_total_agentes` | Booleanos guardados como `object` de pandas. Glue infiere el tipo leyendo el Parquet: se habrían catalogado como texto, y `WHERE discrepancia = true` no habría filtrado nada. |

## Regla adoptada

**Salen 14 columnas**, ninguna del fenómeno medido:

`url_publicada`, `url_pdf`, `archivo`, `estado_descarga`, `ruta_pdf`,
`archivo_pdf`, `bytes`, `archivo_extraido`, `codetecciones_reportadas`,
`n_agentes_panel`, `suma_agentes_panel`, `diferencia_total_agentes`,
`discrepancia_total_agentes`, `observacion_fuente`.

**Se conservan dos que parecían fontanería y no lo son:**

- **`estado_fuente`** distingue por qué una semana está en nulo. Sin ella, «el
  ISP no publicó el informe» y «el informe existe pero no se pudo leer» son el
  mismo `NaN`, y eso es exactamente lo que la regla 5 no permite.
- **`panel_version`** es la razón de ser de la variable principal. El panel del
  ISP cambió tres veces en el período —`clasico_6` (203 semanas), `ampliado`
  (135), `clasico_6_sars` (100)— así que un total de virus sin más tendría un
  salto estructural en 2020, justo donde también cambia la variable de pandemia.
  `actividad_viral_clasica_100` mantiene los **mismos seis virus** comparables
  de punta a punta, y `panel_version` es lo que deja verificarlo.

**Se agrega `semana_id`** en el formato `2018-W02`, que es como `dim_tiempo` y
`analitico_ciudad_semana` nombran una semana. Con eso el cruce es una sola
clave.

Quedan **23 columnas** en la tabla semanal y 24 en la diaria (`fecha`).

## Las semanas MMWR se validaron, no se supusieron

Es el riesgo que más importaba: el DEIS numera con convención **MMWR**
(domingo a sábado) y no ISO, y un desfase de hasta seis días sería del mismo
orden que los rezagos que el estudio mide, sin romper nada visible.

Se contrastaron **las 452 semanas** contra `semana_mmwr()` de
`src/procesamiento/tiempo.py`:

```
semanas comprobadas: 452  |  discrepancias: 0
día en que arranca cada semana: dom=452
```

La comprobación quedó dentro de `validar()`, así que se repite en cada
construcción y no es un chequeo de una vez.

## Cobertura

438 de 452 semanas con dato. Las **14 sin dato quedan en `NaN`**, nunca
interpoladas ni rellenadas, y su motivo queda en `estado_fuente`:

**`pdf_catalogado_no_disponible`** — el ISP lista el informe pero el archivo no
se descarga (10):
2021-SE23, 2021-SE24, 2023-SE15, 2023-SE16, 2023-SE17, 2023-SE46, 2024-SE02,
2024-SE20, 2024-SE37, 2024-SE43.

**`sin_informe_catalogado`** — no hay informe para esa semana (4):
2018-SE27, 2018-SE32, 2018-SE37, 2020-SE22.

Sobre el panel del análisis eso son **42 filas ciudad-semana de 1.350, un 3,1 %**.
Ninguna semana del panel se queda sin fila en el ISP.

## Lo que se pierde al recortar, anotado acá

`discrepancia_total_agentes` marcaba **una sola semana de las 452**, y
`observacion_fuente` la explicaba. Como las dos columnas salen de la tabla, el
hallazgo queda escrito acá:

> **2024-SE47.** Inconsistencia interna del informe del ISP: la Tabla 2 reporta
> 1.547 virus detectados, mientras la suma de agentes y la Tabla 1 corresponden
> a 1.553. La diferencia es de 6.

Es un error del documento oficial, no de la extracción. La tabla publica el
valor de la suma de agentes.

Lo mismo con la procedencia del total: `origen_virus_detectados` **sí se
conserva** y distingue `reportado` (134 semanas), `derivado_suma_agentes` (1) y
`no_reportado` (303). Es la marca de medido contra calculado.

## Trazabilidad

**Los 438 PDF originales no se bajan** — son unos 480 MB y el equipo decidió no
incorporarlos. La zona cruda de esta fuente son los tres archivos tal como
llegaron, en `data/raw/isp/`:

```
isp_vigilancia_viral_semanal_2018_2026.parquet
isp_vigilancia_viral_diaria_2018_2026.parquet
isp_inventario_semanas_2018_2026.csv
```

El CSV **es el manifiesto**: sus 10 columnas son justamente las de descarga que
se retiraron de la tabla, con la URL de cada informe. Mientras exista, cualquier
número se puede contrastar contra su PDF de origen. Si se pierde, la extracción
deja de ser reproducible: es lo más aguas arriba que el proyecto conserva.

## Dos tablas, dos consumidores

| Tabla | Filas | Se une a | Por |
|---|---|---|---|
| `isp_virus_semana` | 452 | `analitico_ciudad_semana` | `semana_id` |
| `isp_virus_dia` | 3.164 | `panel_diario_mp25` | `fecha` |

La diaria es la misma serie repetida por día, no un dato nuevo: existe porque el
case-crossover de `src/analisis/asociacion.py` desplaza rezagos por día y
estratifica por día de la semana.

Comprobado contra Athena tras publicar:

```
cruce semanal : 450 semanas por ciudad, 436 con viralidad
cruce diario  : 48.987 filas, 47.448 con viralidad (3,1 % sin dato)
señal         : invierno 30,3 de media contra 15,6 el resto del año
```

## Lo que esta variable no puede controlar

La serie del ISP es **nacional**. Toma el mismo valor para Santiago, Talcahuano
y Coyhaique en la misma semana, así que controla la **ola viral común del país**
y no la temporada de cada ciudad. En un case-crossover estratificado por
`ciudad × año × mes × día de la semana` sigue siendo identificable —dentro de un
mes la serie varía entre sus cuatro o cinco semanas— pero conviene decirlo antes
de que lo pregunten.

Además entra al modelo como **columna lineal**: `_extras()` en `asociacion.py`
reserva el spline para la temperatura y pasa cualquier otro ajuste tal cual.
Probarla como spline es una sensibilidad pendiente.
