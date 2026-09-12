# `src/informe/` — el informe final y sus figuras

El informe tiene **una sola fuente**,
[`docs/informe/informe_final.md`](../../docs/informe/informe_final.md). De ahí
salen dos cosas, y ninguna se edita a mano: si se editan, la próxima generación
las pisa.

| Módulo | Escribe | Se versiona |
|---|---|---|
| `figuras.py` | `docs/informe/figuras/*.png`, desde `data/processed/` y `modelo.json` | sí |
| `markdown.py` | [`docs/informe/INFORME.md`](../../docs/informe/INFORME.md), lo que se lee en GitHub | sí |
| `generar_docx.py` | el `.docx` del curso, sobre la pauta oficial | **no** |

**Por qué el `.docx` no se versiona.** Se arma sobre la pauta del Samsung Innovation
Campus, cuya licencia prohíbe reproducirla fuera del curso, y la embebe entera.
`.gitignore` excluye todo `*.docx`.

**Por qué las figuras se generan.** Se dibujan cada vez desde los datos, así que no
pueden quedar desfasadas del resultado: si cambia una tabla, cambia la figura. Usan
la paleta del sitio, para que el informe y la página se vean como una sola cosa.

## Uso

```powershell
uv run python -m src.informe.figuras construir
uv run python -m src.informe.markdown construir
uv run python -m src.informe.markdown verificar
uv run python -m src.informe.generar_docx construir   # requiere la pauta en la raíz
```
