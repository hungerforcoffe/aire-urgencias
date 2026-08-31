# Hallazgos de reconocimiento de fuentes

Documento acumulativo. Cada fuente se cierra antes de pasar a la siguiente.

**Ciudades del estudio: Santiago, Talcahuano y Coyhaique.** Talcahuano sustituyó a
Temuco el 2026-08-06; el apartado 4 recoge qué cambia y qué queda por decidir.

| Fuente | Estado | Fecha de consulta |
|---|---|---|
| OpenAQ | **Cerrado** | 2026-08-06 |
| DEIS (MINSAL) | **Cerrado** (reejecutado para Talcahuano) | 2026-08-06 |
| SINCA (MMA) | parcial — patrón de descarga, catálogo de estaciones y validación por estación | 2026-08-06 |

Scripts que reproducen todo lo de abajo:

- `src/ingesta/reconocer_openaq.py` — acceso, partición, conteo, inventario, barrido, descarga
- `src/ingesta/sinca_cliente.py` — cliente de descarga de SINCA (Airviro)
- `src/ingesta/contrastar_openaq_sinca.py` — contraste de validación 2b
- `src/ingesta/reconocer_deis.py` — disponibilidad, descarga validada, esquema por año,
  perfil, establecimientos y cobertura por ciudad

Evidencia en crudo: `docs/reconocimiento/_openaq_*.json`, `docs/reconocimiento/_contraste_*.json`,
muestras descargadas en `data/raw/openaq/` y `data/raw/sinca/`.

---

# 1. OpenAQ

## 1.1 Acceso

**¿Responde el bucket sin credenciales? Sí.**

```
s3://openaq-data-archive   region us-east-1   signature_version=UNSIGNED
list_objects_v2 -> HTTP 200
```

El CGNAT no afecta a S3. Contraste que lo demuestra: desde la **misma IP y el mismo
cliente**, `openaq-data-archive` responde 200 y `openaq-fetches` (el bucket legado)
responde `403 AccessDenied`. Como uno funciona y el otro no en la misma petición, el
403 **no es** bloqueo por IP: ese bucket dejó de ser público. Es exactamente la
distinción que exige la regla del proyecto.

**La API sí está cerrada:**

| Endpoint | Respuesta |
|---|---|
| `api.openaq.org/v3/locations` | `401 Unauthorized` — exige API key |
| `api.openaq.org/v2/locations` | `410 Gone` — versión retirada |

Consecuencia: todo el catálogo hay que derivarlo del propio bucket. Se puede
(ver 1.2), pero condiciona el diseño.

## 1.2 Partición y formato

El bucket tiene **dos árboles paralelos**, y esto no está documentado:

```
records/csv.gz/locationid=<id>/year=<yyyy>/month=<mm>/location-<id>-<yyyymmdd>.csv.gz
records/csv.gz/provider=<prov>/country=<iso2>/locationid=<id>/year=<yyyy>/month=<mm>/...
```

La vista **plana** por `locationid` no dice de qué país es cada estación. La vista por
**proveedor** sí incluye `country=`, y es la única forma de contar países sin API key.

Se descubrió por accidente: el conteo de prefijos falló con `IndexError` al toparse con
un prefijo que no seguía el patrón `locationid=<n>`. El fallo era el hallazgo.

- **Formato:** CSV comprimido con gzip, **un archivo por estación-día**.
- **Codificación: UTF-8.** Verificado a nivel de bytes: `µg/m³` llega como
  `\xc2\xb5g/m\xc2\xb3`, que es UTF-8, no latin-1. **Distinto de las fuentes chilenas**,
  que sí usan latin-1. No aplicar el mismo lector a ambas.
- **Separador:** coma. Decimal: punto.
- **Husos:** `datetime` viene con desplazamiento local explícito (`-04:00` en Chile),
  no en UTC.

### Esquema: no es uniforme

Sobre 208 estaciones muestreadas aparecen **tres esquemas distintos**:

| Frecuencia | Columnas |
|---|---|
| 195 | `location_id, sensors_id, location, datetime, lat, lon, parameter, units, value` |
| 10 | `location_id, sensors_id, location, datetime, lat, lat, lon, lon, parameter, units, value` — **lat y lon duplicadas** |
| 3 | `... measurand, units, value` — **`measurand` en lugar de `parameter`** |

Un lector que asuma la cabecera estándar falla en ~6% de las estaciones. Se comprobó
en carne propia: el muestreo reventó con `KeyError: 'parameter'`.

**No hay columna de país, ni de ciudad, ni marca de validación.** Solo `lat`/`lon`.

## 1.3 Cobertura mundial y volumen

Conteos exhaustivos (no muestreados):

| Métrica | Valor |
|---|---|
| Prefijos `locationid=` (vista plana) | **55.007** |
| Proveedores | **49** |
| Países (vista por proveedor) | **121** |
| Estaciones bajo la vista por proveedor | **17.983** |

**Las dos vistas no son equivalentes:** la de proveedor cubre 17.983 de 55.007
estaciones (33%). Un marco de referencia internacional construido sobre
`provider/country` descansa sobre un tercio del archivo, no sobre todo.

Top de países por estaciones: `mobile` 4.881 (pseudo-país de sensores móviles),
`us` 4.042, `cn` 1.997, `gb` 661, `fr` 647, `es` 547, `pl` 538, `it` 522, `de` 450,
`ca` 371 … **`cl` 171 (puesto 16 de 121)**.

### Volumen 2018-2024

Muestra aleatoria de 250 estaciones reales; 208 (83,2%) tienen datos en el período.

| Magnitud | Estimación |
|---|---|
| Estaciones con datos | ~45.800 |
| Archivos | ~16,2 millones |
| Disco comprimido | ~9,8 GB |
| Disco sin comprimir | ~243 GB |
| Filas | **~74.000 millones (orden de magnitud, no cifra firme)** |

Advertencia sobre la cifra de filas: la media es **4.570 filas por archivo**, pero la
estación Parque O'Higgins tiene **20**. La distribución está dominada por sensores de
bajo costo que registran cada minuto y muchos parámetros a la vez. La media está
inflada por esa cola; la mediana es mucho menor. Tratar los 74.000 millones como cota
superior de orden de magnitud, no como conteo.

Ratio de compresión medido: **24,8x**.

**Cabe en el entorno.** 9,8 GB comprimidos es manejable en la VM de Hadoop de 8 GB si
se procesa por particiones. Lo caro no es el volumen sino los **16 millones de objetos**:
un archivo por estación-día implica un coste de listado y apertura que domina sobre el
coste de leer bytes.

## 1.4 Chile en OpenAQ

`provider=chile-sinca/country=cl/` → **171 estaciones**, 148 con datos 2018-2024.

Estaciones en las tres ciudades del estudio, con su equivalente en SINCA:

| Ciudad | OpenAQ id | Nombre | SINCA | Cobertura 2018-2024 |
|---|---|---|---|---|
| Santiago | 25 | Parque O'Higgins | RM/D14 | completa |
| Santiago | 45 | Puente Alto | RM/D27 | completa |
| Santiago | 54 | Talagante | RM/D28 | completa |
| Santiago | 725 | Independencia | — | **corta en 2021** |
| Santiago | 846 | Cerro Navia | RM/D18 | completa |
| Santiago | 849 | El Bosque | RM/D17 | completa |
| Santiago | 852 | La Florida | RM/D12 | completa |
| Santiago | 967 | Pudahuel | RM/D15 | completa |
| Santiago | 1330 | Las Condes | RM/D13 | completa |
| Santiago | 2268 | Quilicura | RM/D30 | completa |
| Santiago | 8788 | Cerrillos | RM/D16 | **corta en 2021** |
| Santiago | 326680 | Cerrillos II | RM/D35 | **solo 2022-2023** |
| Talcahuano | 2525 | Consultorio - San Vicente | RVIII/802 | completa |
| Talcahuano | 2473 | Nueva Libertad | RVIII/837 | completa |
| Talcahuano | 26 | Inpesca | RVIII/806 | completa |
| Talcahuano | 808 | Indura | RVIII/807 | completa |
| Coyhaique | 73 | Coyhaique II | RXI/B04 | completa |
| Coyhaique | 1984 | Coyhaique | RXI/B03 | completa |

Peso de estas 17 estaciones en 2018-2024: **28.652 archivos, 15,1 MB comprimidos.**

**Hay recambio de estaciones dentro del período.** Cerrillos corta en 2021 y Cerrillos II
arranca en 2022; Independencia corta en 2021. Una serie de "Santiago" que sume estaciones
sin tratar el recambio tendrá saltos artificiales en 2021-2022 que no son variación de
MP2.5 sino cambio de instrumento. Esto hay que resolverlo aunque la fuente final sea
SINCA, porque el recambio es real y también estará ahí.

## 1.5 Contraste de validación (2b)

Pregunta: ¿OpenAQ replica el dato de SINCA o difiere?

Método: mismo mes (julio 2023, invierno) y misma estación en ambas fuentes, comparación
hora a hora. **Se probaron desfases de -2 a +2 horas** para no confundir un
desalineamiento horario con una diferencia de valores.

### Resultado: DIFIEREN, y no por desalineamiento

| Estación | Horas comparadas | Idénticas | Dif. media | Mejor desfase |
|---|---|---|---|---|
| Santiago / Parque O'Higgins | 703 | **2,1%** | +10,5 µg/m³ | ninguno mejora |
| Temuco / Padre Las Casas II † | 674 | **0,7%** | +13,7 µg/m³ | ninguno mejora |
| Coyhaique II | 676 | **0,7%** | +11,2 µg/m³ | ninguno mejora |

Ningún desfase horario sube la coincidencia por encima del 2,4%. No es un problema de
alineación temporal: **son datos distintos**.

### Qué publica OpenAQ realmente

OpenAQ **no publica el dato horario de SINCA**. Publica una **media móvil de 24 horas
desplazada en +10 µg/m³ y redondeada a entero.**

Comparando el valor de OpenAQ contra medias móviles de la serie validada de SINCA:

| Ventana | Correlación |
|---|---|
| 1 h (dato horario) | 0,596 |
| 6 h | 0,734 |
| 12 h | 0,872 |
| **24 h** | **0,9998** |

Con ventana de 24 h, la diferencia respecto de OpenAQ es:

```
media = 10,0048    sd = 0,2888    rango = [9,542 ; 10,500]    n = 680
```

La prueba decisiva es la **sd = 0,2888**. El error de redondear a entero se distribuye
uniforme en [-0,5 ; 0,5], cuya desviación teórica es 1/√12 = **0,28868**. La coincidencia
a cuatro decimales significa que, una vez aplicado el +10, **el único ruido que queda es
el redondeo**: la relación es determinista.

```
OpenAQ = round( media_móvil_24h(SINCA validado) + 10 )
```

Reproduce el valor exacto en el 97,6% de las horas en Parque O'Higgins, y 90-92% en las
demás (la diferencia se explica por huecos en la serie, que desalinean la ventana).

Verificado en **cuatro estaciones de tres regiones**, con el mismo desplazamiento:

| Estación | Offset mediano | `round(MM24+10)` exacto |
|---|---|---|
| Santiago / Parque O'Higgins | +10,00 | 97,6% |
| Santiago / Las Condes | +9,96 | 90,4% |
| Temuco / Padre Las Casas II † | +10,12 | 91,7% |
| Coyhaique II | +10,00 | 92,2% |

Un desplazamiento de +10 idéntico en tres regiones distintas es un artefacto sistemático
del procesamiento de OpenAQ, no una característica de las estaciones.

† Las estaciones de Temuco se usaron cuando esa ciudad estaba en el alcance. Al
sustituirse por Talcahuano (2026-08-06) **la evidencia sigue siendo válida**: el
hallazgo es sobre el procesamiento de OpenAQ, no sobre una ciudad concreta, y se
verificó en cuatro estaciones de tres regiones. No se repitió sobre Talcahuano porque
no cambiaría la conclusión.

### ¿Es el preliminar contra el validado? No

La hipótesis se probó y **no se sostiene**. SINCA expone tres columnas excluyentes
—`Registros validados`, `Registros preliminares`, `Registros no validados`— y en los
períodos consultados la de preliminares está **vacía**:

| Período (Parque O'Higgins) | Validados | Preliminares | No validados |
|---|---|---|---|
| junio 2024 | 714 | 0 | 0 |
| junio 2025 | 719 | 0 | 0 |
| junio 2026 | 718 | 0 | 0 |

Ni siquiera el mes más reciente disponible tiene preliminares pendientes. No hay
diferencia preliminar/validado que explique la discrepancia: la explicación es la media
móvil desplazada.

**Por qué exactamente +10 queda como pregunta abierta.** El dato empírico es firme; el
mecanismo que lo produce, no.

### Marcas de validación y meteorología

- **OpenAQ no conserva marca de validación alguna.** Su esquema no tiene ese campo.
  SINCA sí las tiene, en tres columnas. Esa información **solo existe en SINCA**.
- **OpenAQ no trae meteorología para las estaciones chilenas.** Parque O'Higgins, día
  completo: solo `pm10` y `pm25`, dos sensores. Cero temperatura, cero viento.
- A escala global sí existen `temperature`, `humidity`, `pressure`, `relativehumidity`,
  pero concentrados en sensores de bajo costo de otras redes, no en SINCA.

## 1.6 Percentil mundial (viabilidad de 2a)

**Es viable, con reservas que hay que declarar.**

A favor: 121 países y ~45.800 estaciones con datos en 2018-2024 dan base comparativa
sobrada, y 9,8 GB es procesable en el entorno disponible.

Reservas que condicionan la lectura del percentil:

1. **La cobertura por país es muy desigual.** EE.UU. tiene 4.042 estaciones y hay países
   con una sola. Un percentil sobre estaciones sobre-representa a los países con redes
   densas. Ponderar por país, o declarar que el percentil es *sobre estaciones
   monitoreadas* y no *sobre ciudades del mundo*.
2. **La vista con país cubre un tercio del archivo.** Las otras dos terceras partes no
   tienen país sin geocodificación inversa por `lat`/`lon`.
3. **Mezcla instrumentos.** El pseudo-país `mobile` (4.881 estaciones) y proveedores como
   `habitatmap` o `clarity` son sensores de bajo costo, no equipos de referencia. No son
   comparables con una estación SINCA sin filtrarlos.
4. **El valor chileno en OpenAQ está transformado.** Por 1.5, comparar el número de
   OpenAQ para Santiago contra el resto del mundo compara una media móvil desplazada
   contra lo que publiquen los demás. **El percentil de las tres ciudades debe calcularse
   con el dato de SINCA**, insertado en la distribución mundial de OpenAQ — nunca con el
   número que OpenAQ trae para Chile.

## 1.7 Riesgos y decisiones que gatillan

| # | Riesgo | Evidencia | Decisión que gatilla |
|---|---|---|---|
| R1 | Usar OpenAQ como dato chileno introduciría un sesgo de +10 µg/m³ y suavizado de 24 h | 1.5 | Confirma la regla del proyecto. OpenAQ **solo** para referencia internacional. El punto 2b queda cerrado: no hay respaldo posible desde OpenAQ |
| R2 | El percentil mundial calculado con el valor chileno de OpenAQ sería inválido | 1.5, 1.6 | El percentil se calcula con MP2.5 de SINCA insertado en la distribución de OpenAQ |
| R3 | Tres esquemas de CSV distintos | 1.2 | El lector debe normalizar cabeceras: aceptar `measurand` como alias de `parameter` y colapsar columnas duplicadas. Falla en ~6% si no |
| R4 | La vista con país cubre 33% del archivo | 1.3 | Decidir: ¿percentil sobre las 17.983 con país, o geocodificar las 55.007 por `lat`/`lon`? |
| R5 | 16,2 millones de objetos pequeños | 1.3 | El coste es de listado, no de bytes. Consolidar a Parquet particionado en la ingesta; no arrastrar 16 M de archivos al pipeline |
| R6 | Sensores de bajo costo mezclados con equipos de referencia | 1.6 | Filtrar por proveedor antes de comparar. Requiere criterio escrito en `docs/calidad/` |
| R7 | Recambio de estaciones en Santiago en 2021-2022 | 1.4 | Definir regla de empalme o de exclusión **antes** de agregar por ciudad. Afecta a SINCA también |
| R8 | La API exige key; el bucket legado ya no es público | 1.1 | No construir nada que dependa de la API v3 sin decidir antes si se tramita una key |

## 1.8 Preguntas abiertas para el equipo

1. **¿De dónde sale el +10?** El hallazgo empírico es sólido y suficiente para descartar
   OpenAQ como fuente chilena. Entender el mecanismo no es necesario para el proyecto,
   pero sí sería material publicable. ¿Se investiga o se documenta y se sigue?
2. **¿Percentil sobre estaciones o sobre países?** Cambia el mensaje del resultado y hay
   que fijarlo antes de calcular (R4).
3. **¿Se filtran los sensores de bajo costo?** Afecta a con qué se compara Santiago (R6).
4. **¿Se tramita API key de OpenAQ?** Es gratis y daría el catálogo completo con país y
   tipo de instrumento, resolviendo R4 y R6 de una vez. Hoy no es necesaria, pero
   ahorraría trabajo.
5. **Recambio de estaciones (R7):** ¿se empalman Cerrillos I y II como una serie, se
   tratan por separado, o se excluyen? Decisión de diseño, no técnica.

## 1.9 Conclusión

**OpenAQ queda exclusivamente para el uso 2a, referencia internacional.**

El punto 2b se cierra con un resultado más fuerte que el previsto: no es que OpenAQ
duplique el dato de SINCA —que era la razón original para no usarlo— sino que **publica
una transformación de ese dato** (media móvil de 24 h + 10, redondeada), sin marcas de
validación y sin meteorología. No sirve como respaldo ni como contraste de validación.

La idea de "medir cuánto cambia un dato al validarse" **no es realizable con estas dos
fuentes**: la diferencia observada no es validación, es transformación. Esa medición
requeriría capturar el preliminar de SINCA en tiempo real y compararlo con el validado
meses después — un diseño distinto, fuera del alcance actual.

---

# 2. SINCA (avance parcial)

Reconocimiento completo pendiente (tarea 4). Lo ya establecido para hacer 2b:

**Patrón de descarga**, deducido leyendo el JavaScript de la página de consulta
(no está documentado):

```
https://sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.tsindico2.cgi
    ?outtype=xcl
    &macro=./<REGION>/<ESTACION>/Cal/<PARAM>//<PARAM>.<res>.<agg>.ic
    &from=<AAMMDD>&to=<AAMMDD>
    &path=/usr/airviro/data/CONAMA/&lang=esp&rsrc=&macropath=
```

Tres trampas, todas verificadas:

1. **`outtype=xcl` devuelve CSV**, pese al nombre. `outtype=csv` devuelve un **GIF vacío
   de 0 bytes con HTTP 200**: un éxito aparente sin datos. Nunca tratar 200 como
   sinónimo de "hay dato".
2. **Las barras de `macro` no deben codificarse.** Pasarlo por `params=` de `requests`
   las convierte en `%2F` y el servidor responde el mismo GIF vacío.
3. Fechas en **AAMMDD** (dos dígitos de año).

**Acceso:** `sinca.mma.gob.cl` responde 200, servidor Apache directo, **sin CloudFront**.
El CGNAT no lo bloquea.

**Formato:** CSV, separador `;`, codificación **latin-1**, sin comillas.

**Marcas de validación — el activo diferencial de SINCA:**

```
FECHA (YYMMDD);HORA (HHMM);Registros validados;Registros preliminares;Registros no validados;
230714;0100;50;;;
230714;0200;42;;;
```

Tres columnas excluyentes. Un dato aparece en una sola. Esta información no existe en
ninguna otra fuente del proyecto.

**Códigos de estación identificados** para las tres ciudades:

| Ciudad | Región | Estaciones con MP2.5 |
|---|---|---|
| Santiago | `RM` | D12 La Florida, D13 Las Condes, D14 Parque O'Higgins, D15 Pudahuel, D16 Cerrillos I, D17 El Bosque, D18 Cerro Navia, D27 Puente Alto, D28 Talagante, D29 Quilicura I, D30 Quilicura, D35 Cerrillos II |
| Talcahuano | `RVIII` | 802 Consultorio - San Vicente, 803 Libertad, 806 Inpesca, 807 Indura, 837 Nueva Libertad |
| Coyhaique | `RXI` | B03 Coyhaique, B04 Coyhaique II |

**12 estaciones con MP2.5 en Santiago, 5 en Talcahuano, 2 en Coyhaique.** Pero sólo
una de las cinco de Talcahuano publica datos validados: ver §4.
Nota: `Independencia` aparece en la web de SINCA pero **no entre las estaciones con
macro de MP2.5** en la Región Metropolitana, lo que concuerda con que OpenAQ corte esa
serie en 2021.

Pendiente para la tarea 4: resolución diaria vs horaria, disponibilidad de temperatura y
viento por estación, unidades, filas por estación-año y volumen nacional.

---

# 3. DEIS (MINSAL) — Atenciones de Urgencia

## 3.0 HALLAZGO DESTACADO: el DEIS es DIARIO

**La granularidad es diaria, con cobertura completa y sin huecos.** Cada año trae
exactamente 365 días (366 en bisiestos), del 1 de enero al 31 de diciembre:

| Año | Días distintos | Rango |
|---|---|---|
| 2020 | 366 | 2020-01-01 … 2020-12-31 |
| 2021 | 365 | 2021-01-01 … 2021-12-31 |
| 2022 | 365 | 2022-01-01 … 2022-12-31 |
| 2023 | 365 | 2023-01-01 … 2023-12-31 |
| 2024 | 366 | 2024-01-01 … 2024-12-31 |

El archivo trae **además** una columna `semana` (semana estadística) ya calculada,
de modo que la agregación semanal no exige construirla.

**Esto cambia el diseño de rezagos y hay que decidirlo antes de seguir.** Con dato
diario, el rezago de "hasta 2 semanas" puede especificarse en días (0-14) en vez de
en bloques semanales, lo que permite ver la forma de la respuesta en vez de dos
puntos. SINCA también es horario, así que **ambos lados soportan resolución diaria**;
la restricción semanal del alcance original ya no viene impuesta por los datos.

Ver 3.8 para la decisión que esto abre.

## 3.1 Acceso y validación

Ruta de descarga:

```
https://repositoriodeis.minsal.cl/SistemaAtencionesUrgencia/AtencionesUrgencia<AAAA>.zip
```

**No está enlazada desde ninguna página navegable.** La sección de datos abiertos de
`deis.minsal.cl` se carga por JavaScript y no expone enlaces en el HTML. El registro
de `datos.gob.cl` (dataset 6376, creado en 2013 y nunca actualizado) apunta a
`www.deis.cl`, **dominio que ya no resuelve en DNS**. La ruta se ubicó por búsqueda.

Distinción bloqueado / inexistente, comprobada en el propio servidor:

| Ruta | Respuesta | Lectura |
|---|---|---|
| `repositoriodeis.minsal.cl/` | 403 (IIS "Access is denied") | existe, listado de directorio deshabilitado |
| `/DatosAbiertos/` | **403** | el directorio existe |
| `/DatosAbiertos/AtencionesUrgencia/` | **404** | esa ruta no existe |

El servidor devuelve códigos distintos para "existe pero no listo" y "no existe", así
que el 403 **no es** bloqueo por CGNAT. Se confirma además porque las descargas reales
desde el mismo host funcionan.

Toda descarga pasa por `validar_zip`, que comprueba en orden: código HTTP →
content-type → **números mágicos reales** (`PK\x03\x04`) → integridad (`testzip`) →
que haya miembros. Nada se escribe en `data/raw/` sin pasar los cinco controles.

Años disponibles y verificados como ZIP íntegros: **2017 a 2026**. El período del
estudio está cubierto por completo.

## 3.2 El formato cambia entre años

**El ZIP no siempre contiene un CSV.**

| Año | Contenido del ZIP | Formato |
|---|---|---|
| 2018 | `AtencionesUrgenciaLineal2018.mdb` + `ATENCIONES_DE_URGENCIA.xlsx` | **Microsoft Access** |
| 2019 | `AtencionesUrgencia2019.mdb` + `ATENCIONES_DE_URGENCIA.xlsx` | **Microsoft Access** |
| 2020 | `AtencionesUrgencia2020.csv` + `ATENCIONES_DE_URGENCIA.xlsx` | CSV |
| 2021-2024 | `AtencionesUrgencia<año>.csv` | CSV (sin diccionario) |

Los `.mdb` pesan **1,10 GB y 1,11 GB** descomprimidos. Se leen con el driver ODBC
`Microsoft Access Driver (*.mdb, *.accdb)` de 64 bits, presente en el equipo, vía
`pyodbc`. Sin ese driver, **2018 y 2019 son ilegibles** y el período se reduce a
2020-2024, que son justo los años contaminados por la pandemia.

El `.xlsx` que acompaña a 2018-2020 es el **diccionario de datos oficial**: hojas
`Ficha`, `DiccionarioSADU`, `Anexo 1` (causas), `Anexo 2` (establecimientos) y
`Ord. N°337`. **Desde 2021 deja de publicarse**, así que el diccionario aplicable a
los años recientes hay que tomarlo de 2020.

## 3.3 El esquema NO es estable

Comparación explícita de columnas entre años:

| Año | Columnas | Cabecera | Nombre del campo de causa | Geografía |
|---|---|---|---|---|
| 2018-2019 | 15 | tabla Access | `Idcausa` | no |
| 2020 | 15 | **NO TIENE** | — | no |
| 2021 | 15 | sí | `IdCausa` | no |
| 2022 | 15 | sí | **`Idcausa`** (minúscula) | no |
| 2023 | **21** | sí | `IdCausa` | **sí** |
| 2024 | 21 | sí | `IdCausa` | sí |

Cuatro rupturas concretas:

**1. 2020 se publicó sin fila de cabecera.** La primera línea ya es un dato:

```
19-809;SAPU Talcahuano Sur;21;TOTAL DEMÁS CAUSAS;22;0;1;4;15;2;Wed Sep 23 ... 2020;39;SAPU;Indiferenciado;Ninguna
```

Un lector con `header=0` perdería esa fila y usaría sus valores como nombres de
columna. El script lo detecta y asigna los nombres de 2021.

**2. El formato de fecha cambia.** En 2020 las fechas son objetos `Date` de Java
serializados — `Wed Sep 23 00:00:00 GMT-04:00 2020` — mientras que en 2018, 2019 y
2021-2024 son `dd/mm/aaaa`. Un único parser falla en uno de los dos grupos.

**3. `IdCausa` cambia de capitalización** solo en 2022. Suficiente para romper un
`df["IdCausa"]`.

**4. 2023 añade seis columnas geográficas**: `CodigoRegion`, `NombreRegion`,
`CodigoDependencia`, `NombreDependencia`, `CodigoComuna`, `NombreComuna`.

Codificación **latin-1** y separador `;` en todos los años. Ningún año trae UTF-8.

### Las columnas del Access no tienen nombre

En los `.mdb` de 2018-2019 las seis columnas numéricas se llaman `Col01`…`Col06`, sin
significado declarado, y sus tipos no siguen el orden esperado (`Col01`-`Col04` son
SMALLINT y `Col05`-`Col06` INTEGER, lo que sugiere que el total no va primero).

**No se asumió el mapeo: se verificó.** Sobre las 4.488.935 filas de 2018:

```
Col01 = Col02 + Col03 + Col04 + Col05 + Col06   →   4.488.935 de 4.488.935 (100,00%)
```

Con `MAX(Col01)=2732` dominando al resto, queda establecido que el orden coincide con
el del CSV: `Total, Menores_1, De_1_a_4, De_5_a_14, De_15_a_64, De_65_y_mas`.

## 3.4 Valores derivados: sí los hay, y hay una trampa

**El archivo mezcla agregados con detalle en la misma columna.** Las 40 causas
incluyen totales de sección que son suma de otras filas. Verificado sobre 2018:

```
causas 3+4+5+6+10+11 (detalle respiratorio)  = 4.939.422
causa 2  «TOTAL CAUSAS SISTEMA RESPIRATORIO» = 4.939.422   → IDÉNTICO
```

Y la coincidencia se repite en **todos** los años (2020-2024 comprobados uno a uno).
**Sumar todas las filas de causa cuenta cada atención al menos dos veces.**

### La trampa: la causa 7 no es lo que su nombre dice

La causa **7 se llama `CAUSAS SISTEMA RESPIRATORIO`** y es fácil confundirla con las
atenciones respiratorias. No lo es:

```
causas 7 + 8 + 22 + 23                        = 548.790
causa 25 «SECCIÓN 2. TOTAL DE HOSPITALIZACIONES» = 548.790   → IDÉNTICO
```

**La causa 7 pertenece a la Sección 2 del formulario: son hospitalizaciones por causa
respiratoria, no atenciones de urgencia.** Su magnitud (79.897 en 2018) es ~60 veces
menor que la causa 2 (4.939.422). Usarla como "urgencias respiratorias" subestimaría
el indicador en dos órdenes de magnitud.

Filas que son agregados o encabezados de sección, no causas:
`1, 2, 7, 8, 12, 18, 21, 22, 23, 25, 26, 34, 36, 42`.

### No hay suavizado

A diferencia de OpenAQ, **el DEIS publica conteos brutos, no transformados**:

- Los valores son enteros sin redondeo sospechoso.
- La suma de los cinco grupos etarios iguala la columna `Total` en el **100 % de las
  filas, en los cinco años CSV** (0 discrepancias sobre ~42 millones de filas).

La consistencia interna es exacta. El único "derivado" son los totales por sección
descritos arriba, que además están declarados en el diccionario.

## 3.5 Causas y grupos etarios

**Causas respiratorias, con CIE-10 explícito** (esto es detalle, no agregado):

| IdCausa | Glosa | CIE-10 |
|---|---|---|
| 3 | Bronquitis/bronquiolitis aguda | J20-J21 |
| 4 | Influenza | J09-J11 |
| 5 | Neumonía | J12-J18 |
| 6 | Otra causa respiratoria | J22, J30-J39, J47, J60-J98 |
| 10 | IRA Alta | J00-J06 |
| 11 | Crisis obstructiva bronquial | J40-J46 |

Total de causas distintas: **40 en todos los años** (esto sí es estable).

**Grupos etarios: cinco**, en columnas separadas — `Menores_1`, `De_1_a_4`,
`De_5_a_14`, `De_15_a_64`, `De_65_y_mas`. Permite restringir el análisis a los grupos
más sensibles (menores de 5 y mayores de 65) sin trabajo adicional.

## 3.6 Establecimiento y geografía

Lo que identifica al establecimiento es `IdEstablecimiento`, un **código antiguo** con
formato `RR-NNN` (ej. `13-100`, `21-905`), más `NEstablecimiento` (nombre) y
`GLOSATIPOESTABLECIMIENTO` (Hospital, SAPU, SAR…).

**Hasta 2022 el archivo no trae ningún campo geográfico.** Región, comuna y
dependencia solo aparecen desde 2023. Para 2018-2022 la única vía de asignar una
atención a una ciudad es **cruzar por `IdEstablecimiento` con la Base de
Establecimientos** del año correspondiente:

```
https://repositoriodeis.minsal.cl/ContenidoSitioWeb2020/Establecimientos/Base de Establecimientos <AAAA>.xlsx
```

Trae `Código Comuna`, `Nombre Comuna`, coordenadas y fechas de vigencia. Descargadas y
validadas para 2018-2024.

### La dimensión también tiene esquema inestable

| Año | Columnas | Clave del establecimiento | Fechas vigencia/cierre |
|---|---|---|---|
| 2018 | 29 | `Código Antiguo Establecimiento` | Vigencia + Cierre |
| 2019 | 30 | `Código Antiguo Establecimiento` | Vigencia + Cierre |
| 2020 | 30 | **`Código Antiguo`** | solo `Fecha de Vigencia` |
| 2021 | 31 | `Código Antiguo` | **ninguna** |
| 2022-2023 | 32 | `Código Antiguo` | **ninguna** |
| 2024 | 32 | `Código Antiguo` + `Código  Madre Antiguo` | **ninguna** |

Dos consecuencias:

1. La cabecera real está en la **fila 2**, no en la primera.
2. **Las fechas de apertura y cierre desaparecen desde 2021.** El recambio de
   establecimientos no se puede leer de la dimensión: hay que **inferirlo de la
   presencia o ausencia en cada base anual**, que es lo que hace el script.
3. En 2024 aparece `Código  Madre Antiguo` (con doble espacio), que un emparejador
   por subcadena confunde con la clave. Hay que excluirlo explícitamente.

## 3.7 Cobertura por establecimiento y año en las tres ciudades

Establecimientos con registro de urgencias, por ciudad y año:

| Ciudad | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|
| Santiago (Gran Santiago) | 104 | 104 | **112** | 115 | 113 | 115 | 116 |
| Talcahuano | 5 | 5 | 5 | 6 | 5 | 5 | 5 |
| Coyhaique | 2 | **1** | 2 | 2 | 2 | 2 | 2 |

**Talcahuano es notablemente estable**: 5 establecimientos todos los años, salvo 6 en
2021. No tiene el salto de cobertura que sí tenía Temuco. Pero esconde un problema
más sutil, descrito abajo.

### El identificador de establecimiento NO es una clave estable

En Talcahuano tres códigos tienen presencia parcial:

| Código | Presente en | Ausente en |
|---|---|---|
| `19-808` | 2018-2021 | 2022-2024 |
| `19-912` | 2021-2023 | 2018-2020, 2024 |
| `201018` | 2024 | 2018-2023 |

Parecen tres establecimientos: uno que cierra, otro que nace y muere, y un tercero que
aparece al final. **Son dos, y uno de ellos cambia de identificador.** Cruzando con la
Base de Establecimientos:

```
base 2021:  antiguo=19-808   vigente=119808   SAPU Los Cerros
base 2021:  antiguo=19-912   vigente=201018   SAR  Los Cerros
base 2024:  antiguo=201018   vigente=201018   SAR  Los Cerros   <- el codigo antiguo fue reemplazado
```

Dos cosas distintas ocurriendo a la vez:

1. **`19-808` → `19-912`** es una conversión real: SAPU Los Cerros se convierte en SAR
   Los Cerros. Se ve en el reparto de 2021 (117 días el SAPU, 306 días el SAR).
2. **`19-912` → `201018`** **no es un cambio de establecimiento**: es el mismo SAR Los
   Cerros, al que el DEIS empezó a identificar en 2024 con su código *vigente* en vez
   del *antiguo*.

La migración de codificación es progresiva y afecta a todo el país, no solo a
Talcahuano:

| Año | Ids formato antiguo `NN-NNN` | Ids formato vigente `NNNNNN` |
|---|---|---|
| 2022 | 622 | 16 |
| 2023 | 620 | 22 |
| 2024 | 609 | **31** |

Un análisis que trate `IdEstablecimiento` como clave estable contará el mismo
establecimiento dos veces y verá cierres y aperturas que no ocurrieron.

**Coyhaique pierde un establecimiento en 2019** (`25-900`, presente en 2018 y de
2020 en adelante: un hueco de exactamente un año).

**Santiago tiene 44 de 116 establecimientos con presencia parcial** (38 %).

Serie de urgencias respiratorias (solo causas de detalle, sin agregados):

| Ciudad | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|
| Santiago | 1.461.977 | 1.484.576 | **368.052** | **382.439** | 1.173.996 | 1.427.298 | 1.440.931 |
| Talcahuano | 75.568 | 70.439 | **13.992** | **13.671** | 54.804 | 59.084 | 52.853 |
| Coyhaique | 21.719 | 20.578 | **4.388** | 4.695 | 17.147 | 21.978 | 23.894 |

El desplome de 2020-2021 (Santiago cae al **25 %** de su nivel de 2019) es el efecto
de la pandemia sobre la consulta de urgencia, no sobre la contaminación. Confirma que
controlar por período de pandemia no es opcional.

**Talcahuano no recupera su nivel previo.** 2022-2024 se mueve en 53.000-59.000 frente
a 70.000-76.000 en 2018-2019: alrededor de un **25 % por debajo**, con la misma
cantidad de establecimientos. A diferencia de lo que pasaba con Temuco, aquí la caída
**no** se explica por cobertura — los cinco establecimientos siguen ahí y registran los
365 días. Es una diferencia de nivel que hay que tener presente al modelar, porque un
control de pandemia binario (2020-2021 sí / resto no) no la captura.

### Establecimientos sin correspondencia en la dimensión

| Año | Ids en urgencias que no están en la Base de Establecimientos |
|---|---|
| 2018 | 14 |
| 2019 | 15 |
| 2020 | 1 |
| 2021 | 0 |
| 2022 | 7 |
| 2023 | 5 |
| 2024 | 5 |

Estos registros **no pueden asignarse a comuna** por la vía del cruce. Hay que decidir
si se descartan o si se resuelven a mano, y documentarlo en `docs/calidad/`.

## 3.8 Volumen

| Año | Filas | Formato | Descomprimido |
|---|---|---|---|
| 2018 | 4.488.935 | mdb | 1,10 GB |
| 2019 | 4.550.877 | mdb | 1,11 GB |
| 2020 | 6.446.646 | csv | 1,02 GB |
| 2021 | 8.816.240 | csv | 1,04 GB |
| 2022 | 8.926.307 | csv | 1,06 GB |
| 2023 | 8.899.080 | csv | 1,49 GB |
| 2024 | 8.973.229 | csv | 1,50 GB |
| **Total 2018-2024** | **51.101.314** | | **≈ 8,3 GB** |

Comprimido en ZIP: **573 MB**. Establecimientos activos: 607 (2020) a 642 (2023).

La estructura es un producto cartesiano: establecimiento × causa × día. Por eso hay
tantas filas con valor cero — el archivo registra explícitamente los días sin
atenciones de una causa, lo cual es bueno (ausencia de fila ≠ cero) pero infla el
volumen unas 40 veces respecto del dato con contenido.

## 3.9 Riesgos y decisiones que gatillan

| # | Riesgo | Evidencia | Decisión que gatilla |
|---|---|---|---|
| D1 | **Granularidad diaria** | 3.0 | Decidir resolución del análisis: diaria (0-14 días de rezago) o semanal. Ambas fuentes la soportan. **Bloquea el diseño de rezagos** |
| D2 | Doble conteo por sumar agregados con detalle | 3.4 | Filtrar SIEMPRE a `IdCausa ∈ {3,4,5,6,10,11}`. Nunca sumar todas las causas |
| D3 | La causa 7 parece respiratoria y es hospitalización | 3.4 | Excluirla explícitamente. Error silencioso de factor ~60 |
| D4 | 2018-2019 en Access | 3.2 | Sin driver ODBC el período se reduce a 2020-2024, justo los años de pandemia. Convertir a Parquet una sola vez |
| D5 | 2020 sin cabecera + fecha en formato Java | 3.3 | El lector debe tratar 2020 como caso especial. Un parser único falla |
| D6 | `IdCausa` / `Idcausa` según el año | 3.3 | Normalizar nombres de columna al leer |
| D7 | Sin geografía hasta 2022 | 3.6 | Obligatorio cruzar con Base de Establecimientos por año. No se puede usar la de un solo año para todo el período |
| D8 | **`IdEstablecimiento` cambia de formato a mitad del período** | 3.7 | Normalizar códigos antiguo ↔ vigente con la Base de Establecimientos antes de construir cualquier serie por establecimiento. Afecta a 31 establecimientos en 2024, uno de ellos en Talcahuano |
| D9 | Caída del 75 % en 2020-2021 | 3.7 | El control por pandemia debe ser explícito, no un simple indicador binario de año |
| D10 | 14-15 establecimientos sin mapa en 2018-2019 | 3.7 | Regla de descarte o resolución manual, documentada |
| D11 | El diccionario deja de publicarse en 2021 | 3.2 | Congelar el diccionario de 2020 como referencia del proyecto |

## 3.10 Preguntas abiertas para el equipo

1. **¿Diario o semanal?** Es la decisión que bloquea el resto. El dato diario permite
   ver la forma del rezago en vez de dos puntos, pero multiplica el volumen y exige
   tratar el efecto día de la semana (la consulta de urgencia tiene estacionalidad
   semanal fuerte). Recomendación: construir la tabla final **diaria** y agregar a
   semanal en el último paso, de modo que ambas opciones queden abiertas sin reprocesar.
2. **¿Se empalma SAPU Los Cerros con SAR Los Cerros?** Es una conversión de servicio
   en el mismo lugar, no un cierre y una apertura. Empalmarlos da una serie continua
   para Talcahuano; tratarlos por separado deja dos series truncadas. Recomendación:
   empalmar, y documentar la regla en `docs/calidad/`.
3. **¿Qué causas entran en "urgencia respiratoria"?** Las seis de detalle, o un
   subconjunto. Influenza (4) y las IRA altas (10) pueden responder más a circulación
   viral que a contaminación — de ahí la utilidad de la fuente ISP como control.
4. **¿Se restringe por grupo etario?** Menores de 5 y mayores de 65 son los grupos
   sensibles; usarlos reduce ruido pero también reduce los conteos de Coyhaique, que
   ya son bajos (2 establecimientos).
5. **¿Qué se hace con los establecimientos sin mapa** (D10)?
6. **Coyhaique tiene solo 2 establecimientos y 1 en 2019.** ¿Es suficiente para una
   serie diaria estable, o hay que agregarla semanalmente aunque el resto vaya diario?

## 3.11 Conclusión

El DEIS es una fuente **mejor de lo previsto en granularidad** y **peor de lo previsto
en estabilidad**. Da dato diario limpio, con causas en CIE-10, cinco grupos etarios y
consistencia interna exacta — pero cambia de formato, de esquema y de cabecera entre
años, y esconde dos trampas de agregación que producirían errores silenciosos de
factor 2 y factor 60.

Ninguno de esos problemas es bloqueante. Todos exigen que la ingesta trate **cada año
como un caso distinto** en vez de aplicar un lector único, que es exactamente lo
contrario de lo que sugiere que los archivos se llamen igual.

---

# 4. Cambio de ciudad: Temuco → Talcahuano (2026-08-06)

Talcahuano sustituye a Temuco por ser una ciudad reconocida por su contaminación
industrial. Este apartado recoge lo que cambia y lo que hay que decidir.

## 4.1 Talcahuano en SINCA: 5 estaciones, pero solo 1 sirve

`sinca.mma.gob.cl` declara la comuna de cada estación en un `<div class="comuna">`,
así que la asignación **no se infiere de coordenadas**: se lee del catálogo oficial.

Talcahuano (comuna **8110**) tiene cinco estaciones con macro de MP2.5. Se descargó la
serie diaria completa 2018-2024 de cada una y se miró en qué columna de validación cae
el dato:

| SINCA | Nombre | Validados | Preliminares | No validados | Veredicto |
|---|---|---|---|---|---|
| RVIII/802 | Consultorio - San Vicente | **2.427** | 52 | 31 | **utilizable** |
| RVIII/803 | Libertad | 0 | 0 | 0 | **sin serie** |
| RVIII/806 | Inpesca | 0 | 0 | 2.519 | solo no validados |
| RVIII/807 | Indura | 0 | 0 | 2.504 | solo no validados |
| RVIII/837 | Nueva Libertad | 0 | 0 | 2.522 | solo no validados |

**Solo `RVIII/802` publica datos validados.** Las otras tres con dato son estaciones de
la red industrial (Inpesca, Indura, Nueva Libertad) y todo su registro está en la
columna *no validados*. `Libertad` tiene macro publicado pero la serie viene vacía: el
caso "existe el recurso, no existe el dato" que la regla 5 del proyecto obliga a
distinguir.

Cobertura de la única estación utilizable: **2.427 de 2.556 días (95,0 %)**, repartidos
de forma pareja entre 2018 y 2024 (333 a 364 días por año).

### Comparación con el resto del Gran Concepción

| Comuna | SINCA | Nombre | Validados |
|---|---|---|---|
| Talcahuano | 802 | Consultorio - San Vicente | 2.427 |
| Concepción | 827 | Kingston College | 2.483 |
| Chiguayante | 854 | Punteras | 2.461 |
| Tomé | 830 | Liceo Polivalente | 2.445 |
| Coronel | 831 | Cerro Merquín | 2.441 |
| Hualqui | 841 | Hualqui | 2.367 |
| **Hualpén** | 804, 805, 838 | JUNJI, Bocatoma, ENAP Price | **0 — las tres solo no validadas** |

Hualpén merece mención aparte: se separó de Talcahuano en 2004, comparte la bahía de
San Vicente y el cordón industrial, y **ninguna de sus tres estaciones publica datos
validados**.

## 4.2 Talcahuano en OpenAQ

Cuatro de las cinco estaciones están en OpenAQ, con correspondencia uno a uno:

| OpenAQ | SINCA | Nombre |
|---|---|---|
| 2525 | RVIII/802 | Consultorio - San Vicente |
| 2473 | RVIII/837 | Nueva Libertad |
| 26 | RVIII/806 | Inpesca |
| 808 | RVIII/807 | Indura |

`Libertad` (RVIII/803) no está en OpenAQ, coherente con que no tenga serie. Recordar
que **OpenAQ no sirve como fuente** (§1.5): aquí solo confirma la correspondencia.

## 4.3 Talcahuano en DEIS

Cinco establecimientos con urgencias, estables durante todo el período (seis en 2021
por el traspaso SAPU→SAR descrito en §3.7):

| | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 |
|---|---|---|---|---|---|---|---|
| Establecimientos | 5 | 5 | 5 | 6 | 5 | 5 | 5 |
| Urgencias respiratorias | 75.568 | 70.439 | 13.992 | 13.671 | 54.804 | 59.084 | 52.853 |

Los cinco registran los 365 días del año casi sin excepción.

**Talcahuano es mejor que Temuco en el lado DEIS:** más volumen de urgencias
respiratorias (~70.000 vs ~52.000 en 2018-2019), cobertura estable y sin el salto
artificial de 2020. El único cuidado es el empalme SAPU/SAR Los Cerros y la migración
de códigos (§3.7).

## 4.4 Balance del cambio y decisión pendiente

| Aspecto | Temuco | Talcahuano |
|---|---|---|
| Estaciones SINCA con MP2.5 validado | 3 | **1** |
| Establecimientos DEIS | 5 → 11 (**salto**) | 5 (**estable**) |
| Urgencias respiratorias 2018-2019 | ~52.000 | **~73.000** |
| Cobertura diaria DEIS | completa | completa |

El cambio **mejora el lado salud y empeora el lado aire**. Talcahuano queda apoyado en
una sola estación de MP2.5, frente a las 12 de Santiago y las 2 de Coyhaique. Si esa
estación tiene un vacío largo, la ciudad se queda sin exposición para ese período; no
hay con qué rellenar dentro de la comuna.

**Decisión pendiente — cómo definir el ámbito espacial de Talcahuano:**

1. **Talcahuano estricto (comuna 8110).** Es lo que dice el alcance. Una estación
   (802), cinco establecimientos. Coherente pero frágil.
2. **Talcahuano + Hualpén (8110 + 8112).** Conurbación real y mismo cordón industrial.
   **No aporta ninguna estación validada** — las tres de Hualpén son no validadas — así
   que suma urgencias sin sumar exposición. Empeora la razón señal/ruido.
3. **Gran Concepción (8101-8112).** Seis estaciones validadas en seis comunas y ~200
   establecimientos. Es lo análogo a usar el Gran Santiago, y comparte cuenca
   atmosférica. Pero deja de ser "Talcahuano" y diluye justamente la señal industrial
   que motivó el cambio.

Recomendación: **opción 1**, con la estación 802 como serie de exposición, y dejar la
opción 3 documentada como análisis de sensibilidad. La 2 no se justifica: añade
población sin añadir medición.

Los códigos de comuna de las tres alternativas están en `COMUNAS_ALTERNATIVAS`
(`src/ingesta/reconocer_deis.py`), listos para reejecutar la cobertura con cualquiera.

**Pregunta abierta adicional:** ¿se pueden usar los datos *no validados* de las
estaciones industriales? Son ~2.500 días por estación y cubrirían el período completo
con tres puntos más. Pero mezclar validado con no validado en una misma serie exige
una regla escrita y, dado el hallazgo de OpenAQ, conviene saber qué significa
exactamente "no validado" en SINCA antes de usarlo. Esto entra en la Tarea 4.
