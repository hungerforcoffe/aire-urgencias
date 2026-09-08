# Resultados del modelo: validación y publicación en el sitio

- **Fecha:** 2026-09-06
- **Aplica a:** `sitio/assets/datos/modelo.json` y la mitad superior de
  `sitio/analisis.html`.
- **Implementada en:** `src/sitio/exportar_modelo.py`
- **Verificable con:** `python -m src.sitio.exportar_modelo --verificar`

## Qué llegó

Once archivos (un README, diez CSV, 40 kB) desde el cuaderno de análisis del
equipo: los RR e intervalos del modelo principal, por ciudad, por edad, los
rezagos 0–7, las sensibilidades, el placebo temporal y los controles negativos.

El diseño es un **case-crossover estratificado por tiempo**, con Poisson
condicional sobre conteos diarios, estratos de `ciudad × año × mes × día de la
semana`, y ajuste por temperatura (spline natural), humedad y la actividad viral
del ISP. Exposición: MP2.5 diario. Los RR se expresan por cada +10 µg/m³.

## Por qué se publican precomputados

GitHub Pages sirve archivos y no ejecuta código. El sitio **no puede ajustar una
Poisson condicional**, así que la única forma de mostrar inferencia es traerla
hecha. Eso no es una limitación del sitio: es la razón por la que estos 40 kB de
CSV son exactamente lo que necesitaba.

La entrega original venía rotulada para una app Streamlit. La arquitectura del
proyecto es otra, pero el formato sirve igual y sin backend.

## `escala` no estaba en el diccionario, y sí importaba

Seis de los diez CSV traen una columna `escala` que el diccionario de variables
no define. Es el **factor de sobredispersión cuasi-Poisson** del ajuste, y la
pregunta que importaba era si los intervalos ya venían escalados por él: sin
escalar serían mucho más angostos de lo correcto y todo el conjunto se leería
como más preciso de lo que es.

Se confirmó con el equipo y **se comprobó contra los propios números**. Si la
corrección está aplicada, `SE · √(N/φ)` debe ser constante entre modelos que
comparten exposición y estratos. Los cinco grupos etarios cumplen justo esa
condición:

```
grupo     SE        SE·√N     SE·√(N/φ)
<1        0.00214   1.561     0.947
1–4       0.00225   2.758     0.940
5–14      0.00276   3.724     0.957
15–64     0.00172   3.451     0.995
65+       0.00187   1.669     1.000
```

Con la corrección, los cinco colapsan a un mismo valor (6 % de dispersión); sin
ella se abren en un factor de 2,4. **Los intervalos vienen escalados.**

Como control adicional, `φ ≈ media · CV²` da un coeficiente de variación
residual de 0,16 a 0,28 en los ocho modelos, que es el orden esperable para
conteos diarios de urgencias. La columna es lo que dice ser.

Las ciudades no colapsan igual (Coyhaique 0,296 contra Santiago 1,140) y eso
**no es una inconsistencia**: cada ciudad tiene su propia serie de exposición, y
el MP2.5 de Coyhaique varía muchísimo más. Más contraste por día es más
información por caso — por eso Coyhaique tiene el intervalo más angosto de las
tres pese a aportar 145.200 consultas contra 8,2 millones de Santiago.

## Qué valida el exportador antes de publicar

Regla 5: que un CSV se lea no significa que sirva. `validar()` rechaza si:

| Chequeo | Umbral | Por qué |
|---|---|---|
| Número de filas | exacto por archivo | Un archivo truncado no se nota: las columnas siguen bien. |
| `rr10` en rango | 0,90 a 1,20 | Un RR por +10 µg/m³ vive en centésimas. Fuera de ahí no hay hallazgo, hay cambio de unidad en la exposición. |
| El IC contiene al RR | `ic_inf ≤ rr10 ≤ ic_sup` | Un error de armado que a ojo no se ve: los tres números parecen normales por separado. |
| `convergio` | todas verdaderas | Un ajuste que no converge entrega coeficientes igual. |
| Ciudades | exactamente las tres | Si mañana se agrega una cuarta, el sitio la mostraría a medias o la omitiría en silencio. |

## Los controles negativos no dieron nulos

Es el hallazgo incómodo y **se publica en la página, no en una nota al pie**.

```
traumatismos             +1,15 %   (IC +0,88 a +1,42)   4.348.004 casos
accidentes de tránsito   +1,44 %   (IC +0,37 a +2,53)      82.720 casos
respiratorias            +0,81 %   (IC +0,47 a +1,15)
```

Un control negativo es un desenlace que la exposición no puede provocar:
respirar partículas no fractura un hueso ni provoca un choque. Debería dar 0 %.
Da **más que el desenlace de interés**, así que mide sesgo, no aire.

La explicación más plausible es meteorológica y no administrativa: los días de
alto MP2.5 son días de inversión térmica —fríos, sin viento, con niebla—, y ese
mismo patrón produce caídas y choques por vías que no pasan por los pulmones. El
ajuste por temperatura media diaria no captura hielo en el suelo ni visibilidad.

**Consecuencia editorial:** la página no puede presentar el 1,0192 acumulado
como un resultado limpio. El panel «Las dos pruebas que no salieron limpias»
muestra los controles junto al placebo temporal y dice explícitamente que no se
puede separar cuánto del resultado es aire. Es la justificación numérica de la
regla 1 del proyecto, y vale más mostrarla que esconderla.

El indicador de cabecera usa **traumatismos**, no el RR más alto: 4,3 millones
de casos y un intervalo estrecho lo hacen la evidencia firme, mientras que
tránsito (82.720 casos, IC cuatro veces más ancho) es el número llamativo.

## Lo que cambió en la página

`analisis.html` afirmaba, antes de esto, que los tres intervalos incluían el cero
y que **«no se incorporó la vigilancia del ISP, así que queda declarado y no
corregido»**. Lo segundo dejó de ser cierto el mismo día en que el ISP entró al
catálogo (ver `isp_virus.md`), y lo primero quedó superado.

El análisis semanal **no se borró**: pasó a ser la primera mitad de la historia,
bajo el título «Por qué la semana no bastaba». No estaba equivocado, medía otra
cosa. A resolución semanal, con descuento estacional simple y sin control viral,
la asociación no se distinguía de cero; a resolución diaria, con comparación
dentro del mismo mes y día de semana, aparece. La curva de rezagos lo confirma:
casi todo está en el día 0 y se apaga al segundo.

**El hallazgo metodológico es ese** — la resolución temporal decidía el
resultado — y es más valioso que el RR mismo.

## Trazabilidad

Los CSV originales quedan inmutables en `data/raw/modelo/`, incluido
`00_README_HANDOFF.md` con las instrucciones de quien los produjo y
`11_manifest_archivos.csv`. El JSON publicado es derivado y se reconstruye
entero desde ahí.

## Pendiente con quien produjo los resultados

1. **Curva de rezagos de los controles negativos.** Es el test que separa las
   aguas: si traumatismos sale plano en los ocho rezagos, el sesgo es un piso
   constante y la *forma* de la curva respiratoria sigue siendo información; si
   sale con pico en el día 0, la forma tampoco discrimina. Hoy no lo tenemos.
2. **Cinco columnas sin definir** en el diccionario: `escala` (ya aclarada acá),
   `n_estratos`, `casos`, `convergio` y `significativo`.
3. **`actividad_viral_clasica_100` entra como columna lineal.** `_extras()` en
   `src/analisis/asociacion.py` reserva el spline para la temperatura. Probarla
   como spline sigue siendo una sensibilidad pendiente.
