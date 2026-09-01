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
| ISP | Vigilancia de virus respiratorios: control del confusor | por verificar |
| Reanálisis meteorológico | Temperatura donde SINCA no mide; relleno de vacíos | API pública |
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

## Entorno

- Windows 10, i7-7700HQ, 16 GB RAM. La VM de Hadoop dispone de ~8 GB.
- Python fijado en 3.12 vía `uv` (ver `.python-version`). PySpark **no** está
  entre las dependencias locales; la VM de Hadoop usa su propio intérprete.
- **La conexión está detrás de CGNAT y CloudFront devuelve 403.** Si una
  descarga falla con 403 o timeout, es probable que sea la IP y no el
  servidor. Distinguir siempre "sin permiso / bloqueado" de "no existe /
  vacío" en los mensajes de error.
- AWS: buckets públicos, sin credenciales. Usar `--no-sign-request` en el CLI
  o `Config(signature_version=UNSIGNED)` en boto3.
- Fuentes chilenas: CSV con separador `;` y codificación `latin-1`/`cp1252`
  con frecuencia. No asumir UTF-8 ni coma.

## Estructura del repo

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
  reconocimiento/   # hallazgos sobre estructura de las fuentes
  calidad/          # reportes de calidad de datos
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

## Fuera de alcance

Causalidad · inferencia individual · app para ciudadanos · otros contaminantes
· pronóstico · atribución de fuentes · cobertura nacional · valorización
económica · mortalidad · datos clínicos individuales
