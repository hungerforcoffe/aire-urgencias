# Sitio público

Sitio estático que se publica en GitHub Pages. Tres páginas:

| Archivo | Qué muestra |
|---|---|
| `index.html` | Mapa de las 16 estaciones. Clic en una abre su rosa de contaminación sobre la cartografía. |
| `analisis.html` | La asociación semanal entre MP2.5 y urgencias respiratorias, 1.350 semanas. |
| `fuentes.html` | De dónde sale cada dato, qué APIs se usan, qué reglas se aplican y qué queda fuera. |

## Cómo se actualiza

Los datos **no** se editan a mano. Salen de Athena con:

```bash
python -m src.sitio.exportar            # consulta y escribe assets/datos/*.json
python -m src.sitio.exportar --verificar # relee lo escrito, sin volver a consultar
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
| Teselas | CARTO + OpenStreetMap | la cartografía de fondo |
| Archivo, IBM Plex Sans/Mono | Google Fonts | tipografía |
| Open-Meteo | `api.open-meteo.com` | viento y temperatura actuales |

Open-Meteo entrega **meteorología**. Su capa de calidad del aire modelada no se usa: es
salida de un modelo, no medición, y mezclarla con SINCA rompería la comparabilidad de la
serie.
