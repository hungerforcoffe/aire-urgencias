# Calidad de datos

Regla 4 del proyecto: **toda decisión de limpieza se documenta.**

Si una semana se descarta por cobertura insuficiente, si una estación se excluye,
si un valor se trata como centinela en vez de como medición — la regla queda
escrita aquí, con su umbral y su justificación, antes de aplicarse.

Un documento por decisión o por familia de decisiones, con nombre descriptivo.

## Índice

**Qué es cada ciudad y qué se mide**

| Documento | Decisión |
|---|---|
| [`definicion_ciudades.md`](definicion_ciudades.md) | Qué comunas y qué estaciones forman cada ciudad; por qué Talagante queda fuera de Santiago |
| [`estados_validacion_sinca.md`](estados_validacion_sinca.md) | Los tres estados de validación del SINCA se cargan como dato válido |
| [`cobertura_horaria_semanal.md`](cobertura_horaria_semanal.md) | Cuántas horas hacen un día y cuántos días una semana |
| [`correccion_coordenadas.md`](correccion_coordenadas.md) | Una estación de Talcahuano figuraba en Argentina |
| [`direccion_viento_circular.md`](direccion_viento_circular.md) | La dirección del viento se promedia como magnitud circular |

**Las fuentes**

| Documento | Decisión |
|---|---|
| [`conversion_access_deis.md`](conversion_access_deis.md) | Cómo se leen los años 2018-2019 del DEIS, que llegan en Access |
| [`centinela_satpm.md`](centinela_satpm.md) | El valor −999.9 de la rejilla satelital es un centinela, no una medición |
| [`isp_virus.md`](isp_virus.md) | Vigilancia viral del ISP — **reservado** |

**Los resultados y su publicación**

| Documento | Decisión |
|---|---|
| [`resultados_modelo.md`](resultados_modelo.md) | Cómo se validan y publican los resultados del modelo diario |
| [`resultados_modelo_v2.md`](resultados_modelo_v2.md) | La segunda entrega del modelo, y por qué amplía sin corregir |
| [`analisis_semanal.md`](analisis_semanal.md) | Por qué los resultados semanales se extraen de los notebooks y no de su informe |
| [`escala_icap.md`](escala_icap.md) | La escala de color del MP2.5 es la oficial del D.S. 12/2011 |
| [`figuras_sitio.md`](figuras_sitio.md) | Cómo se presentan las figuras del sitio |
| [`red_nacional_mapa.md`](red_nacional_mapa.md) | La red nacional como capa de contexto del mapa |
| [`rosa_red_nacional.md`](rosa_red_nacional.md) | La rosa de contaminación de la red nacional |

Para agregar una decisión nueva, usa la plantilla de abajo.

## Plantilla

```markdown
# <Nombre de la decisión>

- **Fecha:** AAAA-MM-DD
- **Aplica a:** <fuente / tabla / etapa del pipeline>
- **Implementada en:** <ruta del script y función>

## Qué se observó
Descripción del problema en los datos, con cifras: cuántos registros, qué
proporción del total, en qué años o estaciones se concentra.

## Regla adoptada
El umbral exacto y el criterio, redactado de modo que otra persona pueda
reproducirlo sin leer el código.

## Por qué ese umbral
Justificación. Si viene de una norma, referencia. Si es una convención del
equipo, decirlo explícitamente en vez de presentarla como estándar.

## Qué se pierde
Volumen de datos descartado y si la pérdida se concentra en alguna ciudad,
período o estación del año. Importa: una pérdida concentrada en invierno
sesgaría justo el período de interés.

## Alternativas descartadas
Qué otros umbrales o tratamientos se evaluaron y por qué no se eligieron.
```

Los reportes de calidad **describen**, no corrigen en silencio. La zona cruda
nunca se sobrescribe: toda limpieza produce archivos nuevos en `data/interim/`.
