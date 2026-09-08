# Cómo se presentan las figuras del sitio

- **Fecha:** 2026-09-08
- **Aplica a:** `sitio/analisis.html` y los gráficos de `modelo.js`,
  `analisis.js` y `semanal_nt.js`
- **Implementada en:** bloque `/* figuras */` de `sitio/assets/css/estilo.css` y
  `AU.figura()` en `sitio/assets/js/comun.js`

## Qué se observó

La primera versión de la página integrada dibujaba los gráficos con los tokens
de color del tema (`--s1`, `--tinta`, `--panel`). En el tema oscuro eso los
volvía indistinguibles del panel que los contenía: los ejes eran del mismo gris
que el borde de la tarjeta y el fondo del gráfico era el fondo de la página.

El efecto es que **se pierde la frontera entre lo que es dato y lo que es
diseño**. Un lector no puede decir dónde termina el gráfico. Y son gráficos que
llevan intervalos de confianza y valores p: si no se leen como un objeto
técnico, sus advertencias tampoco se leen.

## Regla adoptada

**Los gráficos no siguen el tema de la página.** Van sobre una lámina clara
fija, con marco, número de figura correlativo y pie con la fuente o la
advertencia metodológica.

Los tokens `--fig-*` se declaran una sola vez, sobre la clase `.fig`, y **no se
redefinen en los bloques de tema oscuro**. Si alguien los agrega allí, la lámina
deja de ser una lámina.

| Token | Valor | Uso |
|---|---|---|
| `--fig-sup` | `#fcfbf8` | superficie |
| `--fig-tinta` | `#16181b` | rótulos y valores |
| `--fig-tinta-2` | `#585d63` | texto de eje |
| `--fig-tinta-3` | `#8b8f95` | ticks y marcas finas |
| `--fig-linea` | `#d5d2c9` | marco y ejes |
| `--fig-rejilla` | `#eae7e0` | rejilla interior |
| `--fig-s1` | `#1c5fa8` | serie 1 — MP2.5, estimaciones |
| `--fig-s2` | `#c2481a` | serie 2 — urgencias |
| `--fig-s3` | `#1a7f5a` | serie 3 — temperatura |
| `--fig-alerta` | `#b3261e` | lo que no debería estar ahí |
| `--fig-sombra` | `#ece9e2` | franjas de contexto (invierno) |

Contraste sobre `#fcfbf8`: `--fig-s1` 6,5:1, `--fig-s2` 4,9:1, `--fig-tinta`
17:1. Los tres pasan AA para texto. `--fig-tinta-3` (2,9:1) se usa solo para
ticks y marcas, nunca para texto que haya que leer.

## Por qué esa regla y no otra

Se evaluó una superficie propia que siguiera el tema —oscura en modo oscuro—.
Separa del panel, pero mantiene dos problemas: el gráfico sigue cambiando de
aspecto según quién lo mire, y no se puede exportar ni imprimir sin rehacerlo.
La lámina fija resuelve los dos: **una figura es la misma figura en cualquier
contexto**, que es la convención de cualquier informe técnico.

El costo es que en modo claro la lámina y el fondo de la página quedan cerca en
luminosidad. Lo resuelve el marco de 1 px, comprobado en ambos temas.

## El número de figura lo cuenta el CSS

`counter-increment: figura` sobre `.fig` y `content: "Fig. " counter(figura)` en
la cabecera. **No se lleva en JavaScript**, por dos razones:

1. Los paneles se repintan cada vez que se mueve un control de la página, y un
   contador en JS seguiría subiendo hasta «Fig. 47».
2. Tres scripts distintos escriben figuras en la misma página y ninguno sabe
   cuántas lleva el anterior.

El contador de CSS cuenta posiciones en el documento, que es lo correcto, y se
recalcula solo cuando el contenido cambia.

## Estructura de una figura

```
<figure class="fig">
  <div class="fig-cab"><b></b><span>Título</span></div>   ← el número lo pone el CSS
  <div class="fig-clave">…</div>                          ← leyenda, opcional
  <div class="fig-cuerpo">SVG o tabla</div>
  <div class="fig-pie">fuente, n, advertencia</div>
</figure>
```

Las **tablas reciben el mismo trato que los gráficos**: son la misma clase de
objeto —un resultado que hay que poder citar— y van dentro de una lámina con su
número y su pie.

## Decisiones de composición

- **Una sola columna de lectura** (880 px), no una grilla de tarjetas. La grilla
  dejaba huecos cada vez que un panel ocupaba el ancho completo, y obligaba a
  leer en zigzag. Con una columna el orden del documento es el orden de lectura.
- **`.fig-par`** para dos figuras que se leen juntas; bajo ~660 px se apilan.
- **Los textos entre figuras son cortos a propósito**: la figura es el
  argumento, el párrafo solo dice qué mirar. La versión anterior tenía párrafos
  de ocho líneas bajo cada gráfico y el conjunto se leía como un ensayo.
- **Cada figura declara de qué análisis viene** (`.fuente`), porque en la misma
  página conviven dos diseños distintos —diario y semanal— y no decirlo obliga
  al lector a suponerlo.

## Consecuencia técnica

Como los colores se escriben como `var(--fig-…)` **dentro del SVG**, ningún
gráfico necesita repintarse al cambiar de tema. Se eliminó la suscripción a
`au:tema` de `analisis.js`, que existía solo para eso.

## Qué se pierde

Los gráficos ya no se integran visualmente con el resto del sitio. Es
deliberado: la página de análisis es un informe con figuras, no un panel de
control. Las páginas `index.html` y `fuentes.html` conservan sus gráficos
integrados al tema, porque el mapa y las tablas de metodología sí son parte de
la interfaz.
