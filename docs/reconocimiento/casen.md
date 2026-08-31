# CASEN — combustible de calefacción del hogar

**Fecha de consulta:** 13 de agosto de 2026
**Reconocido con:** `src/ingesta/reconocer_casen.py`
**Estado:** cerrado para 2022. Otros años sin ruta verificada.

## 0. Qué aporta y qué no

CASEN no mide aire. Aporta el único dato del proyecto sobre la fuente de MP2.5
que está **dentro de la vivienda**: qué combustible usa cada hogar para
calefaccionar. Es el contexto que explica por qué las tres ciudades difieren.

**No es una serie temporal.** La encuesta no es anual y no es representativa a
nivel de comuna. Todo lo que salga de aquí es un descriptor regional y lento, no
una covariable que varíe semana a semana. Usarla como si variara en el tiempo
sería inventar variación que la encuesta no midió.

## 1. Acceso

```
https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/casen/2022/
    Base%20de%20datos%20Casen%202022%20STATA.dta.zip                 99,7 MB
    Base%20de%20datos%20provincia%20y%20comuna%20Casen%202022%20...   0,7 MB
```

HTTP 200, `application/zip`, **TLS válido** (no hace falta desactivar
verificación). El CGNAT no lo bloquea.

Los nombres llevan espacios y van con `%20`. La variante con guiones bajos
devuelve 404.

> **Años sin ruta verificada: 2015, 2017, 2020, 2024.**
> Existen como encuesta; lo que falta es su URL comprobada. Las páginas del
> Observatorio no exponen los enlaces en el HTML, así que hay que sacarlos a
> mano del navegador. `ARCHIVOS` en el script contiene **solo rutas
> comprobadas**, a propósito: un 404 de una URL adivinada dice que la URL estaba
> mal, no que el año no se publique, y tratar ambas cosas igual es el error que
> el proyecto se prohíbe.
>
> Ojo con 2020: es «Casen en Pandemia», con cuestionario reducido. Hay que
> comprobar que el módulo de vivienda exista antes de contarlo como año útil.

## 2. Formato

| | |
|---|---|
| Formatos ofrecidos | Stata `.dta`, SPSS `.sav`, R `.RData` — **no hay CSV** |
| ZIP | 99,7 MB |
| `.dta` descomprimido | **1.733,5 MB** |
| Ratio de compresión | **17,4×** |
| Variables | **917** |
| Filas | **202.231** (personas, no hogares) |

Se lee con `pandas.read_stata`. `pandas.io.stata.StataReader` expone el
diccionario de variables **sin cargar el archivo**, que es la única forma
razonable de explorar 1,7 GB.

> **Trampa — la misma que en SatPM2.5.**
> El ZIP trae `__MACOSX/._Base de datos Casen 2022 STATA.dta`, de 0 bytes y con
> extensión `.dta`. Es basura AppleDouble de macOS. Un extractor que tome «el
> primer `.dta`» puede quedarse con el archivo vacío. `reconocer_casen.py`
> descarta los miembros bajo `__MACOSX/` y los que empiezan por `._`, y se queda
> con el de mayor tamaño.
>
> Dos fuentes independientes con el mismo defecto: conviene tratarlo como patrón
> y no como caso aislado.

## 3. La variable

**`v34b` — «¿Qué combustible o fuente de energía usa habitualmente para
calefaccionar?»**

Detectada **por su etiqueta**, no por su nombre (regla 6): `reconocer_casen.py
variables` busca `calefacc` en las etiquetas de las 917 variables y devuelve una
sola candidata. El nombre cambia entre años; suponerlo es la forma conocida de
leer la columna equivocada sin enterarse.

Relacionadas: `v34a` (cocinar) y `v34c` (agua caliente).

Categorías, conteo nacional sin ponderar:

| Código | Categoría | n |
|---|---|---|
| 4 | **Carbón, leña o derivados (pellets, astillas…)** | **76.401** |
| 1 | Gas licuado (cilindro o tanque individual) | 41.225 |
| 8 | No tiene sistema | 30.084 |
| 5 | Electricidad | 18.848 |
| 3 | Parafina (kerosene) o petróleo | 17.137 |
| 7 | No usa combustible o fuente de energía | 10.366 |
| 2 | Gas por red (de cañería) | 8.002 |
| 6 | Energía solar | 168 |

> **La categoría 4 mezcla leña con pellets.** No son lo mismo para este estudio:
> el recambio de calefactores a pellet es justamente la intervención que evaluó
> el estudio de Coyhaique de 2020, y su efecto sobre el MP2.5 es distinto al de
> la leña húmeda. `v34b` **no permite separarlos**. Si esa distinción llega a
> importar, hay que buscarla en otra fuente.

## 4. Geografía — la limitación que manda

**En la base principal no hay variable de comuna.** Solo `region` y `estrato`
(comuna-área-NSE). La comuna vive en la base complementaria de 0,7 MB.

Y aunque se cruce, no sirve de mucho:

> **CASEN no es representativa a nivel comunal.** Las comunas no son dominio de
> estudio del diseño muestral; las estimaciones directas a ese nivel pueden ser
> imprecisas o sesgadas y el propio Observatorio no las recomienda. La
> representatividad es **nacional, regional y urbano/rural**. Para el nivel
> comunal, el Ministerio publica estimaciones de área pequeña (SAE), pero solo
> de pobreza — no de combustible de calefacción.

**Consecuencia adoptada:** se usa el nivel **regional**, y así debe reportarse.
El único factor de expansión presente en la base es `expr`, regional, lo que es
coherente.

Esto degrada distinto según la ciudad, y conviene decirlo:

- **Coyhaique**: la Región de Aysén es pequeña y Coyhaique concentra buena parte
  de su población, así que el dato regional se le parece bastante.
- **Santiago**: la Región Metropolitana incluye el Gran Santiago casi entero.
  Aceptable.
- **Talcahuano**: la Región del Biobío es grande y heterogénea, e incluye zonas
  rurales donde la leña es mucho más común que en una comuna portuaria e
  industrial. **Aquí el dato regional probablemente sobrestima** el uso de leña
  en Talcahuano. Es la ciudad donde este proxy es más débil, y coincide con ser
  la ciudad donde el dato de aire también es más débil.

## 5. Resultado — el gradiente

`% de personas que viven en viviendas cuya calefacción habitual es carbón, leña o
derivados`, ponderado por `expr`:

| Región | Ciudad | n muestral | n con leña | **% ponderado** |
|---|---|---|---|---|
| Aysén | **Coyhaique** | 3.747 | 3.165 | **82,5%** |
| Biobío | **Talcahuano** | 19.914 | 13.811 | **63,5%** |
| Metropolitana | **Santiago** | 38.674 | 2.281 | **3,6%** |

**Un gradiente de 23× entre Santiago y Coyhaique.** Es el modificador de efecto
que se buscaba: la misma concentración medida en una estación no significa la
misma exposición si en una región cuatro de cada cinco personas tienen una fuente
de combustión dentro de la casa y en otra la tiene una de cada veintiocho.

**Contraste externo.** La literatura reporta ~94% de uso de leña para la
población **urbana de Coyhaique**. Aquí sale 82,5% para **toda la Región de
Aysén**, que incluye comunas donde la penetración es menor. Los dos números son
compatibles y el orden de magnitud calza. La diferencia es de unidad geográfica,
no de error.

**Unidad, con precisión.** La base es de personas, no de hogares. La cifra es el
porcentaje de *personas* que viven en una vivienda que se calefacciona con leña,
no el porcentaje de *hogares*. Para lo que interesa aquí —exposición— la unidad
de personas es la más pertinente, pero no debe rotularse como «hogares».

## 6. Qué queda pendiente

1. **Verificar las URL de 2017 y 2024** para tener al menos dos puntos en el
   tiempo. Con un solo año no se puede saber si el gradiente se movió durante
   2018-2024, y los planes de descontaminación de Coyhaique operaron justo en
   ese período.
2. **Cruzar con la base complementaria de comuna** y reportar el n muestral de
   las comunas de Coyhaique y Talcahuano — no para usarlo como estimación, sino
   para dejar escrito cuán chico es y por qué no se usa.
3. **Buscar una fuente que separe leña de pellet**, si la distinción llega a
   importar. Candidata: el estudio de consumo nacional de leña del MMA.
4. **Escribir la regla en `docs/calidad/`** sobre qué nivel geográfico se usa y
   cómo se reporta, antes de que la cifra entre en ninguna tabla.

## 7. Preguntas abiertas

- ¿El `estrato` (comuna-área-NSE) permite recuperar comuna sin la base
  complementaria? Si el código de estrato lleva el código comunal embebido,
  saldría gratis. No se ha inspeccionado.
- ¿Existe factor de expansión de hogar además de `expr`? Haría falta si en algún
  momento se quiere la proporción de hogares y no de personas.
- ¿Cómo trata `v34b` a quien usa dos combustibles? La pregunta dice
  «habitualmente», lo que sugiere respuesta única, pero no está confirmado.
