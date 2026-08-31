# Calidad de datos

Regla 4 del proyecto: **toda decisión de limpieza se documenta.**

Si una semana se descarta por cobertura insuficiente, si una estación se excluye,
si un valor se trata como centinela en vez de como medición — la regla queda
escrita aquí, con su umbral y su justificación, antes de aplicarse.

Un documento por decisión o por familia de decisiones, con nombre descriptivo:
`cobertura_horaria_semanal.md`, `estaciones_excluidas.md`,
`centinelas_sinca.md`.

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
