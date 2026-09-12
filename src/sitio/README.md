# `src/sitio/` — los datos del sitio público

Etapa 5. El [sitio](https://hungerforcoffe.github.io/aire-urgencias/) no tiene
backend: GitHub Pages sirve archivos y no guarda secretos, así que el sitio no
consulta Athena. Lee JSON agregados que estos módulos exportan con credenciales
locales, y esos JSON se versionan en `sitio/assets/datos/`.

| Módulo | Lee de | Escribe |
|---|---|---|
| `exportar.py` | Athena | `meta`, `estaciones`, `mensual`, `ciudades`, `semanal` |
| `exportar_nacional.py` | `data/processed/red_nacional_*`, en local, sin AWS | `nacional` |
| `exportar_modelo.py` | los CSV del cuaderno de análisis | `modelo` |
| `exportar_semanal.py` | los CSV extraídos del análisis semanal | `semanal_nt` |

`exportar_modelo.py` **no ajusta ningún modelo**: valida lo que llegó y lo publica.

Todos validan antes de escribir: si una consulta vuelve vacía, con menos filas de
las esperadas o con una columna entera en nulo, abortan y **dejan intactos los JSON
anteriores**. Un vacío publicado es peor que un error visible.

## Uso

```powershell
uv run python -m src.sitio.exportar
uv run python -m src.sitio.exportar --verificar      # relee sin volver a consultar
```

El sitio en sí —páginas, estilos y gráficos— está en [`sitio/`](../../sitio/).
