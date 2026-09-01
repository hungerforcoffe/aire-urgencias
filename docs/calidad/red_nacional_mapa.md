# La red nacional de SINCA como capa de contexto del mapa

- **Fecha:** 2026-08-31
- **Aplica a:** `red_nacional_estacion`, `red_nacional_mes` y la capa nacional
  del mapa (`sitio/assets/datos/nacional.json`). **No aplica** a
  `hecho_medicion`, `analitico_ciudad_semana` ni a ninguna cifra del análisis.
- **Implementada en:** `src/ingesta/red_nacional.py`,
  `src/procesamiento/red_nacional.py`, `src/sitio/exportar_nacional.py`
- **Verificable con:** `python -m src.procesamiento.red_nacional verificar` y
  `python -m src.sitio.exportar_nacional --verificar`

## Qué se observó

El mapa del sitio mostraba 16 estaciones sobre un mapa de Chile. Un mapa así no
dice «el estudio son tres ciudades»: dice «en el resto del país no hay
medición», que es falso.

El catálogo de SINCA, recorrido región por región el 2026-08-31, tiene
**213 estaciones en las 16 regiones, y 111 declaran medir MP2.5**. De esas 111:

| | estaciones |
|---|---|
| declaran MP2.5 en el catálogo | 111 |
| con coordenada en su ficha | 111 |
| con serie utilizable 2018-2026 | 101 |
| rechazadas por venir sin ningún valor | 10 |
| ya presentes en el estudio (cruce por coordenada) | 17 |
| **nuevas en el mapa** | **84** |

Las 10 rechazadas devuelven **HTTP 200 y 3.163 filas**, una por día del período,
**todas vacías**: Los Andes, Quilpué, Cerrillos I, Quilicura I, El Boldo,
Libertad, Meteorológica de Chiguayante, Museo Ferroviario, CESFAM Lago Ranco y
Entre Lagos. Declaran el parámetro y no publican dato en la ventana. Es la
regla 5 del proyecto: la descarga «funcionó» y no traía nada. Van a
`data/raw/sinca/nacional/_rechazadas.json`, no a la zona cruda.

## Regla adoptada

1. **La serie nacional se pide agregada a día**, con el macro `diario.diario` de
   Airviro, y **no entra a `hecho_medicion`**. Vive en tablas propias.
2. **Un mes se muestra si tiene 20 o más días con dato.** Los que no llegan
   quedan en el Parquet marcados `suficiente = false` y no se exportan al sitio.
3. **Dos estaciones a 300 m o menos son la misma estación.** Las que coinciden
   con una del estudio se marcan `en_estudio = true` y **no** se exportan a la
   capa nacional.
4. **Una coordenada fuera de Chile se descarta**, no se corrige ni se sustituye
   por la de la comuna.

## Por qué esos umbrales

**Por qué diario y no horario.** Con resolución horaria son ~75.000 filas por
estación y varios GB para las 111; con diaria son 3.164 filas y 56 kB por
estación, unos 6 MB en total. El mapa muestra medias mensuales: la hora no
aporta nada que el mes vaya a usar. Y las combinaciones que no existen
—`mensual.mensual`, `diario.promedio`— no fallan: devuelven HTTP 200 con un
`text/plain` que dice «psgraph: Could not load macro». Por eso el validador mira
el tipo de contenido y la cabecera antes de aceptar.

**Por qué no entra a `hecho_medicion`.** Esa tabla es horaria y conserva los tres
estados de validación de SINCA por separado; es lo que hace verificable el
análisis. Una serie ya promediada por el proveedor es otra clase de dato.
Mezclarlas dejaría de ser cierto que cada fila es una medición horaria, y nadie
podría distinguir después qué filas eran qué.

**20 días al mes.** Es el mismo 65-75 % de cobertura que ya aplica el resto del
sitio (18 de 24 horas para un día, 300 de 365 días para un año, ver
`cobertura_horaria_semanal.md`). Un mes de 5 días pinta un color en el mapa con
la misma fuerza que uno de 30, y el lector no tiene cómo notar la diferencia.

**300 metros.** Es holgado para una diferencia de redondeo entre el catálogo y
`dim_estacion`, y estrecho frente a la distancia real entre estaciones distintas:
las dos más cercanas del estudio, en Talcahuano, están a 1,3 km. El cruce se hace
por coordenada y **no por nombre** porque SINCA escribe el mismo sitio de varias
formas —«Coyhaique» y «Coihaique»—, y un cruce por texto pierde estaciones sin
lanzar ningún error. Resultado: identificó las 17 del estudio, incluidas
Talagante (fuera de las tres ciudades) y San Vicente (sin datos en la ventana).

## Qué se pierde

- **190 filas estación-mes de 9.243 (2,1 %)** quedan fuera por no llegar a 20
  días. La pérdida se concentra en los extremos de la serie de cada estación
  —el mes en que entró en operación y el mes en que dejó de reportar—, no en una
  estación del año, así que no sesga el contraste verano/invierno.
- **10 estaciones** no aparecen en el mapa aunque el catálogo diga que miden
  MP2.5. Quedan nombradas arriba: es un dato ausente conocido, no un hueco.

## Alternativas descartadas

- **OpenAQ.** Cosecha los datos chilenos desde SINCA y publica
  `round(media_móvil_24h + 10)`, sin marcas de validación
  (`docs/reconocimiento/hallazgos.md` §1.5). En el mismo mapa, sus valores
  quedarían sistemáticamente ~10 µg/m³ por encima de los de SINCA, y el color
  del punto diría más sobre de qué fuente vino que sobre el aire de la comuna.
- **PurpleAir.** Sensores de bajo costo: otro instrumento, otra calibración, y
  sesgo conocido por humedad. Además exige llave de API, y GitHub Pages no puede
  guardar un secreto — la llave quedaría publicada en el JavaScript del sitio.
- **Interpolar una superficie entre estaciones.** Ya estaba descartado para las
  tres ciudades (R² 0,533 del modelo contra 0,750 del promedio de vecinas) y a
  escala nacional es peor: entre Arica y Calama hay 700 km sin una sola estación.
- **Meter la serie nacional en `hecho_medicion`** y dejar que el análisis la use.
  Cambiaría la pregunta del estudio, que está acotada a tres ciudades, y lo haría
  con datos de otra granularidad y sin control de cobertura horaria.
