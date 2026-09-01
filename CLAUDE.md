# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Proyecto: Aire y Urgencias

Capstone de Big Data. Analiza la asociación entre material particulado fino
(MP2.5) y consultas de urgencia respiratoria en tres ciudades chilenas.
El repositorio está escrito en español: código, comentarios y documentos.

## Pregunta

¿Cómo se asocia la variación semanal de MP2.5 con la variación semanal de
consultas de urgencia por causa respiratoria en Santiago, Talcahuano y Coyhaique
(2018-2026), controlando por temperatura, estacionalidad y período de pandemia?

## Alcance

- Ciudades: Santiago, Talcahuano, Coyhaique
- Período: 2018-2026 (2026 parcial: el DEIS publica hasta el día anterior;
  la última semana epidemiológica completa manda)
- Contaminante: solo MP2.5
- Agregación: semanal en `analitico_ciudad_semana`; el case-crossover de
  `src/analisis/asociacion.py` trabaja a ciudad-día
- Rezagos: hasta 2 semanas

## Reglas que no se rompen

1. **Asociación, nunca causalidad.** Ningún texto, nombre de variable,
   comentario o gráfico debe afirmar que la contaminación *causa* consultas.
   Es un estudio ecológico observacional.

2. **Acotar al final, no al principio.** Ingesta y procesamiento operan a
   escala nacional/global. El filtro a tres ciudades ocurre en la última etapa
   (`analitico.py`). Si se filtra en la ingesta, el proyecto deja de ser Big
   Data.

3. **Nunca sobrescribir la zona cruda.** Los archivos descargados son
   inmutables. Todo reproceso parte de ahí. Una corrección no se aplica al
   archivo: se declara en el código con su evidencia (ver `CORRECCIONES` en
   `src/procesamiento/estaciones.py`). La política IAM del bucket deniega
   `s3:DeleteObject` sobre `raw/*`, así que la regla la sostiene la
   infraestructura y no la memoria de quien sube.

4. **Toda decisión de limpieza se documenta.** Si se descarta una semana por
   cobertura insuficiente, la regla queda escrita con su umbral y su
   justificación en `docs/calidad/`, siguiendo la plantilla de su README.

5. **Un fallo nunca puede parecer un éxito.** Fuentes conocidas
   devuelven HTTP 200 con contenido vacío o de tipo incorrecto
   (SINCA: GIF de 0 bytes cuando el parámetro está mal; INE: XLSX en una URL
   que termina en `.csv`). Toda descarga se valida antes de darse por buena:
   - tamaño > 0
   - tipo de contenido esperado, comprobado por los números mágicos del cuerpo
   - parseable en el formato declarado
   - número de filas > 0 y dentro de rango plausible

   Un archivo que no pasa la validación va a la cola de errores,
   nunca a la zona cruda. Un vacío silencioso se vuelve
   indistinguible de un dato faltante real, y contamina el análisis
   sin dejar rastro.

6. **Ningún lector asume esquema.** Se detectaron tres variantes de CSV en
   OpenAQ (lat/lon duplicadas; `measurand` en vez de `parameter`) y tres
   formatos distintos del DEIS entre 2018 y 2026. Los lectores normalizan por
   detección, no por supuesto, y registran qué variante encontraron. Vale
   también para el catálogo: `src/nube/catalogo.py` declara los tipos leyendo el
   esquema real del Parquet, no un DDL escrito de memoria.

## Comandos

```powershell
uv sync                       # entorno en .venv; Python 3.12 fijado por .python-version
uv run ruff check .           # lint (E, F, I, UP, B; línea de 100)
uv export --no-hashes -o requirements.txt   # regenerar el pin para quien no usa uv
```

No hay suite de pruebas: `pytest` está en el grupo `dev` pero `tests/` no
existe. La verificación del proyecto es otra y sí se corre: cada etapa expone un
subcomando `verificar` / `auditar` / `validar` que contrasta lo escrito contra la
fuente. Si se añaden pruebas, una sola se corre con
`uv run pytest tests/test_x.py::test_y`.

Todo módulo se invoca como `python -m src.<paquete>.<módulo> <subcomando>` desde
la raíz del repositorio, nunca por ruta de archivo. Los scripts de `src/nube/`
**simulan por defecto**: hay que pasar `--aplicar` para que toquen la red.

### Reconstruir el modelo, en orden

El orden importa: cada paso lee lo que escribió el anterior.

```bash
python -m src.ingesta.reconocer_deis descargar --desde 2018 --hasta 2026   # -> data/raw/deis/*.zip
python -m src.procesamiento.deis_access convertir     # .mdb de 2018-2019 -> data/interim/
python -m src.procesamiento.tiempo construir && python -m src.procesamiento.tiempo validar
python -m src.procesamiento.deis construir            # hecho_urgencia, dim_causa, dim_establecimiento
python -m src.procesamiento.estaciones construir --bucket <bucket> --perfil <perfil>
python -m src.procesamiento.ciudades auditar && python -m src.procesamiento.ciudades construir
python -m src.ingesta.reconocer_ine descargar && python -m src.procesamiento.poblacion construir
python -m src.procesamiento.sinca construir --bucket <bucket> --perfil <perfil>
python -m src.procesamiento.analitico construir       # única etapa que recorta a tres ciudades
```

La red nacional del mapa es una rama aparte y no depende de lo anterior:

```bash
python -m src.ingesta.red_nacional catalogo          # 213 estaciones, 111 con MP2.5
python -m src.ingesta.red_nacional descargar         # serie diaria por estación
python -m src.procesamiento.red_nacional construir
```

### Publicar

```bash
python -m src.nube.sincronizar --bucket <bucket> subir --zona processed --aplicar
python -m src.nube.catalogo --bucket <bucket> --perfil <perfil> --aplicar   # Glue + Athena
python -m src.sitio.exportar                          # Athena -> sitio/assets/datos/*.json
python -m src.sitio.exportar_nacional                 # capa nacional (local, sin Athena)
python -m http.server 8000 --directory sitio          # ver el sitio en local
```

`sitio/assets/datos/*.json` se versiona y se le hace commit: el flujo de GitHub
Pages (`.github/workflows/paginas.yml`) publica los JSON tal como están y falla
si falta alguno de los cinco. El CI no consulta Athena a propósito — hacerlo
obligaría a guardar una llave en los secretos del repositorio.

## Arquitectura

### Las tres capas

- **`data/` local** — `raw/` inmutable, `interim/` regenerable, `processed/` en
  Parquet. Está en `.gitignore`.
- **S3 + Glue + Athena** — el bucket replica las mismas zonas; `interim/` nunca
  viaja. Athena **es** la base de datos del equipo: lee los Parquet donde están,
  sin copiarlos, y `src/nube/consultar.consultar(sql)` devuelve un DataFrame. Por
  eso nadie necesita sincronizar `processed/` para trabajar.
- **`sitio/`** — HTML estático en GitHub Pages, sin build. Lee JSON de agregados,
  nunca la base: Pages sirve archivos y no puede guardar un secreto.

Dos módulos de procesamiento (`sinca.py`, `estaciones.py`) leen su entrada
**desde S3**, no del disco: exigen `--bucket` y `--perfil`. El resto lee de
`data/`.

### Modelo estrella (`data/processed/`, base Athena `aire_urgencias`)

| Tabla | Grano | La escribe |
|---|---|---|
| `hecho_urgencia` | establecimiento × día × causa × edad, particionado por `anio` | `procesamiento/deis.py` |
| `hecho_medicion` | estación × hora | `procesamiento/sinca.py` |
| `dim_tiempo` | día, con semana MMWR | `procesamiento/tiempo.py` |
| `dim_causa`, `dim_establecimiento` | — | `procesamiento/deis.py` |
| `dim_estacion` | estación de SINCA, con correcciones | `procesamiento/estaciones.py` |
| `dim_ciudad` | las tres ciudades y sus comunas | `procesamiento/ciudades.py` |
| `poblacion_comuna_anio`, `poblacion_ciudad_anio` | denominador por franja etaria | `procesamiento/poblacion.py` |
| `analitico_ciudad_semana` | ciudad × semana: exposición, desenlace, controles | `procesamiento/analitico.py` |
| `red_nacional_estacion`, `red_nacional_mes` | red SINCA de todo el país, MP2.5 diario agregado a mes | `procesamiento/red_nacional.py` |

Las edades del DEIS van **en columnas**, no despivotadas a filas: en Parquet
cuesta lo mismo en disco y menos al consultar.

Las dos tablas `red_nacional_*` son **contexto del mapa, no del análisis**: traen la
serie que SINCA ya entrega promediada a día, así que no entran a `hecho_medicion`
—que es horaria y conserva los tres estados de validación— ni a ninguna cifra del
estudio. Ver `docs/calidad/red_nacional_mapa.md`.

### Qué es una ciudad

Una ciudad no existe en los datos. Existe como conjunto de comunas del lado de la
salud y como conjunto de estaciones del lado del aire.
`src/procesamiento/geografia.py` fija esa correspondencia **por código de
comuna** y la comparten los dos lados; `ciudades.py auditar` verifica que
describan el mismo territorio. Una estación cuya comuna no está en ninguna lista
no pertenece a ninguna ciudad (`ciudad_de` devuelve `None`); no se le asigna la
más cercana. Al tocar esta definición, cambiar `geografia.py`, no una lista
copiada.

### Análisis

`src/analisis/asociacion.py` es la maquinaria (Poisson con efectos fijos de
estrato, quasi-Poisson, semilla `SEMILLA`); el notebook
`notebooks/analisis_mp25_urgencias.ipynb` es la narrativa. `urg_diarrea` está en
la tabla analítica como **control negativo** a propósito.
`src/analisis/spark_grano_fino.py` corre en la VM con `spark-submit`, no importa
nada de `src/` y lee las comunas desde `dim_ciudad`.

### Idioma de los módulos

Cada módulo ejecutable sigue el mismo patrón: docstring que explica **por qué**
está escrito así, `sys.path.insert(0, ...parents[2])` con `# noqa: E402` para
correr desde la raíz, subcomandos de `argparse` (`construir` / `verificar` /
`auditar` / `descargar`), y `logging.basicConfig` a `logs/<nombre>.log`. Los
docstrings guardan hallazgos que costaron horas: leerlos antes de tocar el
módulo.

## Trampas verificadas (no volver a descubrirlas)

- **Semana MMWR, no ISO.** El DEIS numera de domingo a sábado.
  `datetime.isocalendar()` y `strftime('%V')` **no se usan en el proyecto**: el
  desfase llega a seis días, del mismo orden que los rezagos que se miden.
  `tiempo.py validar` contrasta fila por fila contra el DEIS y se detiene si no
  coinciden al 100 %.
- **`pyarrow>=20`.** Los Parquet los escribe pyarrow 25 con `SizeStatistics`;
  pyarrow 19 falla con `OSError: Repetition level histogram size mismatch`, un
  error que no menciona la versión. Casi siempre significa estar corriendo con
  otro Python (un Anaconda viejo).
- **SINCA (Airviro).** `outtype=xcl` devuelve CSV; `outtype=csv` devuelve un GIF
  vacío con HTTP 200. Las barras del parámetro `macro` van **sin codificar**, así
  que la URL se arma como texto y no con `params=`. Fechas en `AAMMDD`, respuesta
  en latin-1 con `;`.
- **Macro de Airviro.** `diario.diario` existe y devuelve la misma cabecera que
  `horario.horario` con 24 veces menos filas. `mensual.mensual` y `diario.promedio`
  **no existen y no fallan**: responden HTTP 200 con un `text/plain` que dice
  «psgraph: Could not load macro». Validar tipo de contenido y cabecera, no el
  código de estado.
- **Teselas del mapa.** CARTO dejó de servir sin llave: responde HTTP 200 con un
  PNG que dice «API KEY REQUIRED» impreso encima. El sitio usa Esri Canvas, que
  no pide llave. Cualquier proveedor con llave queda fuera por diseño — Pages no
  puede guardar un secreto.
- **CGNAT.** Un 403 de CloudFront suele ser la IP, no el servidor. Distinguir
  siempre "sin permiso / bloqueado" de "no existe / vacío": llevan a decisiones
  opuestas.
- **Fuentes chilenas.** CSV con `;` y codificación latin-1/cp1252 con
  frecuencia. No asumir UTF-8 ni coma. Las páginas del INE y del DEIS listan sus
  archivos por JavaScript: el HTML no trae los enlaces y las rutas se dedujeron.
- **AWS.** Buckets públicos sin credenciales: `--no-sign-request` en el CLI,
  `Config(signature_version=UNSIGNED)` en boto3. Athena cobra por byte escaneado:
  filtrar por `anio` usa la partición.

## Fuentes

| Fuente | Rol | Acceso |
|---|---|---|
| SINCA (MMA) | **Única fuente de aire para Chile.** MP2.5 horario + meteorología | `src/ingesta/sinca_cliente.py` |
| DEIS (MINSAL) | Co-primaria: urgencias respiratorias | ZIP por año, ruta no enlazada |
| INE | Proyecciones de población: el denominador | XLSX por comuna y edad simple |
| CASEN | Combustible de calefacción: contexto regional, no covariable semanal | `.dta` por año |
| SatPM2.5 (ACAG) | MP2.5 satelital **mensual**: papel espacial, no temporal | `s3://satpmdata/` |
| OpenAQ | **Solo referencia internacional.** NO usar para datos chilenos | `s3://openaq-data-archive/` |
| Open-Meteo | Viento y temperatura actuales, solo en el sitio | API sin llave |
| Dimensiones | comunas, establecimientos, estaciones, calendario | construidas por el equipo |

### Regla sobre OpenAQ

OpenAQ es un agregador que cosecha los datos chilenos desde SINCA, y **no los
replica**: publica `round(media_móvil_24h + 10)`, sin marcas de validación y sin
meteorología (`docs/reconocimiento/hallazgos.md` §1.5). Usarlo como fuente de
MP2.5 chileno sería contar la misma medición dos veces, con sesgo. **Su único rol
es el marco de referencia internacional:** posicionar Santiago, Talcahuano y
Coyhaique frente a ciudades del mundo.

Cualquier consulta a OpenAQ que filtre por Chile para obtener mediciones de aire
es un error de diseño, salvo en el contraste explícito de validación descrito en
`docs/reconocimiento/`.

## Entorno

- Windows 10, i7-7700HQ, 16 GB RAM. La VM de Hadoop dispone de ~8 GB.
- Python 3.12 vía `uv`. PySpark **no** está entre las dependencias locales; la VM
  de Hadoop usa su propio intérprete.
- `pyodbc` lee los `.mdb` del DEIS con el driver de Access que Office ya instala
  en Windows; no hace falta `mdbtools`.
- AWS: bucket del equipo `aire-urgencias-2026-pr`, perfil `aire-admin` en
  `~/.aws/credentials`, base Athena `aire_urgencias`. Ninguna credencial en el
  código, en un notebook ni en el sitio.

## Estructura del repo

```
data/          raw/ (inmutable) · interim/ (regenerable) · processed/ (Parquet)
src/
  ingesta/         descarga y reconocimiento de fuentes (reconocer_*.py)
  procesamiento/   construcción del modelo estrella
  analisis/        maquinaria del análisis + trabajo de Spark
  nube/            S3, Glue, Athena, sincronización
  sitio/           exportación de los JSON del sitio
  rutas.py         todas las rutas se derivan de aquí; ninguna absoluta
docs/
  reconocimiento/  hallazgos sobre la estructura de las fuentes + evidencia JSON
  calidad/         una decisión de limpieza por documento (regla 4)
  nube/            cómo trabaja el equipo sobre S3
sitio/         HTML estático publicado en Pages; assets/datos/*.json versionados
               (nacional.json es opcional: el mapa degrada sin él)
notebooks/     análisis (local) y versión PySpark (Colab)
logs/
```

`Improve Chile MP2.5 Dashboard/` no está versionado ni forma parte del proyecto:
es un experimento de Figma Make (React + Vite). No tocarlo salvo que se pida.

## Convenciones

- Nada de rutas absolutas ni credenciales en el código; las rutas salen de
  `src/rutas.py`.
- Nombres de archivo: `fuente_alcance_periodo.ext`
  (ej. `sinca_mp25_2018-2024.parquet`).
- Formato intermedio y final: Parquet (23× más liviano que el CSV del DEIS, y
  columnar).
- Los procesos largos escriben a `logs/`, no a stdout.
- `data/` está en `.gitignore`; se versiona el código, no los datos. La única
  excepción deliberada es `sitio/assets/datos/`, que es resultado publicado
  —agregados, ~900 kB— y sin él el sitio se despliega vacío.

## Fuera de alcance

Causalidad · inferencia individual · app para ciudadanos · otros contaminantes
· pronóstico · atribución de fuentes · cobertura nacional · valorización
económica · mortalidad · datos clínicos individuales
