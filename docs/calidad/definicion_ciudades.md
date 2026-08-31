# Qué comunas y qué estaciones son cada ciudad

- **Fecha:** 2026-08-26
- **Aplica a:** `dim_ciudad`, `puente_estacion_ciudad`, y por arrastre a todo
  agregado por ciudad
- **Implementada en:** `src/procesamiento/ciudades.py`, constantes `CIUDADES` y
  `COD_COMUNA`, función `auditar`
- **Estado:** decisión 1 **tomada el 2026-08-26**; `dim_ciudad` construida.
  Quedan abiertas la 2 (Hualpén) y la 3 (población), y ninguna bloquea.

## Por qué esto no es un detalle administrativo

Una ciudad no existe en los datos. Existe dos veces, y por separado:

- del lado de la **salud**, como un conjunto de **comunas** (el DEIS trae código
  de comuna por establecimiento);
- del lado del **aire**, como un conjunto de **estaciones** de SINCA.

Si los dos conjuntos no describen el mismo territorio, el estudio correlaciona
el MP2.5 de un sitio con las urgencias de otro. El resultado sale, se grafica y
no hay nada en él que lo delate.

Por eso `ciudades.py` cruza las dos definiciones y falla si discrepan.

## Decisión 1 — Talagante no es Santiago · TOMADA

El cruce encontró **una** discrepancia entre las 19 estaciones con datos y las
comunas de las tres ciudades:

```
Estación Talagante: está en Talagante (13601),
que NO es una de las 34 comunas de santiago
```

`COMUNAS_CIUDAD["Santiago"]` en `src/ingesta/reconocer_deis.py` son las 32
comunas de la Provincia de Santiago más Puente Alto (13201) y San Bernardo
(13401). Talagante es 13601, Provincia de Talagante. No está.

### Lo que dicen los datos

| Estación | Distancia a Parque O'Higgins |
|---|---|
| Cerrillos II | 4,5 km |
| Independencia | 4,7 km |
| Cerro Navia | 7,5 km |
| Pudahuel | 8,8 km |
| La Florida | 8,9 km |
| El Bosque | 9,6 km |
| Quilicura | 14,0 km |
| Puente Alto | 15,4 km |
| Las Condes | 16,0 km |
| **Talagante** | **35,7 km** |

Talagante está a **más del doble** que la siguiente más lejana. No es periferia
del Gran Santiago: es otra localidad, separada por terreno agrícola. Su
cobertura de MP2.5 en la ventana es 81,1%, la segunda más baja de las
utilizables, y su mediana (14 µg/m³) es la más baja de Santiago.

### Lo decidido

**Estación Talagante queda fuera de Santiago.** Razonamiento del equipo: tiene
sensor de SINCA y por eso «entre comillas sirve», pero como no es Santiago
propiamente tal sería otro dato y metería ruido.

### Cómo se implementó, y por qué así

`ciudad_de()` ya no asigna Santiago por descarte. Ahora la pertenencia se decide
por **código de comuna** contra el conjunto de cada ciudad, y una comuna que no
está en ninguno devuelve `None`.

En consecuencia, en `dim_estacion` la fila 197 queda con:

```
ciudad_id = NULL
nota      = "Comuna 13601, fuera de las 34 que definen Santiago…"
```

**La estación no se borra.** Sigue en la dimensión, con `tiene_datos = true`,
sus coordenadas y su nota. Perder el registro de que existe y se descartó sería
peor que descartarla.

El detalle que importa es *por qué `NULL` y no una bandera*. Con `ciudad_id`
apuntando a Santiago más una columna `en_alcance`, una consulta que filtre
`WHERE ciudad_id = 'santiago'` y se olvide de la bandera **vuelve a meter
Talagante** — justo el ruido que la decisión quería evitar. Con `ciudad_id`
nulo, el descuido la excluye solo. La opción segura es la que protege al
distraído.

`FUERA_DE_ALCANCE`, en `src/procesamiento/geografia.py`, guarda el motivo junto
a la exclusión, y la auditoría distingue entre **problema** y **exclusión
declarada**: si aparece una estación fuera de toda ciudad *sin* motivo escrito,
eso sí es un problema y detiene la construcción. Una auditoría que suena en rojo
para siempre deja de leerse.

### Resultado

| Ciudad | Comunas | Estaciones con datos | Excluidas |
|---|---|---|---|
| Santiago | 34 | **12** (antes 13) | 1 |
| Talcahuano | 1 | 4 | 0 |
| Coyhaique | 1 | 2 | 0 |

`dim_ciudad` lleva `n_estaciones_excluidas` para que la decisión viaje con la
tabla y no haya que ir al código a recordarla.

**La alternativa descartada** —añadir 13601 a las comunas de Santiago— obligaba
a añadir también las demás comunas provinciales y cambiaba mucho el denominador
poblacional.

## Decisión 2 — Talcahuano solo, o Talcahuano con Hualpén

`COMUNAS_CIUDAD["Talcahuano"]` es `{8110}`: la comuna sola.
`reconocer_deis.py` ya contempla dos alternativas:

| Definición | Comunas |
|---|---|
| `Talcahuano` (actual) | 8110 |
| `Talcahuano_con_Hualpen` | 8110, 8112 |
| `Gran_Concepcion` | 8101 a 8112 |

Hualpén se separó de Talcahuano en 2004 y la conurbación es continua. El
catálogo nacional de SINCA tiene una estación ahí —`Estación ENAP Price`— que
**no está descargada**.

Eso hace la decisión asimétrica: añadir Hualpén sumaría población y urgencias
del lado de la salud **sin sumar ninguna estación** del lado del aire, salvo que
antes se descargue ENAP Price. La cobertura de aire quedaría representando un
territorio más grande del que mide.

### Recomendación

**Mantener Talcahuano = 8110** mientras no se descargue la estación de Hualpén.
Las cuatro estaciones actuales están todas dentro de la comuna 8110, así que hoy
las dos definiciones cuadran. Si el equipo quiere la conurbación, el orden
correcto es: descargar ENAP Price primero, ampliar la definición después.

## Decisión 3 — la población, que hoy no existe

`dim_ciudad` se construye con `poblacion = None` en las tres ciudades.

Sin denominador no se comparan 1,4 millones de urgencias en Santiago con 24 mil
en Coyhaique: la ciudad grande gana siempre y la comparación no dice nada. Con
población, es probable que Coyhaique domine.

Ninguna fuente del proyecto la tiene:

- **CASEN** es una encuesta. `docs/reconocimiento/casen.md` advierte que su
  representatividad comunal es limitada. Sirve para el % de leña regional, no
  para poblacion comunal.
- **Censo 2017 (INE)** la tiene, y no está descargado.

Se deja explícitamente en nulo. **Una población inventada sería peor que
ninguna:** las tasas por 100.000 saldrían plausibles y estarían mal, y nadie
podría notarlo mirando el resultado.

Queda pendiente decidir además **de qué año**: Censo 2017 es un dato medido pero
tiene nueve años; las proyecciones INE 2026 son estimaciones. Para una ventana
2018-2026 conviene, o bien población proyectada por año, o bien una población
fija declarada como tal.

## Lo que sí está fijado

| Ciudad | Comunas | Estaciones con datos | % leña (CASEN, regional) |
|---|---|---|---|
| Santiago | 34 | 13 | 3,6% |
| Talcahuano | 1 | 4 | 63,5% |
| Coyhaique | 1 | 2 | 82,5% |

El `% leña` es **regional, no comunal**, y así hay que citarlo. Para Coyhaique
la literatura reporta ~94% en población urbana frente al 82,5% regional de aquí:
la región incluye zonas rurales y localidades pequeñas. Está discutido en
`docs/reconocimiento/casen.md`.
