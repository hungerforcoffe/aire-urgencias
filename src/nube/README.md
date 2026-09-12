# `src/nube/` — S3, Glue y Athena

Etapa 3. **Athena es la base de datos del equipo.** Los Parquet viven en S3, el
catálogo de Glue sabe dónde está cada uno y qué columnas tiene, y Athena los
consulta con SQL donde están. Nadie copia los datos a su máquina para consultarlos.

| Módulo | Qué hace |
|---|---|
| `configurar_s3.py` | Prepara el bucket una sola vez: privado, versionado, cifrado, y un usuario IAM por integrante |
| `sincronizar.py` | Sube y baja `data/raw/` y `data/processed/` |
| `catalogo.py` | Crea la base y sus tablas en Glue. El DDL se genera **leyendo el esquema real del Parquet**, no se escribe a mano |
| `consultar.py` | Consulta Athena y devuelve un DataFrame |
| `historial.py` | Baja del historial de Athena el DDL vigente de cada tabla y escribe el anexo del informe |

La base `aire_urgencias` tiene **14 tablas**: las 12 del modelo en estrella y dos
materializaciones hechas durante el análisis. El DDL de cada una está en
[`docs/informe/anexos/athena_ddl.md`](../../docs/informe/anexos/athena_ddl.md).

## Uso

Todo lo que modifica AWS **simula por defecto**: sin `--aplicar` no toca la red.

```powershell
uv run python -m src.nube.consultar tablas
uv run python -m src.nube.consultar sql "SELECT * FROM dim_ciudad"
uv run python -m src.nube.historial tablas
```

Desde Python:

```python
from src.nube.consultar import consultar
df = consultar("SELECT ciudad_id, COUNT(*) FROM hecho_medicion "
               "WHERE anio = 2024 GROUP BY ciudad_id")
```

Las tablas de hechos están particionadas por `anio`: filtrar por año evita leer los
años que no se piden, y un `SELECT *` sin filtro sobre `hecho_urgencia` escanea la
tabla entera.

Las credenciales se leen del perfil local de `~/.aws/credentials` y nunca van en el
código. La operación del bucket y los permisos del equipo están en
[`docs/nube/`](../../docs/nube/).
