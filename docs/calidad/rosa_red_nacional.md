# Rosa de contaminación para la red nacional

- **Fecha:** 2026-09-01
- **Aplica a:** `red_nacional_rosa` y el campo `rosa` de las estaciones de
  `sitio/assets/datos/nacional.json`. **No aplica** a `hecho_medicion`,
  `analitico_ciudad_semana` ni a ninguna cifra del análisis: la rosa es una
  figura del mapa.
- **Implementada en:** `src/ingesta/sinca_cliente.py` (`macro_serie`,
  `series_estacion`), `src/ingesta/red_nacional.py` (`sondeo`, `viento`,
  `validar_horaria`), `src/procesamiento/red_nacional_rosa.py`,
  `src/sitio/exportar_nacional.py`
- **Verificable con:** `python -m src.procesamiento.red_nacional_rosa verificar`
  y `python -m src.sitio.exportar_nacional --verificar`

## Qué se observó

Las 84 estaciones de la red nacional entraron al mapa como capa de contexto, con
media mensual y tabla anual, pero **sin rosa de contaminación**: solo las 16 del
estudio la tenían. Un punto que se abre y no muestra lo mismo que los demás
parece a medio hacer.

La rosa necesita cruzar **la concentración de MP2.5 con la dirección del viento
de la misma hora**, así que hacían falta dos series horarias por estación. La
capa nacional solo tenía la serie diaria de partículas.

## El macro que faltaba, y la trampa

La meteorología de SINCA no cuelga de `/Cal/` como los contaminantes sino de
`/Met/`, y no usa el sufijo `.<resolución>.<agregación>`. Pero el problema real
era otro: **pedir la dirección del viento devuelve una rosa de frecuencias, no
una serie**.

| Macro | Qué devuelve |
|---|---|
| `./RM/D14/Met/WSPD//horario_010.ic` | serie horaria de velocidad |
| `./RM/D14/Met/WDIR//horario_010.ic` | **rosa de frecuencias**, 16 sectores, 400 bytes |
| `./RM/D14/Met/WDIR//horario_010_spec.ic` | **serie horaria de dirección** |

La rosa de frecuencias llega con **HTTP 200, `application/csv` y la cabecera
`FECHA (YYMMDD);HORA (HHMM)`**, la misma que una serie legítima. Lo único que
las separa es que su primera columna dice `352,5-7,5` en vez de una fecha. Es la
regla 5 del proyecto en su forma más pura, y por eso `validar_horaria` comprueba
la primera columna y nombra esta causa en el mensaje de error.

El sufijo no se adivinó: sale del propio selector de Airviro, que ofrece las dos
variantes rotuladas «rosa de los vientos» y «serie de tiempo».

Además, **el número del macro es la altura del sensor** (`_010` = 10 m, `_000` =
sin informar) y cambia de estación en estación. Se lee de la ficha, nunca se
construye: es la regla 6.

## Regla adoptada

1. **El macro sale de la ficha, no de una plantilla.** `sondeo` recorre las 111
   fichas y guarda cada serie declarada con su rango real de fechas en
   `data/raw/sinca/nacional/sinca_series_nacional.json`. Es metadato: 111
   páginas de ~30 kB, y responde sin descargar nada cuántas estaciones tienen
   anemómetro y hasta cuándo.
2. **Cuando una ficha declara el mismo parámetro dos veces** —dos sensores a
   distinta altura— se toma **el que llega más lejos en el tiempo** y, a igual
   fin, el que empieza antes. Ver la advertencia del final: elegir mal esta
   entrada hace que una serie viva parezca apagada.
3. **Solo se piden las estaciones que el sondeo dice que tienen dirección del
   viento dentro de la ventana**, y se piden las dos series horarias juntas:
   media rosa no es media información.
4. **El cruce es por (fecha, hora) exacta.** No se interpola ni se busca la hora
   más próxima: emparejar una concentración con la dirección de otra hora sería
   inventar la coincidencia que la rosa afirma haber observado.
5. **Misma definición que las 16 del estudio**, para que las dos rosas del mapa
   se puedan comparar: ocho sectores de 45° con el primero centrado en el norte
   (`floor(((dir + 22.5) mod 360) / 45)`), invierno son los meses 5 a 8, y solo
   entran las horas con las dos medidas presentes, MP2.5 ≥ 0 y dirección en
   [0, 360].

### Umbrales

| Umbral | Valor | Por qué |
|---|---|---|
| `MIN_HORAS_SECTOR` | 50 h de invierno | Bajo eso el pétalo queda en nulo. Una mediana de cuatro horas no es una mediana: es una anécdota con forma de pétalo. El sitio no dibuja los pétalos nulos, que es lo que ya hace con los sectores sin dato del estudio. |
| `MIN_HORAS_INVIERNO` | 720 h pareadas | La estación sin eso se queda sin rosa. Son treinta días completos de mediciones horarias: menos que un invierno, suficiente para que la figura signifique algo. |
| Rango de `WDIR` | [0, 360]° | Detector de columna equivocada: un 999 sería el código de dato faltante de otro sistema colándose como medición. |
| Rango de MP2.5 horario | [0, 3000] µg/m³ | Más alto que el techo diario (1.000) porque una media de 24 horas suaviza lo que una hora de episodio no. No es un límite físico sino un detector de unidad. |

## Resultado

| | estaciones |
|---|---|
| fichas sondeadas | 111 |
| declaran dirección del viento | 87 |
| con dirección dentro de la ventana 2018-2026 | 83 |
| con dirección **y** MP2.5 horario | 82 |
| rechazadas al validar | 1 |
| bajo la reja de cobertura | 1 |
| **con rosa en `red_nacional_rosa`** | **80** |
| de las 84 del mapa, con rosa | 66 |
| de las 84 del mapa, sin rosa | 18 |

- **Descarga:** 164 peticiones, **220,7 MB**. Una serie horaria completa
  2018-2026 son 75.959 filas y ~1,5 MB, y tarda entre 2 y 4 segundos.
- **1.720.874 horas de invierno pareadas** en total.
- **639 de 640 pétalos** tienen mediana de invierno.
- La única rechazada es **Cerrillos I**: devuelve 75.959 filas, todas vacías, en
  las dos series. Ya figuraba entre las diez que hacen lo mismo con la serie
  diaria (`red_nacional_mapa.md`). Va a
  `data/raw/sinca/nacional/_rechazadas_horario.json`.
- La única bajo la reja es **Copiapó Sivica**, con 24 horas de invierno: empezó
  a medir el 31-12-2025.

## Lo que la rosa no dice

Sigue valiendo lo que ya decía el sitio para las 16 del estudio. Un pétalo largo
al este dice «cuando sopló del este, el sensor midió más». **No identifica la
fuente ni predice hacia dónde va el material particulado**: eso exigiría un
inventario de emisiones georreferenciado y un modelo de dispersión, que están
fuera del alcance. Y no afirma causalidad, que es la regla 1.

Dos diferencias con la rosa del estudio, las dos declaradas:

1. La mediana acá es **exacta**; la del estudio sale de `approx_percentile` de
   Athena, que es aproximada. En series de decenas de miles de horas la
   diferencia es de decimales.
2. **No hay velocidad del viento.** `vel_media` va en nulo: WSPD existe en SINCA
   pero el sitio no lo dibuja, y bajarlo habría duplicado el peso de la descarga
   para un campo que nadie lee. Coyhaique ya viaja así entre las del estudio.

## Advertencia: la entrada de sensor equivocada apaga una serie viva

Al sondear Parque O'Higgins (`RM/D14`) apareció esto:

| Serie | Rango que declara la ficha | Junio 2025 | Junio 2026 |
|---|---|---|---|
| `WDIR//horario_000_spec.ic` | 15-12-2003 a **08-05-2025** | 0 de 719 horas | 0 de 719 horas |
| `WDIR//horario_010_spec.ic` | 15-12-2003 a 01-09-2026 | **719 de 719** | **719 de 719** |

Las dos entregan lo mismo donde las dos existen —en junio de 2023 devuelven
bytes idénticos— y solo la de 10 m sigue publicando después de mayo de 2025.

El 8 de mayo de 2025 es exactamente la fecha en que `sitio/fuentes.html` dice
que «la red meteorológica de Santiago se apagó», y sobre esa lectura descansa
que **81.216 de las 90.029 horas-estación de MP2.5 de Santiago no tengan viento
medido** y que se traiga reanálisis ERA5 para rellenarlas.

Lo que se apagó fue **una entrada de sensor, no el anemómetro**. La regla 2 de
este documento —quedarse con la serie que llega más lejos— evita el problema en
la capa nacional. **La ingesta del estudio no está revisada y queda fuera de
este documento**: comprobarlo exige re-ingerir el viento de las 16, reconstruir
`hecho_medicion` y volver a correr Athena, y eso cambia covariables del
análisis. Queda anotado acá para que la decisión se tome a la vista.
