# La escala de color del MP2.5 es el ICAP del D.S. 12/2011, no una escala propia

- **Fecha:** 2026-09-01
- **Aplica a:** todo color que represente una concentración de MP2.5 en el sitio
  público: círculos del mapa, rampa de la leyenda, puntos de la barra lateral,
  marcas del meteograma y pétalos de la rosa de contaminación.
- **Implementada en:** `sitio/assets/js/comun.js` (`icap`, `tono`, `peldano`,
  `CATEGORIAS`, `REFERENCIAS`) y los tokens `--icap-*` de
  `sitio/assets/css/estilo.css`.
- **Verificable con:** comparar `AU.icap(c)` contra el campo `icap` que publica
  `https://sinca.mma.gob.cl/index.php/json/listadomapa2k19/`.

## Qué se observó

La escala anterior la eligió el proyecto: seis peldaños en las guías anuales de
la OMS 2021 (5 / 10 / 15 / 25 / 35 µg/m³) con una paleta propia. Es defendible,
pero no es la que usa nadie más en Chile, así que un lector que conoce el mapa de
SINCA no podía comparar los dos.

Chile **sí** tiene una escala legal, y está en el **D.S. N°12/2011 del Ministerio
del Medio Ambiente**:

- **Art. 2º letra l)** define el ICAP2,5 como una función lineal por tramos
  anclada en tres puntos: ICAP 0 = 0 µg/m³N, ICAP 100 = 50, ICAP 500 = 170.
- **Art. 5º** fija los niveles de episodio: Alerta 80–109, Preemergencia
  110–169, Emergencia ≥170, que caen en ICAP 200, 300 y 500.
- **Art. 3º** fija la norma: **50 µg/m³ en 24 horas y 20 µg/m³ anual**.

De las anclas se despeja la fórmula:

```
ICAP = 2·C                  si C ≤ 50
ICAP = 100 + (C − 50)·10/3  si C > 50
```

Comprobada contra tres estaciones de la API de SINCA el 2026-09-01:

| Estación | MP2.5 | ICAP que publica SINCA | Fórmula |
|---|---|---|---|
| Alto Hospicio | 3 | 6 | 6,0 |
| Valdivia | 54 | 113 | 113,3 |
| Universidad de Los Lagos | 86 | 220 | 220,0 |

## Regla adoptada

1. **El color de una concentración se calcula con el ICAP**, interpolando de
   forma continua entre los cinco colores oficiales. No hay peldaños: la función
   del decreto es continua y dibujarla a escalones insinuaría saltos que la ley
   no tiene.
2. **Los colores son los de SINCA**, en su paleta de marcadores de mapa.
3. **La interpolación es en OKLab**, no en sRGB.
4. **Esos colores no se usan nunca como color de texto.** Donde había un número
   coloreado ahora hay un punto de color y el número en tinta.
5. **Las líneas de referencia de los gráficos son los umbrales que la ley
   nombra** —20, 50, 80, 110, 170— y no una retícula de números redondos.

## Por qué esos valores, y la advertencia que no se puede omitir

**El ICAP está definido sobre la concentración de 24 horas. El mapa de este sitio
pinta medias mensuales.** No son la misma magnitud, y la diferencia importa: una
media mensual de 45 µg/m³ se pinta verde —«Bueno» en la escala de 24 h— cuando en
realidad es **más del doble de la norma anual**, que el mismo decreto fija en 20.

La decisión de usar igual el ICAP se tomó a sabiendas, por comparabilidad con
SINCA. La consecuencia se compensa así:

- La leyenda del mapa lo dice con todas sus letras.
- La rampa marca los **20 µg/m³ de la norma anual** junto a los umbrales de 24 h.
- El radio del círculo sigue siendo proporcional al valor, así que la magnitud se
  puede leer aunque el color no la distinga.

## Qué se pierde

**Resolución en el tramo bajo, que es donde vive casi todo el país.** El ICAP
comprime 0–50 µg/m³ en un quinto de la escala, así que entre Las Condes (18) y
Pudahuel (28) hay 20 puntos de ICAP sobre 500 y el color casi no cambia: en agosto
de 2026 las diez estaciones de Santiago se ven del mismo verde. Con la escala
anterior, esos mismos valores caían en peldaños distintos.

Es el costo aceptado a cambio de que el color signifique lo mismo acá y en el
mapa oficial. Quien necesite comparar dentro de una ciudad tiene el tamaño del
círculo, el meteograma y la tabla año por año.

## Alternativas descartadas

- **Aplicar los cortes de 24 h como peldaños discretos a la media mensual.** Es
  lo más literal, y deja el mapa de Chile prácticamente verde entero: se pierde
  toda la información que hoy transmite.
- **Mantener la escala de la OMS.** Tiene mejor resolución en el tramo bajo y sus
  guías anuales sí son comparables con una media larga, pero no es la escala
  legal chilena y no permite comparar con SINCA.
- **La otra paleta oficial de SINCA**, la de estado de estación (`#2eae00`,
  `#fbff00`, `#ff7d1c`, `#ff0931`, `#46016b`). Se descartó por contraste: su
  amarillo da **1,08:1** sobre fondo claro y su morado **1,14:1** sobre el azul
  marino del tema oscuro; en ambos casos el color desaparece. La paleta de
  marcadores, igual de oficial, tiene 3,78:1 en el peor caso.

## Vigencia

El D.S. 12/2011 sigue vigente. Una norma nueva —15 µg/m³ anual, 38 en 24 h, con
episodios en 68 / 98 / 158— fue aprobada por el Consejo de Ministros en diciembre
de 2025, pero el Gobierno **retiró el decreto desde Contraloría en marzo de 2026**
antes de su publicación, así que nunca entró en vigor.

Por eso los cortes viven en un solo sitio (`CATEGORIAS` en `comun.js`) y no
repartidos por el código: si la norma cambia, se edita una tabla.
