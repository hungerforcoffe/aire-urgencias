# Aire y Urgencias

Capstone de Big Data. Estudia la **asociación** entre material particulado fino
(MP2.5) y las consultas de urgencia por causa respiratoria en tres ciudades
chilenas.

## Pregunta de investigación

¿Cómo se asocia la variación semanal de MP2.5 con la variación semanal de
consultas de urgencia por causa respiratoria en Santiago, Talcahuano y Coyhaique
(2018–2024), controlando por temperatura, estacionalidad y período de pandemia?

## Alcance

| Dimensión | Definición |
|---|---|
| Ciudades | Santiago, Talcahuano, Coyhaique |
| Período | 2018–2024 |
| Contaminante | solo MP2.5 |
| Agregación | semanal (revisar si DEIS permite diario) |
| Rezagos | hasta 2 semanas |

**Fuera de alcance:** causalidad · inferencia individual · app para ciudadanos ·
otros contaminantes · pronóstico · atribución de fuentes · cobertura nacional ·
valorización económica · mortalidad · datos clínicos individuales.

## Reglas que no se rompen

1. **Asociación, nunca causalidad.** Ningún texto, nombre de variable, comentario
   o gráfico debe afirmar que la contaminación *causa* consultas. Es un estudio
   ecológico observacional.
2. **Acotar al final, no al principio.** La ingesta y el procesamiento operan a
   escala nacional/global. El filtro a tres ciudades ocurre en la última etapa.
   Si se filtra en la ingesta, el proyecto deja de ser Big Data.
3. **Nunca sobrescribir la zona cruda.** Los archivos de `data/raw/` son
   inmutables. Todo reproceso parte de ahí.
4. **Toda decisión de limpieza se documenta.** Si se descarta una semana por
   cobertura insuficiente, la regla queda escrita en `docs/calidad/` con su
   umbral y su justificación.

## Fuentes

| Fuente | Rol | Acceso |
|---|---|---|
| SINCA (MMA) | **Única fuente de aire para Chile.** MP2.5 horario + meteorología | descarga web por estación/año |
| DEIS (MINSAL) | Co-primaria: urgencias respiratorias | descarga de archivos |
| ISP | Vigilancia de virus respiratorios: control del confusor | por verificar |
| Reanálisis meteorológico | Temperatura donde SINCA no mide; relleno de vacíos | API pública |
| OpenAQ | **Solo referencia internacional.** NO usar para datos chilenos | `s3://openaq-data-archive/` |
| Dimensiones | comunas, establecimientos, estaciones, calendario epidemiológico | construidas por el equipo |

**Regla sobre OpenAQ.** OpenAQ cosecha los datos chilenos desde SINCA, pero **no los
replica**: publica `round(media_móvil_24h + 10)`, sin marcas de validación y sin
meteorología (ver `docs/reconocimiento/hallazgos.md` §1.5). Usarlo como fuente de
MP2.5 chileno introduciría un sesgo sistemático. Su único rol es posicionar las tres
ciudades frente al resto del mundo.

## Estructura

```
data/
  raw/          # inmutable, tal como se descargó
  interim/      # intermedios de limpieza
  processed/    # tablas finales
src/
  ingesta/
  procesamiento/
  analisis/
docs/
  reconocimiento/   # hallazgos sobre la estructura de las fuentes
  calidad/          # reportes de calidad de datos
notebooks/
logs/
```

`data/` y `logs/` están en `.gitignore`: se versiona el código, no los datos.
La estructura de carpetas se conserva mediante archivos `.gitkeep`.

## Puesta en marcha

Requiere [`uv`](https://docs.astral.sh/uv/). El entorno queda fijado en Python
3.12 (ver `.python-version`).

```powershell
uv sync                      # crea .venv e instala dependencias
.venv\Scripts\activate
```

Para generar un `requirements.txt` si el equipo lo necesita:

```powershell
uv export --no-hashes -o requirements.txt
```

## Convenciones

- Nada de rutas absolutas ni credenciales en el código.
- Nombres de archivo: `fuente_alcance_periodo.ext`
  (ej. `sinca_mp25_2018-2024.parquet`).
- Los procesos largos escriben a `logs/`, no a stdout.
- Formato intermedio y final: Parquet.

## Notas de entorno

- Windows 10, i7-7700HQ, 16 GB RAM. La VM de Hadoop dispone de ~8 GB.
- **PySpark no está en las dependencias locales**: la VM de Hadoop corre su
  propio intérprete. Si se necesita Spark en el equipo anfitrión, se agrega
  aparte y se verifica la compatibilidad con Python 3.12.
- **La conexión está detrás de CGNAT y CloudFront devuelve 403.** Si una descarga
  falla con 403 o timeout, lo más probable es que sea la IP y no el servidor. El
  código de ingesta debe distinguir siempre *sin permiso / bloqueado* de
  *no existe / vacío* en sus mensajes de error.
- AWS: los buckets son públicos y no se usan credenciales. Con `boto3`, esto
  significa `Config(signature_version=UNSIGNED)`; con el CLI, `--no-sign-request`.
- Las fuentes chilenas suelen entregar CSV con separador `;` y codificación
  `latin-1`/`cp1252`. No asumir UTF-8 ni coma.
