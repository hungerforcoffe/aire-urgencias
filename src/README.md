# `src/` — el código

Cinco etapas. El dato viaja en una sola dirección, de la fuente al resultado, y
cada paquete es una etapa.

| Etapa | Paquete | Escribe en |
|---|---|---|
| 1. Ingesta | [`ingesta/`](ingesta/) | `data/raw/` — inmutable, tal como lo entregó cada organismo |
| 2. Procesamiento | [`procesamiento/`](procesamiento/) | `data/processed/` — el modelo en estrella, en Parquet |
| 3. Nube | [`nube/`](nube/) | S3 + Glue + Athena: la base de datos del equipo |
| 4. Análisis | [`analisis/`](analisis/) | el modelo de asociación y el trabajo de Spark |
| 5. Publicación | [`sitio/`](sitio/) · [`informe/`](informe/) | los JSON del sitio y el informe final |

[`rutas.py`](rutas.py) es el único lugar con rutas: todo se deriva de la raíz del
repositorio, así el código corre igual en cualquier máquina.

## Cómo se ejecuta un módulo

Siempre como módulo y desde la raíz del repositorio:

```powershell
uv run python -m src.<paquete>.<modulo> <subcomando>
uv run python -m src.<paquete>.<modulo> --help     # la ayuda es el docstring
```

Todos los módulos siguen la misma forma, así que leer uno enseña a leer los demás:

- **El docstring es la documentación**: qué hace, qué *no* hace a propósito, y
  cómo se usa. `--help` lo muestra tal cual.
- Subcomandos con significado fijo: **`construir`** escribe y **`verificar`** relee
  lo escrito sin recalcular; en `nube/`, **`--simular`** es el comportamiento por
  defecto y nada toca AWS sin **`--aplicar`**.
- Los procesos largos escriben su registro en `logs/`.
- Los mensajes de error dicen qué comando arregla el problema.
