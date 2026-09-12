# `docs/informe/` — el informe final

**Para leer el informe, abre [`INFORME.md`](INFORME.md).**

| Archivo | Qué es |
|---|---|
| [`INFORME.md`](INFORME.md) | El informe, listo para leer en GitHub |
| [`informe_final.md`](informe_final.md) | Su **fuente**. Usa bloques propios que GitHub muestra como texto crudo; se edita esta y se regenera el resto |
| [`figuras/`](figuras/) | Las figuras. Las genera `src/informe/figuras.py` desde los datos, salvo `tabla_causas_cie10`, que se armó aparte |
| [`anexos/athena_ddl.md`](anexos/athena_ddl.md) | El DDL con el que se creó cada tabla de Athena, bajado de su historial de consultas |

`mp25.png` y `urgencias.png` son las versiones para presentación: una sola serie por
gráfico y sin texto de apoyo, porque en una diapositiva lo explica quien habla.

## Regenerar

```powershell
uv run python -m src.informe.figuras construir
uv run python -m src.informe.markdown construir
```

El `.docx` que se entregó al curso **no se versiona**: se arma sobre la pauta del
Samsung Innovation Campus, cuya licencia prohíbe reproducirla fuera del curso. Ver
[`src/informe/`](../../src/informe/).
