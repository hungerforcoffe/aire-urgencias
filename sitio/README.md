# Sitio público

Sitio estático que se publica en GitHub Pages. Tres páginas:

| Archivo | Qué muestra |
|---|---|
| `index.html` | Mapa de la red y barra lateral **región → comuna → estación**, de norte a sur. Cualquier estación se abre con su meteograma y su tabla año por año; solo las 16 del estudio tienen además rosa de contaminación. Las comunas de las tres ciudades del estudio van marcadas. |
| `analisis.html` | La asociación semanal entre MP2.5 y urgencias respiratorias, 1.350 semanas. |
| `fuentes.html` | De dónde sale cada dato, qué APIs se usan, qué reglas se aplican y qué queda fuera. |

## Cómo se actualiza

Los datos **no** se editan a mano. Salen de Athena con:

```bash
python -m src.sitio.exportar            # consulta Athena y escribe assets/datos/*.json
python -m src.sitio.exportar --verificar # relee lo escrito, sin volver a consultar

python -m src.sitio.exportar_nacional            # capa nacional -> assets/datos/nacional.json
python -m src.sitio.exportar_nacional --verificar
```

`nacional.json` es la capa de contexto del mapa: las 84 estaciones de SINCA que miden MP2.5
fuera de las tres ciudades. Sale de `data/processed/red_nacional_*` y **no pasa por Athena**
— se construye entera en local desde la zona cruda, así que no necesita credenciales. Es
**opcional**: si el archivo no está, el mapa sigue funcionando con las 16 del estudio y el
interruptor de la capa queda desactivado, con la instrucción de cómo generarla. Para
reconstruirla desde cero:

```bash
python -m src.ingesta.red_nacional catalogo      # 16 regiones, coordenadas de cada ficha
python -m src.ingesta.red_nacional descargar     # serie diaria de MP2.5 por estación
python -m src.procesamiento.red_nacional construir
```

El exportador valida antes de escribir: si una consulta vuelve vacía, con menos filas de
las esperadas o con una columna entera en nulo, aborta y **deja intactos los JSON
anteriores**. Un vacío silencioso publicado es peor que un error visible.

Para verlo en local:

```bash
python -m http.server 8000 --directory sitio
```

Hay que servirlo por HTTP: abriendo `index.html` con doble clic, el navegador bloquea el
`fetch` de los JSON por política de origen y el mapa queda en blanco.

## Por qué los JSON sí están versionados

El repositorio no versiona datos: `data/` está en `.gitignore` y ahí viven las zonas cruda,
intermedia y procesada. `sitio/assets/datos/` es otra cosa — es el **resultado publicado**,
del orden de las figuras de un informe:

- solo agregados: medias mensuales por estación, medianas por sector de viento, la tabla
  semanal por ciudad;
- ningún registro individual, ninguna atención de ninguna persona;
- unos 900 kB en total.

GitHub Pages sirve archivos y nada más, así que estos JSON tienen que estar en el repo para
que el sitio funcione. Si dejan de estarlo, el flujo de publicación falla a propósito antes
de desplegar.

## Lo que este sitio nunca puede tener

**Una credencial.** GitHub Pages no ejecuta código de servidor ni guarda secretos: todo lo
que llegue acá queda público. Por eso el sitio no consulta Athena en vivo y solo llama APIs
que no piden llave. Las credenciales de AWS del equipo viven fuera del repositorio y se leen
del perfil local (`~/.aws/credentials`) únicamente en el paso de exportación.

## Dependencias externas

| Qué | De dónde | Para qué |
|---|---|---|
| Leaflet 1.9.4 | cdnjs | el mapa |
| Teselas | Esri Canvas (gris claro / gris oscuro) | la cartografía de fondo |
| Fraunces, Source Sans 3, JetBrains Mono | Google Fonts | tipografía |
| Open-Meteo | `api.open-meteo.com` | viento y temperatura actuales |

**Ninguna de las cuatro pide llave, y esa es la condición de entrada.** CARTO servía las
teselas hasta que empezó a exigir una: no falla con un error, responde **HTTP 200 con un PNG
válido que dice «API KEY REQUIRED» impreso encima**. El `fetch` no se queja, la capa se
agrega y el mapa se ve roto solo al mirarlo. Es la regla 5 del proyecto aplicada a una
imagen, y la razón de que la cartografía se revise a ojo y no solo por código de estado.

Open-Meteo entrega **meteorología**. Su capa de calidad del aire modelada no se usa: es
salida de un modelo, no medición, y mezclarla con SINCA rompería la comparabilidad de la
serie.
