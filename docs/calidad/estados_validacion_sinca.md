# Los tres estados de validación de SINCA se cargan como dato válido

- **Fecha:** 2026-08-26
- **Aplica a:** SINCA, MP2.5 horario. Afecta a `hecho_medicion`, a `agg_aire_dia`
  y por arrastre a `analitico_ciudad_semana`
- **Implementada en:** el lector de SINCA (`src/procesamiento/`, pendiente) y en
  la ausencia de filtro por `estado_validacion` en `agg_aire_dia`
- **Decidida por:** el equipo, sobre el comentario de revisión del modelo

## Qué se observó

Los 19 archivos de MP2.5 traen la cabecera

```
FECHA (YYMMDD);HORA (HHMM);Registros validados;Registros preliminares;Registros no validados;
```

Las tres columnas son **excluyentes**. Verificado sobre los 19 archivos completos
dentro de la ventana 2018-01-01 → 2026-08-22: **0 filas con valor en más de una
columna y 0 pares (fecha, hora) repetidos**. El supuesto de exclusividad no es
una lectura de la documentación, está comprobado.

El reparto entre estados no es homogéneo. Hay dos regímenes distintos:

| Régimen | Estaciones | Validados | Preliminares | No validados |
|---|---|---|---|---|
| Normal | las 15 con dato en Santiago y Coyhaique, más Consultorio San Vicente | 93–99% | ~1% | <1% |
| Sin validar nunca | Indura, Inpesca, Nueva Libertad (Talcahuano) | **0** | **0** | **100%** |

Las tres estaciones del segundo régimen acumulan 355.101 mediciones y **ni una
sola validada en catorce años**. No es que falte validación reciente: SINCA
nunca ha validado esas series.

Filtrar por `estado_validacion = 'validado'`, que era la regla anterior, deja a
Talcahuano con **una sola estación** y 92,7% de cobertura, frente a once
estaciones en Santiago y dos en Coyhaique.

## Regla adoptada

**Las tres columnas se cargan como medición válida.** No hay filtro por
`estado_validacion` en ninguna etapa del pipeline, ni en la ingesta, ni en
`agg_aire_dia`, ni en la tabla analítica.

La columna `estado_validacion` **se conserva en `hecho_medicion`** con su valor
real (`validado` / `preliminar` / `no_validado`). No se carga como constante ni
se descarta: es lo que hace reversible esta decisión.

## Por qué

Dos razones, y la segunda es la que sostiene la primera.

**1. Conveniencia, declarada como tal.** El equipo no dispone del tiempo ni del
instrumental para hacer la validación por su cuenta. Ese es el motivo real y va
escrito así en el informe: *«se tomó por conveniencia»*. No se presenta como
criterio metodológico ni se le busca respaldo normativo que no tiene.

**2. El dato sin validar se comporta como dato validado.** Antes de aplicar la
regla se contrastó, sobre medias diarias con al menos 18 horas de dato:

| Par | r de Pearson | n (días) |
|---|---|---|
| Nueva Libertad (0% val.) vs Consultorio San Vicente (92% val.) | **0,827** | 3.061 |
| Inpesca (0% val.) vs Consultorio San Vicente | **0,928** | 3.057 |
| Indura (0% val.) vs Consultorio San Vicente | **0,820** | 3.038 |

El contraste que da sentido a esas cifras son los pares **validado contra
validado** de Santiago, donde nadie discute la calidad:

| Par de control | r de Pearson |
|---|---|
| La Florida vs Puente Alto | 0,954 |
| La Florida vs Parque O'Higgins | 0,935 |
| Cerro Navia vs Parque O'Higgins | 0,928 |
| Cerro Navia vs Puente Alto | 0,800 |

Las estaciones sin validar de Talcahuano correlacionan con su vecina validada
**dentro del mismo rango** que dos estaciones validadas de Santiago entre sí
(0,80–0,95). La distribución tampoco delata nada: mediana 9–13 µg/m³, p99
124–277, máximo 915–989, **cero valores negativos**. El máximo más alto de todo
Talcahuano (2.000 µg/m³) está en Consultorio San Vicente, que sí está validada.

Dicho de otro modo: si el dato no validado fuera ruido, no seguiría a la
estación validada de su misma ciudad durante 3.000 días.

## Qué se gana y qué se pierde

**Se gana**, en horas de MP2.5 dentro de la ventana:

| Ciudad | Solo validado | Los tres estados | Cambio |
|---|---|---|---|
| Talcahuano | 70.243 (1 estación) | **297.385 (4 estaciones)** | ×4,2 |
| Santiago | 695.422 | 706.696 | +1,6% |
| Coyhaique | 147.391 | 150.287 | +2,0% |
| **Total** | 913.056 | **1.154.368** | +26,4% |

**Se pierde** la garantía de calidad que da la validación de SINCA sobre el 21%
de las horas resultantes. Concentrada, además: casi toda la ganancia es
Talcahuano. En Santiago y Coyhaique la regla cambia menos de dos puntos, así que
allí es casi irrelevante — **la decisión es, en la práctica, una decisión sobre
Talcahuano.**

Eso tiene una consecuencia que hay que declarar en el informe: las tres ciudades
no quedan en pie de igualdad. Santiago y Coyhaique se sostienen en datos
validados por el organismo; Talcahuano, mayoritariamente no.

## Cómo se revierte

Como `estado_validacion` sigue en `hecho_medicion`, el análisis de sensibilidad
es una cláusula:

```sql
-- rehacer la asociación solo con dato validado
WHERE estado_validacion = 'validado'
```

**Ese análisis es obligatorio antes de cerrar el informe.** Si el coeficiente de
asociación de Talcahuano cambia de signo o de magnitud al restringir a dato
validado, el resultado depende de esta decisión de conveniencia y hay que
decirlo. Si no cambia, la decisión no afectó la conclusión y también hay que
decirlo. En Santiago y Coyhaique se espera que no cambie nada, porque el
material afectado es menos del 2%.

## Alternativas descartadas

- **Filtrar a `validado`** (regla anterior). Deja Talcahuano con una estación y
  convierte en limitación estructural algo que el contraste muestra innecesario.
- **Cargar los tres estados y ponderar por estado.** Los pesos serían inventados:
  no hay base para decir que un dato preliminar vale 0,7 de uno validado.
- **Usar las tres estaciones solo para rellenar huecos de San Vicente.** Mezcla
  regímenes de calidad dentro de una misma serie sin dejar rastro en la fila,
  que es exactamente lo que la regla 5 del proyecto prohíbe.
- **Imputar.** Fuera de alcance y peor: fabrica variación que nadie midió.

## Nota sobre la variante V1

El comentario que originó esta decisión afirmaba que la columna sin nombre de la
variante V1 (`FECHA;HORA;;`) es MP2.5 validado. **En los archivos que hay en el
bucket no es así:** los 19 archivos de MP2.5 traen cabecera V2, y los 62 de
variante V1 son todos meteorología — temperatura, humedad, dirección y velocidad
del viento. No hay ningún MP2.5 con cabecera V1.

Lo que sí es cierto, y es lo que importa para el modelo: **la columna sin nombre
de V1 no trae estado de validación**, así que la meteorología —que son las
variables de control del estudio— entra entera sin filtro posible. En eso la
regla nueva y la vieja coinciden; lo que cambia es que ahora el MP2.5 se trata
igual que su meteorología en vez de con un criterio más estricto.

El cruce nombre-cabecera se mantiene como chequeo: si un archivo dice «MP2.5» y
llega con cabecera V1, o dice meteorología y llega con V2, se rechaza. Hoy los
81 archivos de estación pasan ese cruce.
