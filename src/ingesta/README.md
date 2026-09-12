# `src/ingesta/` — reconocimiento y descarga de las fuentes

Etapa 1. Escribe en `data/raw/`, que es **inmutable**: nada de lo que se descarga
se edita después, y todo reproceso parte de ahí.

## Cómo se obtuvieron los datos del estudio

La ingesta definitiva de las fuentes principales se hizo con **scrapers propios del
equipo**, que no están publicados en este repositorio:

| Fuente | Mecanismo |
|---|---|
| DEIS · atenciones de urgencia | scraper sobre la plataforma Cognos del MINSAL |
| SINCA · meteorología | scraper sobre el sistema de consulta del SINCA |
| SINCA · MP2.5 de las tres ciudades | descarga manual, estación por estación |
| ISP · vigilancia viral | base propia de una integrante — reservada |

Lo que sí vive acá es el **reconocimiento** de cada fuente —qué entrega, en qué
formato, qué se rompe— y la descarga de las fuentes de contexto.

## Los módulos

| Módulo | Qué hace |
|---|---|
| `reconocer_deis.py` | Disponibilidad, descarga validada, esquema por año y cobertura por ciudad del DEIS |
| `sinca_cliente.py` | Cliente de descarga del SINCA (Airviro APUB), deducido del JavaScript de su página |
| `red_nacional.py` | Catálogo de la red nacional del SINCA con coordenadas, serie diaria y par horario MP2.5 + viento |
| `reconocer_ine.py` | Proyecciones de población comunal del INE |
| `reconocer_casen.py` | Microdatos de la encuesta CASEN |
| `reconocer_satpm.py` | MP2.5 satelital mensual (ACAG), usado solo como contexto espacial |
| `reconocer_openaq.py` · `contrastar_openaq_sinca.py` | Reconocimiento de OpenAQ y el contraste hora a hora contra el SINCA |

**Sobre OpenAQ.** Se reconoció y **se descartó como fuente**: no replica el dato del
SINCA, sino que publica una media móvil de 24 horas desplazada en +10 µg/m³.
El contraste que lo demuestra está en
[`docs/reconocimiento/hallazgos.md`](../../docs/reconocimiento/hallazgos.md) §1.5.

## Uso

Los subcomandos van de barato a caro: primero se comprueba el acceso, después se
cuenta, y solo al final se descarga.

```powershell
uv run python -m src.ingesta.reconocer_deis disponibilidad
uv run python -m src.ingesta.red_nacional catalogo
uv run python -m src.ingesta.red_nacional --help
```
