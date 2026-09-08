# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Proyecto: Aire y Urgencias

Capstone de Big Data. Analiza la asociación entre material particulado fino
(MP2.5) y consultas de urgencia respiratoria en tres ciudades chilenas.

## Pregunta

¿Cómo se asocia la variación semanal de MP2.5 con la variación semanal de
consultas de urgencia por causa respiratoria en Santiago, Talcahuano y Coyhaique
(2018-2024), controlando por temperatura, estacionalidad y período de pandemia?

## Alcance

- Ciudades: Santiago, Talcahuano, Coyhaique
- Período: 2018-2024
- Contaminante: solo MP2.5
- Agregación: semanal (revisar si DEIS permite diario)
- Rezagos: hasta 2 semanas

## Reglas que no se rompen

1. **Asociación, nunca causalidad.** Ningún texto, nombre de variable,
   comentario o gráfico debe afirmar que la contaminación *causa* consultas.
   Es un estudio ecológico observacional.

2. **Acotar al final, no al principio.** Ingesta y procesamiento operan a
   escala nacional/global. El filtro a tres ciudades ocurre en la última
   etapa. Si se filtra en la ingesta, el proyecto deja de ser Big Data.

3. **Nunca sobrescribir la zona cruda.** Los archivos descargados son
   inmutables. Todo reproceso parte de ahí.

4. **Toda decisión de limpieza se documenta.** Si se descarta una semana por
   cobertura insuficiente, la regla queda escrita con su umbral y su
   justificación en `docs/calidad/`.
5. **Un fallo nunca puede parecer un éxito.** Fuentes conocidas
   devuelven HTTP 200 con contenido vacío o de tipo incorrecto
   (SINCA: GIF de 0 bytes cuando el parámetro está mal). Toda
   descarga se valida antes de darse por buena:
   - tamaño > 0
   - tipo de contenido esperado
   - parseable en el formato declarado
   - número de filas > 0 y dentro de rango plausible

   Un archivo que no pasa la validación va a la cola de errores,
   nunca a la zona cruda. Un vacío silencioso se vuelve
   indistinguible de un dato faltante real, y contamina el análisis
   sin dejar rastro.

6. **Ningún lector asume esquema.** Se detectaron tres variantes de
   CSV en OpenAQ (lat/lon duplicadas; `measurand` en vez de
   `parameter`). Los lectores normalizan por detección, no por
   supuesto, y registran qué variante encontraron.

## Fuentes

| Fuente | Rol | Acceso |
|---|---|---|
| SINCA (MMA) | **Única fuente de aire para Chile.** MP2.5 horario + meteorología | descarga web por estación/año |
| DEIS (MINSAL) | Co-primaria: urgencias respiratorias | descarga de archivos |
| ISP | Vigilancia de virus respiratorios: control del confusor | tabulado por el equipo desde los PDF |
| Reanálisis meteorológico | Temperatura donde SINCA no mide; relleno de vacíos | API pública |
| INE | Proyecciones de población por comuna y año: el denominador | XLSX |
| CASEN | Combustible de calefacción del hogar: contexto regional, no covariable | `.dta` por año |
| SatPM2.5 (ACAG) | MP2.5 satelital mensual: papel **espacial**, no temporal | `s3://` público |
| OpenAQ | **Solo referencia internacional.** NO usar para datos chilenos | `s3://openaq-data-archive/` |
| Dimensiones | comunas, establecimientos, estaciones, calendario | construidas por el equipo |

### Regla sobre OpenAQ

OpenAQ es un agregador que cosecha los datos chilenos desde SINCA.
Usarlo como fuente de MP2.5 chileno sería contar la misma medición dos
veces. **Su único rol es el marco de referencia internacional:**
posicionar Santiago, Talcahuano y Coyhaique frente a ciudades del mundo.

Cualquier consulta a OpenAQ que filtre por Chile para obtener
mediciones de aire es un error de diseño, salvo en el contraste
explícito de validación descrito en docs/reconocimiento/.

Además, OpenAQ **no replica** el dato de SINCA: publica
`round(media_móvil_24h + 10)`, sin marcas de validación y sin meteorología
(`docs/reconocimiento/hallazgos.md` §1.5).

## Entorno

- Windows 10, i7-7700HQ, 16 GB RAM. La VM de Hadoop dispone de ~8 GB.
- Python fijado en 3.12 vía `uv` (ver `.python-version`). PySpark **no** está
  entre las dependencias locales; la VM de Hadoop usa su propio intérprete.
- El `python` del PATH del sistema puede ser otro (3.14). Todo comando del
  proyecto va por `uv run` o por `.venv\Scripts\python.exe`.
- **La conexión está detrás de CGNAT y CloudFront devuelve 403.** Si una
  descarga falla con 403 o timeout, es probable que sea la IP y no el
  servidor. Distinguir siempre "sin permiso / bloqueado" de "no existe /
  vacío" en los mensajes de error.
- AWS: buckets públicos, sin credenciales. Usar `--no-sign-request` en el CLI
  o `Config(signature_version=UNSIGNED)` en boto3. El bucket **del proyecto**
  sí es privado y se lee con `--perfil` de `~/.aws/credentials`.
- Fuentes chilenas: CSV con separador `;` y codificación `latin-1`/`cp1252`
  con frecuencia. No asumir UTF-8 ni coma.

## Comandos

```powershell
uv sync                                  # crea .venv (3.12) e instala el lock
uv run ruff check .                      # lint: E, F, I, UP, B; line-length 100
uv run ruff check --fix .
uv run python -m http.server 8000 --directory sitio   # ver el sitio en local
uv run jupyter lab
```

No hay suite de pruebas: `pytest` está en el grupo `dev` pero no existe
`tests/`. La verificación del proyecto es el subcomando `verificar` de cada
módulo (ver más abajo), no un test runner.

Todo script se ejecuta como módulo desde la raíz del repositorio:

```powershell
uv run python -m src.<paquete>.<modulo> <subcomando> [opciones]
uv run python -m src.<paquete>.<modulo> --help        # la ayuda es el docstring
```

Tres convenciones de subcomando que se repiten en todo el repo:

| Patrón | Significado |
|---|---|
| `--simular` / `--aplicar` | los módulos de `src/nube/` **simulan por defecto**; sin `--aplicar` no tocan la red |
| `construir` / `verificar` | `src/procesamiento/*` y `src/sitio/*`: construir escribe, verificar relee lo escrito sin recalcular |
| `acceso`, `particion`, `contar`, `descargar` | `src/ingesta/reconocer_*`: reconocimiento de una fuente, de barato a caro |

Cadena completa, de la fuente al sitio:

```powershell
# 1. ingesta -> data/raw (inmutable)
uv run python -m src.ingesta.reconocer_deis descargar --desde 2018 --hasta 2024
uv run python -m src.ingesta.reconocer_ine descargar
uv run python -m src.ingesta.red_nacional catalogo
uv run python -m src.ingesta.red_nacional descargar

# 2. procesamiento -> data/processed (Parquet)
uv run python -m src.procesamiento.deis_access convertir      # 2018-2019: .mdb -> CSV
uv run python -m src.procesamiento.deis construir
uv run python -m src.procesamiento.sinca construir --bucket <bucket> --perfil <perfil>
uv run python -m src.procesamiento.tiempo construir
uv run python -m src.procesamiento.tiempo validar             # MMWR contra el DEIS
uv run python -m src.procesamiento.estaciones construir --bucket <bucket> --perfil <perfil>
uv run python -m src.procesamiento.ciudades construir
uv run python -m src.procesamiento.poblacion construir
uv run python -m src.procesamiento.isp_virus construir
uv run python -m src.procesamiento.analitico construir        # recorte a 3 ciudades
uv run python -m src.procesamiento.analisis_semanal extraer   # notebooks -> CSV

# 3. nube: S3 + Glue + Athena
uv run python -m src.nube.sincronizar --bucket <bucket> --perfil <perfil> subir --zona processed --aplicar
uv run python -m src.nube.catalogo --bucket <bucket> --perfil <perfil> --aplicar
uv run python -m src.nube.consultar tablas
uv run python -m src.nube.consultar sql "SELECT * FROM dim_ciudad"

# 4. sitio -> sitio/assets/datos/*.json (se versionan)
uv run python -m src.sitio.exportar --verificar
uv run python -m src.sitio.exportar_nacional
uv run python -m src.sitio.exportar_modelo
uv run python -m src.sitio.exportar_semanal
```

Spark corre **fuera** del repositorio, en la VM, con su propio intérprete:

```bash
spark-submit --master yarn --deploy-mode client \
    --driver-memory 1g --executor-memory 2g --num-executors 2 \
    src/analisis/spark_grano_fino.py \
    hdfs:///user/$USER/aire/processed hdfs:///user/$USER/aire/trabajo
```

## Arquitectura

Cinco etapas. El dato viaja en una sola dirección y cada frontera está
justificada; leer un módulo suelto no la muestra.

```
fuentes web/S3
  -> src/ingesta/        descarga + valida (regla 5)   -> data/raw/       inmutable
  -> src/procesamiento/  lee y normaliza (regla 6)     -> data/processed/ Parquet
  -> src/nube/           S3 + Glue + Athena = la base de datos del equipo
  -> src/analisis/       modelo (notebook + asociacion.py)
  -> src/sitio/          agregados publicables         -> sitio/assets/datos/*.json
                                                       -> GitHub Pages (.github/workflows/paginas.yml)
```

**`src/rutas.py` es el único lugar con rutas.** Todo se deriva de la raíz del
repositorio, así el código corre igual en cualquier máquina y en la VM.

### El modelo en estrella de `data/processed/`

| Tabla | Grano | La escribe |
|---|---|---|
| `hecho_medicion` | estación × hora, con los tres estados de validación de SINCA | `procesamiento/sinca.py` |
| `hecho_urgencia` | establecimiento × día × causa, franjas etarias en **columnas** | `procesamiento/deis.py` |
| `dim_tiempo` | día, con semana **MMWR**, invierno y período de pandemia | `procesamiento/tiempo.py` |
| `dim_estacion` | estación de SINCA, con `CORRECCIONES` aplicadas en código | `procesamiento/estaciones.py` |
| `dim_ciudad` | qué comunas forman cada ciudad; audita aire contra salud | `procesamiento/ciudades.py` |
| `dim_causa`, `dim_establecimiento` | catálogos del DEIS | `procesamiento/deis.py` |
| `poblacion_comuna_anio`, `poblacion_ciudad_anio` | denominador por año y franja etaria | `procesamiento/poblacion.py` |
| `isp_virus_dia`, `isp_virus_semana` | circulación viral: control del confusor | `procesamiento/isp_virus.py` |
| `analitico_ciudad_semana` | **ciudad × semana MMWR** — la última etapa, y el único sitio donde el recorte a tres ciudades es legítimo (regla 2) | `procesamiento/analitico.py` |
| `red_nacional_estacion/_mes/_anio/_rosa` | contexto del mapa; serie **diaria** ya promediada por Airviro | `procesamiento/red_nacional*.py` |

**Los dos carriles no se mezclan.** `hecho_medicion` es horario y sostiene el
análisis; `red_nacional_*` es diario y solo alimenta el mapa. Mezclarlos
rompería la procedencia de la tabla horaria.

### Athena es la base de datos

Nadie sincroniza `data/processed/` para consultar: Glue guarda dónde está cada
Parquet y Athena los lee desde S3 (`src/nube/consultar.py`). El DDL se genera
leyendo el **esquema real del Parquet**, no a mano — es la regla 6 aplicada al
catálogo. Filtrar por `anio` usa la partición; `SELECT *` sin filtro escanea la
tabla entera.

### El sitio no tiene backend

GitHub Pages sirve archivos y no guarda secretos, así que el sitio **no**
consulta Athena: lee los JSON que alguien exportó con credenciales locales, y
esos JSON se versionan (excepción deliberada, anotada en `.gitignore`). El CI
solo publica: comprueba que los cinco JSON obligatorios existan y avisa —sin
fallar— si falta `nacional.json`. Tres exportadores con orígenes distintos:

- `exportar.py` — Athena; `meta/estaciones/mensual/ciudades/semanal.json`
- `exportar_nacional.py` — `data/processed/red_nacional_*` en local, sin AWS
- `exportar_modelo.py` — CSV del cuaderno en `data/raw/modelo/` y
  `data/raw/modelo_viz/`; **no ajusta ningún modelo**, solo valida y publica
- `exportar_semanal.py` — el segundo análisis del equipo, a escala ciudad-semana.
  Llegó en notebooks sin handoff de CSV, así que
  `procesamiento/analisis_semanal.py` los extrae leyendo las salidas guardadas de
  las celdas. **Su informe `.md` no es la fuente**: está desincronizado de los
  notebooks (ver `docs/calidad/analisis_semanal.md`)

Todos abortan dejando los JSON anteriores intactos si una consulta vuelve vacía
o con una columna en nulo: un vacío publicado es peor que un error visible.

### El análisis

`src/analisis/asociacion.py` es la maquinaria (panel ciudad-día, rezagos de
Almon, Poisson condicional por efectos fijos de estrato, quasi-Poisson);
`notebooks/analisis_mp25_urgencias.ipynb` es la narrativa. Las decisiones de
diseño están fijadas en el docstring del módulo y no se eligen al vuelo.

`Improve Chile MP2.5 Dashboard/` es un scaffold de Figma Make (React 19 + Vite +
Tailwind v4) **ajeno a la cadena de datos**, con su propio `AGENTS.md`. No es el
sitio que se publica; el sitio es `sitio/`.

## Estructura del repo

```
data/
  raw/          # inmutable, tal como se descargó
  interim/      # intermedios de limpieza (regenerables, no viajan a S3)
  processed/    # tablas finales
src/
  ingesta/  procesamiento/  analisis/  nube/  sitio/  rutas.py
docs/
  reconocimiento/   # hallazgos sobre estructura de las fuentes
  calidad/          # una decisión de limpieza por archivo (plantilla en su README)
  nube/             # operación del bucket y de los permisos del equipo
sitio/          # sitio estático publicado en GitHub Pages
notebooks/
logs/
```

## Convenciones

- Python 3.12, entorno virtual local gestionado con `uv`
- Nada de rutas absolutas ni credenciales en el código
- `data/` está en `.gitignore`; se versiona el código, no los datos
- Nombres de archivo: `fuente_alcance_periodo.ext`
- Logs a `logs/`, no a stdout, cuando el proceso sea largo
- Formato intermedio y final: Parquet

### Anatomía de un módulo ejecutable

Todos siguen la misma forma; conviene copiarla al agregar uno:

- **El docstring es la documentación.** Explica qué hace, qué *no* hace a
  propósito, y termina con una sección `Uso`. `argparse` lo muestra como
  `description` con `RawDescriptionHelpFormatter`.
- `main(argv=None)` con subparsers y `sub.add_parser(...).set_defaults(fn=...)`;
  al final, `if __name__ == "__main__": raise SystemExit(main())`.
- `logging.basicConfig(..., handlers=[FileHandler(LOGS / "<modulo>.log")])`,
  y `sys.stdout.reconfigure(encoding="utf-8")` antes de imprimir: la consola de
  Windows es cp1252 y revienta con `≥` o `µ`.
- Bootstrap `sys.path.insert(0, str(Path(__file__).resolve().parents[2]))`
  seguido de los imports de `src.*` con `# noqa: E402`.
- Los mensajes de error dicen **el comando que arregla el problema**
  (`Bájalo con: python -m src.ingesta.reconocer_ine descargar`).

### Trampas ya pagadas

- **Semanas MMWR, nunca ISO.** `datetime.isocalendar()` y `strftime('%V')` no
  se usan en el proyecto: desfasan hasta seis días contra el DEIS, del mismo
  orden que el efecto que se busca medir. `tiempo.py validar` lo contrasta fila
  a fila y se detiene si no coinciden al 100 %.
- **`pyarrow>=20`.** Los Parquet los escribe pyarrow 25 con `SizeStatistics`;
  pyarrow 19 falla con `Repetition level histogram size mismatch`, un error que
  no menciona la versión. Si aparece, es que corre otro Python — casi siempre un
  Anaconda. Ver `notebooks/README.md`.
- **SINCA: `outtype=xcl` devuelve CSV.** `outtype=csv` devuelve un GIF de 0
  bytes con HTTP 200. Las barras del parámetro `macro` van sin codificar (no
  usar `params=` de requests) y las fechas en `AAMMDD`.
- **MP2.5 de ciudad = media de las medias por estación**, no media agrupada de
  horas: la agrupada pondera por accidentes de mantenimiento, hasta 10,3 µg/m³
  de diferencia. `mp25_media_pool` guarda la otra versión para poder medir esa
  sensibilidad.
- **Cobertura:** un día vale con ≥18 de 24 horas; una semana con ≥5 de 7 días;
  un año del mapa con ≥300 días. Cada umbral está documentado en
  `docs/calidad/`.
- **Las correcciones de datos van en código, no en `raw/`** (`CORRECCIONES` en
  `estaciones.py`, con su evidencia). La zona cruda no se edita jamás.

## Fuera de alcance

Causalidad · inferencia individual · app para ciudadanos · otros contaminantes
· atribución de fuentes · cobertura nacional · valorización económica ·
mortalidad · datos clínicos individuales

### Una extensión declarada: el pronóstico

`pronóstico` salió de esa lista el 2026-09-08 y no porque el alcance haya
crecido. El equipo produjo un bloque de proyección a t+1 y de planificación de
dotación asistencial, y el sitio lo publica **rotulado como fuera del alcance
declarado**, en una sección aparte y con esas palabras en su encabezado.

La regla que sí sigue en pie: **no forma parte del resultado del estudio.** La
pregunta de investigación es sobre asociación. El pronóstico está ahí porque su
respuesta acota la anterior —si el MP2.5 fuera el motor de las urgencias, se
habría notado al intentar predecirlas— y su aporte medido es marginal.

`valorización económica` se mantiene fuera: esa extensión estima dotación de
personal y camas, no costos.
