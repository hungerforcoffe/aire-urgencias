# Reconocimiento de fuentes

Hallazgos sobre la **estructura real** de cada fuente, antes de escribir código
de ingesta definitivo: qué entrega, en qué formato, con qué codificación, qué
campos trae, qué falta y qué se rompe.

## Qué hay

| Archivo | Contenido |
|---|---|
| [`hallazgos.md`](hallazgos.md) | El documento principal: OpenAQ, SINCA, DEIS y el cambio de Temuco a Talcahuano |
| [`casen.md`](casen.md) | La encuesta CASEN y el combustible de calefacción |
| [`satpm.md`](satpm.md) | El MP2.5 satelital de ACAG |
| `_*.json` | La evidencia en crudo de cada hallazgo, tal como la escribieron los módulos de `src/ingesta/` |
| [`informe_etapa1.html`](informe_etapa1.html) · `.pdf` · `figuras/` | El informe de cierre de esta etapa |

Este es el registro de **cómo se eligieron las fuentes**, no de cómo se usaron al
final: por ejemplo, OpenAQ aparece reconocido en detalle porque el contraste contra
el SINCA es lo que justificó descartarlo.

## Qué debía dejar por escrito cada reconocimiento

Cada documento debería dejar por escrito:

- **Acceso.** URL o ruta exacta, método de descarga, si requiere sesión o
  cabeceras, y si el CGNAT lo bloquea (403 de CloudFront) o no.
- **Formato.** Extensión, separador, codificación, presencia de encabezados,
  filas de metadatos antes de los datos.
- **Granularidad.** Unidad de observación, resolución temporal, cobertura
  geográfica y período disponible.
- **Esquema.** Columnas, tipos, unidades, y el significado de los códigos
  (especialmente los de causa en DEIS y los de estación en SINCA).
- **Faltantes y centinelas.** Cómo se representa un dato ausente: celda vacía,
  `-9999`, `NA`, cero sospechoso.
- **Rupturas.** Cambios de esquema entre años, estaciones que aparecen o
  desaparecen, comunas que cambian de código.
- **Fecha de consulta.** Las fuentes se actualizan; un hallazgo sin fecha no es
  verificable.

Distinguir siempre **"sin permiso / bloqueado"** de **"no existe / vacío"**: un
403 por CGNAT y un recurso inexistente llevan a decisiones opuestas.
