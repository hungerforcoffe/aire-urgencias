# `src/procesamiento/` — el modelo en estrella

Etapa 2. Lee `data/raw/` y escribe **Parquet** en `data/processed/`. Los lectores no
suponen el esquema: el DEIS cambia de formato y de cabecera entre años, así que
cada lector normaliza por detección y registra qué variante encontró.

![El modelo en estrella](../../docs/informe/figuras/estrella.png)

## Qué tabla escribe cada módulo

| Módulo | Tabla | Grano |
|---|---|---|
| `sinca.py` | `hecho_medicion` | estación × hora, con el estado de validación del SINCA |
| `deis.py` | `hecho_urgencia`, `dim_causa`, `dim_establecimiento` | establecimiento × día × causa |
| `deis_access.py` | — | convierte los `.mdb` de Access de 2018-2019 a CSV, para que un solo lector sirva para todos los años |
| `tiempo.py` | `dim_tiempo` | día, con semana epidemiológica, invierno y período de pandemia |
| `estaciones.py` | `dim_estacion` | estación, con las correcciones de coordenadas aplicadas en código |
| `ciudades.py` | `dim_ciudad` | qué comunas forman cada ciudad |
| `poblacion.py` | `poblacion_comuna_anio`, `poblacion_ciudad_anio` | el denominador |
| `analitico.py` | `analitico_ciudad_semana` | **ciudad × semana** — la tabla del análisis |
| `red_nacional.py` · `red_nacional_rosa.py` | `red_nacional_*` | contexto del mapa del sitio |
| `analisis_semanal.py` | — | extrae a CSV los resultados que llegaron en notebooks |
| `isp_virus.py` | — | **reservado** — ver [`docs/calidad/isp_virus.md`](../../docs/calidad/isp_virus.md) |

## Dos decisiones que viven en un solo sitio

- **`geografia.py`** define qué comunas forman cada ciudad, por código de comuna. La
  usan los dos lados del modelo —el aire y la salud—, y `ciudades.py` falla si
  describen territorios distintos.
- **La semana epidemiológica** se construye en `tiempo.py` y se contrasta fila a fila
  contra la numeración del DEIS. Las funciones de calendario ISO desfasan hasta
  seis días, del mismo orden que el efecto que se mide.

## El recorte a tres ciudades

Todo el procesamiento es **nacional**. El recorte a Gran Santiago, Talcahuano y
Coyhaique ocurre una sola vez, en `analitico.py`, la última tabla de la cadena.

Cada decisión de limpieza —umbrales de cobertura, estados de validación, ámbito de
cada ciudad— está documentada en [`docs/calidad/`](../../docs/calidad/).

## Uso

```powershell
uv run python -m src.procesamiento.tiempo construir
uv run python -m src.procesamiento.tiempo validar
uv run python -m src.procesamiento.analitico construir
uv run python -m src.procesamiento.analitico verificar
```
