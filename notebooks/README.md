# Cómo correr los cuadernos

Dos cuadernos, con requisitos distintos:

| Cuaderno | Qué hace | Necesita |
|---|---|---|
| `analisis_mp25_urgencias.ipynb` | El análisis completo: QA, descriptivo, meteorología, rezagos y case-crossover | Python 3.12 + `data/processed/` |
| `spark_colab_aire_urgencias.ipynb` | El mismo pipeline en PySpark, para la parte de Big Data | Google Colab + los datos en Drive |

---

## El error que se lleva la primera tarde de todos

```
OSError: Repetition level histogram size mismatch
```

No dice nada útil, y no es un archivo corrupto: es **la versión de pyarrow**.

Los Parquet del proyecto los escribe pyarrow 25, que guarda `SizeStatistics` en
los metadatos, y **pyarrow 19 falla al leerlos**. Verificado: 19 falla, 20 lee.
Tampoco se puede evitar al escribir — probado con `write_page_index=False`,
`write_statistics=False` y los formatos 1.0, 2.4 y 2.6.

Por eso `pyproject.toml` exige `pyarrow>=20`. Si aparece ese error, **estás
corriendo con otro Python**, casi siempre un Anaconda con una versión vieja.

---

## Camino 1 · Alguien del equipo (tiene credenciales de AWS)

El código pesa 5 MB y los datos 209 MB, así que se separan: el código viaja, los
datos se bajan.

```bash
# 1. el entorno, fijado en el lock
uv sync

# 2. los datos procesados desde S3 (209 MB, una vez)
uv run python -m src.nube.sincronizar \
    --bucket aire-urgencias-2026-pr --perfil aire-admin \
    bajar --zona processed --aplicar

# 3. registrar el kernel del proyecto en Jupyter
uv run python -m ipykernel install --user \
    --name aire-urgencias --display-name "Python (aire-urgencias)"

# 4. abrir
uv run jupyter lab
```

**En Jupyter: Kernel → Change kernel → «Python (aire-urgencias)».** Ese paso es
el que evita el error de arriba.

No hace falta bajar `data/raw/` (3,5 GB): el cuaderno solo lee `processed/`.

---

## Camino 2 · Alguien de fuera del equipo, sin credenciales

Un paquete autocontenido. Se arma así:

```bash
# desde la raíz del repositorio
tar --exclude=.venv --exclude=.git --exclude=data/raw --exclude=data/interim \
    --exclude=__pycache__ -czf aire_urgencias.tar.gz .
```

Quedan ~214 MB: el código más `data/processed/`. Quien lo reciba:

```bash
tar -xzf aire_urgencias.tar.gz && cd aire_urgencias
pip install -r requirements.txt        # pyarrow queda fijado en 25.0.0
jupyter lab
```

`requirements.txt` está congelado con versiones exactas (`uv export`), así que no
depende de qué resuelva pip ese día.

---

## Camino 3 · Sin instalar nada, desde Athena

Si lo único que se quiere es **consultar** —no correr el análisis completo—, no
hace falta ni entorno ni datos:

```python
from src.nube.consultar import consultar
df = consultar("SELECT * FROM analitico_ciudad_semana")
```

Athena lee los Parquet directamente desde S3 y devuelve un DataFrame. Cada
integrante necesita su propio usuario IAM (ver `docs/nube/README.md`), y nunca
una clave dentro del cuaderno.

Ventaja de paso: **por este camino la versión de pyarrow da lo mismo**, porque
quien lee los archivos es el servidor de Athena y no la máquina de cada uno.

---

## Reproducibilidad

- **Semilla fija** (`asociacion.SEMILLA`) y rutas relativas: el cuaderno corre
  igual desde `notebooks/` o desde la raíz.
- **Sin archivos preparados a mano.** La limpieza de temperatura está
  reimplementada dentro del pipeline con sus umbrales escritos, así que no
  depende de ningún intermedio que alguien haya arreglado en su computador.
- **Las decisiones con umbral están documentadas** en `docs/calidad/`, no
  enterradas en el código.
- El cuaderno se valida ejecutándolo entero de arriba a abajo, no revisándolo a
  ojo.
