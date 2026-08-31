# Corrección de coordenadas: Nueva Libertad estaba en Argentina

- **Fecha:** 2026-08-26
- **Aplica a:** `raw/coordenadas_intereses.csv`, origen de `dim_estacion`
- **Implementada en:** `src/procesamiento/estaciones.py`, constante `CORRECCIONES`
  y función `aplicar_correcciones`
- **Verificable con:** `python -m src.procesamiento.estaciones auditar --bucket <bucket> --perfil <perfil>`

## Qué se observó

La fila 240, `Estación Nueva Libertad`, declara longitud **-67.118855**. Las
otras tres estaciones de Talcahuano están en -73.1. Con -67.1 la estación cae
**en Argentina**, a unos 535 km de la comuna que dice tener.

Se auditaron las 21 filas cruzando la lat/lon declarada contra su propio UTM.
El resultado obliga a un matiz que la nota original del modelo no tenía:

> **Las 21 filas coinciden con su UTM a 0,0 km**, incluida la mala.

Es decir, las dos codificaciones **no son independientes**: una se derivó de la
otra. El UTM no sirve como testigo ingenuo — reproduce el error igual de bien
que reproduce los aciertos.

## Qué está mal realmente

No es un dígito traspapelado. Es el **huso**.

| | Valor |
|---|---|
| Easting declarado | `667962 E` |
| Huso declarado | **19** |
| Leído en huso 19 | longitud **-67.118855** ← lo que dice el archivo |
| Leído en huso 18 | longitud **-73.118855** ← el valor correcto |
| Diferencia | **exactamente 6.000000°** = el ancho de un huso UTM |

La lat/lon se calculó a partir de un easting válido leyendo el huso equivocado.
Un solo campo mal (`Huso`) produjo la longitud errónea.

### La evidencia que sostiene la corrección

1. **El huso contradice a la comuna.** Talcahuano está al oeste de -72° y
   corresponde al huso 18. Las otras tres estaciones de Talcahuano declaran 18.
2. **El easting encaja entre sus vecinas** en huso 18: Indura 668339,
   Inpesca 669252, Consultorio San Vicente 667557, San Vicente Bomberos 667625,
   Nueva Libertad 667962.
3. **La diferencia es exactamente el ancho de un huso**, no un valor arbitrario.
4. **La posición corregida es plausible.** Distancias a sus vecinas de comuna:

   | Vecina | Distancia |
   |---|---|
   | Inpesca | 1,30 km |
   | Consultorio San Vicente | 1,46 km |
   | San Vicente Bomberos | 1,64 km |
   | Libertad | 2,19 km |
   | Indura | 3,79 km |

## Regla adoptada

**El archivo crudo no se toca.** Ni en local, ni editando en S3, ni bajando y
volviendo a subir. Regla 3: la zona cruda es inmutable, y la política del bucket
la respalda (`raw/*` deniega `s3:DeleteObject`). Un archivo «arreglado» en
`raw/` deja de reproducir lo que entregó la fuente, y a partir de ahí ningún
reproceso es verificable.

La corrección vive en `CORRECCIONES`, en el código, con dos entradas para la
misma fila:

| ID | Campo | Crudo | Corregido |
|---|---|---|---|
| 240 | `Longitud` | `-67.118855` | `-73.118855` |
| 240 | `Huso` | `19` | `18` |

**Las dos son necesarias.** Corregir solo la longitud deja la fila
contradiciéndose a sí misma —lat/lon en Talcahuano, huso 19— y la auditoría se
niega a pasar, como debe.

### La corrección falla si el origen cambia

`aplicar_correcciones` comprueba que el valor crudo sea el esperado antes de
sustituirlo. Si el archivo se vuelve a descargar y el valor ya viene corregido,
la corrección se omite y se registra en el log. Si viene con un tercer valor
distinto, **el proceso se detiene**: aplicarla a ciegas escribiría un valor
arbitrario encima de un dato que nadie revisó.

## Qué NO se corrige

**Fila 127, `Estación Libertad`.** Declara huso 19 con easting `132748`, fuera
del rango válido de un huso (~160.000 a 834.000). Su lat/lon, en cambio, es
correcta: -36.717419, -73.111355, dentro de Talcahuano.

Se deja como está, registrada en `TOLERADAS`, por tres razones: la lat/lon es
buena, el UTM no viaja a la dimensión, y la estación **no tiene archivos de
datos** en el bucket. Documentar por qué se tolera importa tanto como corregir:
un aviso que siempre suena deja de leerse.

**El UTM no entra en `dim_estacion`.** Su único papel en el proyecto fue delatar
la fila 240. Para todo lo demás se usa lat/lon.

## Hallazgos laterales del mismo trabajo

**El catálogo tiene 21 filas y solo 19 estaciones tienen datos.** Sobran
`Libertad` (127) y `San Vicente, Bomberos` (91), ambas de Talcahuano.
`dim_estacion` las conserva con `tiene_datos = false` en vez de descartarlas:
saber que existen y no se midieron es información, borrarlas es perderla.

**El cruce por nombre no es literal.** De los 20 nombres de estación que
aparecen en los archivos de SINCA, **16 coinciden literalmente con el catálogo y
20 coinciden normalizando**. Los cuatro que fallan: `Estacion Coyhaique` y
`Estacion Coyhaique II` sin tilde en el archivo, y `Estación Consultorio San
Vicente` frente a `Estación Consultorio - San Vicente` con guion en el catálogo.
La misma estación llega escrita con y sin tilde dentro de la misma carpeta.

`normalizar_nombre` quita acentos, mayúsculas, `(Acreditada)` y puntuación.
**No normaliza más:** quitar `Consultorio` haría colisionar la fila 241 con la
91, que está a 210 m y es otra estación. La auditoría comprueba que no haya
colisiones tras normalizar.

**Una fila lleva coma dentro de comillas.** `"Estación San Vicente, Bomberos"`,
en un archivo separado por comas. Un `split(",")` ingenuo devuelve 9 campos en
vez de 8 para esa fila y desplaza todas sus columnas. Se lee con el módulo
`csv`, que respeta el entrecomillado.

## Alternativas descartadas

- **Editar el CSV.** Rompe la regla 3 y la política del bucket lo impide.
- **Subir un `coordenadas_intereses_corregido.csv` a `raw/`.** Deja dos archivos
  con autoridad ambigua; el siguiente que llegue no sabrá cuál usar.
- **Corregir solo la longitud.** Deja la fila internamente incoherente.
- **Descartar la estación.** Es una de las cuatro de Talcahuano y tiene 98,9% de
  cobertura de MP2.5: la mejor de la ciudad. Perderla por un campo mal escrito
  sería el peor de los desenlaces.
