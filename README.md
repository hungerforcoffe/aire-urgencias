# Aire y Urgencias

¿Se asocia el material particulado fino (MP2.5) con las consultas de urgencia
por causa respiratoria? Un estudio ecológico en **Gran Santiago, Talcahuano y
Coyhaique**, 2018–2026, sobre 70 millones de registros de fuentes públicas
chilenas.

Proyecto capstone del curso de Big Data del Samsung Innovation Campus.

**[Ver el sitio](https://hungerforcoffe.github.io/aire-urgencias/)** ·
**[Leer el informe](docs/informe/INFORME.md)**

![De la fuente al análisis](docs/informe/figuras/arquitectura.png)

---

## Qué encontramos

**La resolución temporal decide el resultado.** A escala semanal, descontando la
estacionalidad, la asociación entre MP2.5 y urgencias no se distingue de cero. A
escala diaria, comparando cada ciudad consigo misma dentro del mismo mes y día de
la semana, aparece: **+0,81 % de consultas respiratorias por cada +10 µg/m³**
el mismo día (IC 95 % +0,47 a +1,15), ajustando por temperatura, humedad y
circulación viral.

**Pero no es un resultado limpio.** Los controles negativos —traumatismos y
accidentes de tránsito, que respirar partículas no puede provocar— dan una
asociación igual o mayor. Eso mide sesgo, no aire: los días de alto MP2.5 son días
de inversión térmica, fríos y sin viento, y ese patrón mueve también otras
urgencias. Con esta metodología **no podemos separar cuánto de la asociación es
el aire**, y lo decimos.

Es un estudio ecológico y observacional: habla de **asociación, nunca de
causalidad**, y ninguna fila describe a una persona.

## En números

| | |
|---|---|
| Filas procesadas | **70,5 millones** en 16 tablas Parquet (209 MB) |
| Zona cruda | **3,7 GB** en siete formatos distintos |
| Base en Athena | **14 tablas**, 12 del modelo en estrella |
| Estaciones de monitoreo | 16 del estudio + 84 de contexto nacional en el mapa |
| Días-ciudad en el modelo | 8.713 |
| Código | 38 módulos de Python |

## Cómo está organizado

| Carpeta | Qué hay |
|---|---|
| [`src/`](src/) | El código, en cinco etapas: ingesta → procesamiento → nube → análisis → sitio |
| [`docs/`](docs/) | El informe final, cada decisión de limpieza con su umbral, y el reconocimiento de las fuentes |
| [`sitio/`](sitio/) | El sitio público: mapa de la red, análisis y metodología |
| [`notebooks/`](notebooks/) | La narrativa del análisis y su réplica en PySpark |

Cada carpeta tiene su propio README.

## Reproducir

Requiere [`uv`](https://docs.astral.sh/uv/); el entorno queda fijado en Python 3.12.

```powershell
uv sync                                        # crea .venv e instala el lock
uv run python -m src.nube.consultar tablas     # la base, desde Athena (requiere perfil AWS)
uv run python -m http.server 8000 --directory sitio   # el sitio en local
```

Los datos no están en el repositorio: `data/` se construye desde las fuentes con
los módulos de [`src/`](src/), o se baja del bucket del proyecto con credenciales
del equipo. Todo módulo se ejecuta como `python -m src.<paquete>.<modulo>` y su
`--help` es su documentación.

## Equipo · PARTICULAS CERO

| Integrante | Rol | GitHub |
|---|---|---|
| Pablo Rojas | Ingesta, procesamiento, nube y sitio | [@hungerforcoffe](https://github.com/hungerforcoffe) |
| Camila Bravo | Diseño, presentación y análisis de datos | [@mikabldev](https://github.com/mikabldev) |
| Nicolás Torres | Análisis de datos | [@NicolasTorresSSNA](https://github.com/NicolasTorresSSNA) |
| Noemi Calabuig | Análisis de datos | [@noemicalabuig](https://github.com/noemicalabuig) |
| Dante Velasquez | Gráficos temporales interactivos | [@Sketles](https://github.com/Sketles) |

## Fuentes y créditos

| Fuente | Qué aporta |
|---|---|
| **SINCA** · Ministerio del Medio Ambiente | MP2.5 horario y meteorología por estación |
| **DEIS** · Ministerio de Salud | Atenciones de urgencia por establecimiento, causa y día |
| **INE** | Proyecciones de población comunal |
| **CASEN** | Combustible de calefacción de los hogares |
| **ISP** · Instituto de Salud Pública | Vigilancia de virus respiratorios |

La **base de vigilancia viral** que usa el modelo la construyó una integrante del
equipo a partir de los informes semanales del ISP, y se publicará en su propio
repositorio. Hasta entonces su documentación está reservada.
