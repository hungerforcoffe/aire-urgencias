"""Publica el informe final como Markdown que GitHub renderiza directo.

Por qué existe
--------------
El informe tiene una sola fuente, `docs/informe/informe_final.md`, y de ahí
salen dos cosas. El `.docx` del curso no se versiona: lleva la pauta del Samsung
Innovation Campus, cuya licencia prohíbe reproducirla fuera del curso. Lo que se
publica en el repositorio es este Markdown.

La fuente no sirve tal cual para GitHub. Usa bloques propios (`::: clave`,
`::: cifras`) que GitHub muestra como texto crudo, sus imágenes apuntan desde la
raíz del repositorio, y le faltan los encabezados de primer nivel porque en el
`.docx` los pone la pauta. Este módulo traduce eso, en vez de mantener una segunda
copia a mano que se desincronizaría de la primera.

Qué traduce
-----------
    ::: clave     ->  > [!IMPORTANT]      avisos nativos de GitHub
    ::: trampa    ->  > [!WARNING]
    ::: regla     ->  > [!NOTE]
    ::: limite    ->  > [!CAUTION]
    ::: cifras    ->  tabla de una fila
    bloque indentado  ->  bloque cercado con ```
    docs/informe/figuras/x.png  ->  figuras/x.png

Lee la fuente con `leer_fuente()` y `bloques()` de `generar_docx.py`, así que las
dos salidas entienden exactamente el mismo Markdown.

Qué NO incluye
--------------
Las secciones 5 y 6 de la pauta —revisión de integrantes e instructor— son del
curso, no del informe.

Uso
---
    python -m src.informe.markdown construir
    python -m src.informe.markdown verificar
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.informe.generar_docx import FUENTE_MD, SECCIONES, bloques, leer_fuente  # noqa: E402
from src.rutas import DOCS, LOGS, RAIZ, asegurar  # noqa: E402

log = logging.getLogger(__name__)

SALIDA = DOCS / "informe" / "INFORME.md"

AVISOS = {"clave": "IMPORTANT", "trampa": "WARNING", "regla": "NOTE",
          "limite": "CAUTION"}

# El capítulo de cada sección de la pauta: el número antes del primer punto.
CAPITULOS = {"1": "1. Introducción", "2": "2. Ejecución del Proyecto",
             "3": "3. Resultados", "4": "4. Impacto Proyectado"}


def ruta_imagen(ruta: str) -> str:
    """De la raíz del repositorio a una ruta relativa a INFORME.md."""
    absoluta = (RAIZ / ruta).resolve()
    try:
        return absoluta.relative_to(SALIDA.parent.resolve()).as_posix()
    except ValueError:
        return Path("..", "..", ruta).as_posix()


def render(bs: list[tuple[str, object]], nivel_h3: str = "####") -> list[str]:
    """Bloques tipados de vuelta a Markdown estándar."""
    out: list[str] = []
    for tipo, dato in bs:
        if tipo == "h3":
            out += [f"{nivel_h3} {dato}", ""]
        elif tipo == "parrafo":
            out += [dato, ""]
        elif tipo == "lista":
            out += [f"- {it}" for it in dato] + [""]
        elif tipo == "numerada":
            out += list(dato) + [""]
        elif tipo == "cita":
            out += [f"> {dato}", ""]
        elif tipo == "codigo":
            out += ["```"] + list(dato) + ["```", ""]
        elif tipo == "tabla":
            filas = dato
            if filas:
                out.append("| " + " | ".join(filas[0]) + " |")
                out.append("|" + "---|" * len(filas[0]))
                out += ["| " + " | ".join(f) + " |" for f in filas[1:]]
                out.append("")
        elif tipo == "img":
            ruta, pie = dato
            out += [f"![{pie}]({ruta_imagen(ruta)})", "", f"*{pie}*", ""]
        elif tipo == "cifras":
            valores = [v.strip() for v, _ in dato]
            etiquetas = [e.strip() for _, e in dato]
            out.append("| " + " | ".join(f"**{v}**" for v in valores) + " |")
            out.append("|" + ":---:|" * len(valores))
            out.append("| " + " | ".join(etiquetas) + " |")
            out.append("")
        elif tipo == "recuadro":
            clase, titulo, lineas = dato
            cuerpo = render(bloques(lineas))
            while cuerpo and not cuerpo[-1]:
                cuerpo.pop()
            out.append(f"> [!{AVISOS.get(clase, 'NOTE')}]")
            if titulo:
                out.append(f"> **{titulo}**")
                out.append(">")
            out += [f"> {linea}" if linea else ">" for linea in cuerpo]
            out.append("")
    return out


def construir(_args) -> int:
    meta, secciones = leer_fuente(FUENTE_MD)
    faltan = [s for s in SECCIONES if s not in secciones]
    if faltan:
        raise SystemExit("Al .md fuente le faltan secciones:\n  " + "\n  ".join(faltan))

    integrantes = [x.strip() for x in meta.get("integrantes", "").split("|")
                   if x.strip()]
    lineas = [
        f"# {meta.get('titulo', 'Informe final')}",
        "",
        f"**{meta.get('equipo', '')}** · " + " · ".join(integrantes),
        "",
        "> Informe final del proyecto capstone de Big Data. Se genera desde "
        "[`informe_final.md`](informe_final.md) con "
        "`python -m src.informe.markdown construir`; no se edita a mano.",
        "",
    ]

    capitulo_actual = None
    for clave in SECCIONES:
        capitulo = CAPITULOS[clave.split(".", 1)[0]]
        if capitulo != capitulo_actual:
            lineas += [f"## {capitulo}", ""]
            capitulo_actual = capitulo
        lineas += [f"### {clave}", ""]
        lineas += render(bloques(secciones[clave]))

    # Sin líneas en blanco repetidas: GitHub las ignora, pero ensucian el diff.
    texto = re.sub(r"\n{3,}", "\n\n", "\n".join(lineas)).rstrip() + "\n"
    asegurar(SALIDA.parent)
    SALIDA.write_text(texto, encoding="utf-8")
    print(f"Escrito: {SALIDA.relative_to(RAIZ)}  "
          f"({len(texto.splitlines())} líneas, {len(texto) / 1024:.0f} kB)")
    return 0


def verificar(_args) -> int:
    if not SALIDA.exists():
        raise SystemExit(f"No existe {SALIDA.name}.\n"
                         "Constrúyelo con: python -m src.informe.markdown construir")
    texto = SALIDA.read_text(encoding="utf-8")
    problemas = []

    for clave in SECCIONES:
        if f"### {clave}" not in texto:
            problemas.append(f"falta la sección {clave!r}")

    crudos = [n for n, linea in enumerate(texto.splitlines(), 1)
              if linea.startswith(":::") or "<!-- meta" in linea]
    if crudos:
        problemas.append(f"bloques de la fuente sin traducir en las líneas {crudos[:5]}")

    imagenes = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", texto)
    rotas = [r for r in imagenes if not (SALIDA.parent / r).exists()]
    if rotas:
        problemas.append(f"imágenes que no resuelven: {rotas}")

    abiertos = texto.count("```") % 2
    if abiertos:
        problemas.append("hay un bloque de código sin cerrar")

    print(f"  secciones  : {sum(f'### {c}' in texto for c in SECCIONES)} de {len(SECCIONES)}")
    print(f"  imágenes   : {len(imagenes) - len(rotas)} de {len(imagenes)} resuelven")
    print(f"  avisos     : {len(re.findall(r'^> \[!', texto, re.M))}")
    if problemas:
        print("\nProblemas:")
        for x in problemas:
            print(f"  · {x}")
        return 1
    print("\nINFORME.md está completo y listo para GitHub.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("construir").set_defaults(fn=construir)
    sub.add_parser("verificar").set_defaults(fn=verificar)

    args = p.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "informe_markdown.log",
                                      encoding="utf-8")])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
