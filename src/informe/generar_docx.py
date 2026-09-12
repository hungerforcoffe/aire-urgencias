"""Arma el informe final del capstone inyectando el Markdown en la pauta .docx.

Qué hace
--------
Lee `docs/informe/informe_final.md` —que es la **fuente única** del informe— y
escribe `Informe_Final_Aire_y_Urgencias_v2.docx` rellenando la pauta oficial del
curso. La pauta original **no se toca**: se abre como plantilla y se escribe un
archivo nuevo, igual que la zona cruda del proyecto no se sobrescribe (regla 3).

Qué NO hace
-----------
No inventa contenido ni calcula nada. Todo lo que aparece en el .docx está en el
.md, y todo lo que el .md no sabe queda como «POR COMPLETAR» a la vista.

Por qué se genera y no se edita a mano
--------------------------------------
Si el .docx se editara directamente habría dos versiones del mismo informe y
terminarían divergiendo, que es exactamente el fallo que
`docs/calidad/analisis_semanal.md` documenta entre los notebooks del análisis
semanal y el informe .md de su autor: mismas tablas, números distintos, y sin
forma de saber cuál manda. Acá manda el .md, siempre.

Cómo inyecta sin romper el XML
------------------------------
La pauta no usa estilos con nombre: todo su formato es directo, así que no sirve
buscar «Heading2». Los anclajes se localizan por texto sobre los elementos de
primer nivel de `w:body`, cuyas posiciones exactas en bytes se obtienen con
`xml.parsers.expat`. El resto del documento se copia byte a byte — encabezados,
pies, la portada y las tablas de revisión quedan intactos.

No se usa `python-docx`: no está entre las dependencias del proyecto y el
tratamiento por offsets deja el archivo original mucho más intacto que una
reserialización completa del XML.

Markdown que entiende
---------------------
`## ` sección de la pauta · `### ` subtítulo · párrafos · `- ` viñetas ·
listas numeradas · tablas con `|` · bloques indentados con 4 espacios (código) ·
`> ` cita · `![pie](ruta)` imagen · `**negrita**` y `` `monoespaciado` ``.

Y dos bloques propios, que son los que le quitan al informe el aire de muro de
texto:

    ::: clave | Título del recuadro        (o trampa, regla, limite)
    El párrafo destacado.
    :::

    ::: cifras
    66.305.151 | filas en hecho_urgencia
    :::

Uso
---
    python -m src.informe.generar_docx construir
    python -m src.informe.generar_docx verificar
"""

from __future__ import annotations

import argparse
import logging
import re
import struct
import sys
import xml.parsers.expat
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.rutas import DOCS, LOGS, RAIZ, asegurar  # noqa: E402

log = logging.getLogger(__name__)

PLANTILLA = RAIZ / "SIC_Big_Data_Informe_Final_Proyecto_Capstone_ES.docx"
FUENTE_MD = DOCS / "informe" / "informe_final.md"
SALIDA = RAIZ / "Informe_Final_Aire_y_Urgencias_v2.docx"

# Las 15 secciones de la pauta, en el orden en que aparecen en el cuerpo del
# documento. Son las claves con las que se busca el anclaje y con las que el .md
# titula sus `##`.
SECCIONES = [
    "1.1. Información de Contexto",
    "1.2. Motivación y Objetivo",
    "1.3. Integrantes y Asignación de Roles",
    "1.4. Cronograma e Hitos",
    "2.1. Descripción del Escenario Simulado",
    "2.2. Selección y Descripción de los Datasets",
    "2.3. Pipeline de Ingesta de Datos",
    "2.4. Procesamiento de Transformación de Datos",
    "2.5. Consulta de Datos e Insights",
    "3.1. Scripts y Código de Ingesta de Datos",
    "3.2. Scripts y Código de Transformación de Datos",
    "3.3. Descripción y Muestra de los Datasets Transformados",
    "3.4. Visualización de Datos de los Resultados de Consulta",
    "4.1. Logros y Beneficios",
    "4.2. Mejoras Futuras",
]

# Encabezados de nivel superior: no reciben contenido, pero delimitan hasta
# dónde llega la región de relleno de la subsección anterior.
CIERRES = ["1. Introducción", "2. Ejecución del Proyecto", "3. Resultados",
           "4. Impacto Proyectado", "5. Revisión y Comentario de los Integrantes",
           "6. Revisión y Comentario del Instructor"]

# --- Medidas del documento -------------------------------------------------
# A4 (11906 twips) menos los márgenes de 1440 a cada lado, menos la sangría de
# 427 con la que la pauta indenta el cuerpo.
ANCHO_TWIPS = 11906 - 1440 - 1440 - 427
EMU_POR_TWIP = 635

TIPO = "SamsungOne-400"
TIPO_N = "SamsungOne-700"
MONO = "Consolas"
GRIS = "f2f2f2"       # fondo de los bloques de código
GRIS_CAB = "e7e7e7"   # fondo de la cabecera de las tablas
BORDE = "bfbfbf"


# ---------------------------------------------------------------------------
# Lectura de la fuente
# ---------------------------------------------------------------------------

def leer_fuente(ruta: Path) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Devuelve (metadatos, {sección: líneas}) desde el Markdown."""
    if not ruta.exists():
        raise SystemExit(f"No existe {ruta}.\n"
                         "Es la fuente del informe y no se genera sola.")
    texto = ruta.read_text(encoding="utf-8")

    meta: dict[str, str] = {}
    m = re.search(r"<!--\s*meta(.*?)-->", texto, re.S)
    if m:
        for linea in m.group(1).strip().splitlines():
            if ":" in linea:
                clave, valor = linea.split(":", 1)
                meta[clave.strip()] = valor.strip()

    secciones: dict[str, list[str]] = {}
    actual: str | None = None
    for linea in texto.splitlines():
        if linea.startswith("## "):
            actual = linea[3:].strip()
            secciones[actual] = []
        elif actual is not None:
            secciones[actual].append(linea)
    return meta, secciones


def bloques(lineas: list[str]) -> list[tuple[str, object]]:
    """Agrupa las líneas de una sección en bloques tipados."""
    salida: list[tuple[str, object]] = []
    i, n = 0, len(lineas)
    while i < n:
        linea = lineas[i]
        if not linea.strip():
            i += 1
            continue

        if linea.startswith("::: "):
            cabecera = linea[4:].strip()
            tipo, _, titulo = cabecera.partition("|")
            cuerpo = []
            i += 1
            while i < n and not lineas[i].startswith(":::"):
                cuerpo.append(lineas[i])
                i += 1
            i += 1  # el cierre
            if tipo.strip() == "cifras":
                salida.append(("cifras", [
                    tuple(x.split("|", 1)) for x in cuerpo if "|" in x]))
            else:
                salida.append(("recuadro",
                               (tipo.strip(), titulo.strip(), cuerpo)))
        elif linea.startswith("### "):
            salida.append(("h3", linea[4:].strip()))
            i += 1
        elif linea.startswith("!["):
            m = re.match(r"!\[(.*?)\]\((.*?)\)", linea)
            if m:
                salida.append(("img", (m.group(2), m.group(1))))
            i += 1
        elif linea.lstrip().startswith("|") and "|" in linea:
            filas = []
            while i < n and lineas[i].lstrip().startswith("|"):
                celdas = [c.strip() for c in lineas[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in celdas):
                    filas.append(celdas)
                i += 1
            salida.append(("tabla", filas))
        elif linea.startswith("    "):
            codigo = []
            while i < n and (lineas[i].startswith("    ") or not lineas[i].strip()):
                # Un salto en blanco solo corta el bloque si lo que sigue no es código.
                if not lineas[i].strip():
                    if i + 1 < n and lineas[i + 1].startswith("    "):
                        codigo.append("")
                        i += 1
                        continue
                    break
                codigo.append(lineas[i][4:])
                i += 1
            salida.append(("codigo", codigo))
        elif linea.startswith("> "):
            cita = []
            while i < n and lineas[i].startswith(">"):
                cita.append(lineas[i].lstrip(">").strip())
                i += 1
            salida.append(("cita", " ".join(cita)))
        elif linea.startswith("- "):
            items = []
            while i < n and (lineas[i].startswith("- ") or
                             (lineas[i].startswith("  ") and items and lineas[i].strip())):
                if lineas[i].startswith("- "):
                    items.append(lineas[i][2:].strip())
                else:
                    items[-1] += " " + lineas[i].strip()
                i += 1
            salida.append(("lista", items))
        elif re.match(r"^\d+\. ", linea):
            items = []
            while i < n and (re.match(r"^\d+\. ", lineas[i]) or
                             (lineas[i].startswith("   ") and items and lineas[i].strip())):
                m = re.match(r"^(\d+)\. (.*)", lineas[i])
                if m:
                    items.append(f"{m.group(1)}. {m.group(2)}")
                else:
                    items[-1] += " " + lineas[i].strip()
                i += 1
            salida.append(("numerada", items))
        else:
            parrafo = []
            corta = ("- ", "|", "### ", "> ", "    ", "![", ":::")
            while (i < n and lineas[i].strip()
                   and not lineas[i].startswith(corta)
                   and not re.match(r"^\d+\. ", lineas[i])):
                parrafo.append(lineas[i].strip())
                i += 1
            salida.append(("parrafo", " ".join(parrafo)))
    return salida


# ---------------------------------------------------------------------------
# Construcción del XML de WordprocessingML
# ---------------------------------------------------------------------------

def esc(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def runs(texto: str, sz: int, color: str = "000000", negrita: bool = False,
         tipo: str = TIPO) -> str:
    """Convierte **negrita** y `mono` en runs, respetando el resto del texto.

    La negrita se resuelve primero y su contenido se vuelve a recorrer, porque
    en el .md hay `código` dentro de **negrita** y en una sola pasada el tramo
    en negrita se traga las comillas invertidas y las imprime literales.
    """
    out = []
    for parte in re.split(r"(\*\*.+?\*\*)", texto):
        if not parte:
            continue
        if parte.startswith("**") and parte.endswith("**"):
            out.append(runs_mono(parte[2:-2], sz, color, True, TIPO_N))
        else:
            out.append(runs_mono(parte, sz, color, negrita, tipo))
    return "".join(out)


def runs_mono(texto: str, sz: int, color: str, negrita: bool, tipo: str) -> str:
    """Los runs de un tramo ya resuelto en negrita: solo queda el `mono`."""
    out = []
    for parte in re.split(r"(`[^`]+`)", texto):
        if not parte:
            continue
        t, f = parte, tipo
        if parte.startswith("`") and parte.endswith("`"):
            t, f = parte[1:-1], MONO
        rpr = (f'<w:rPr><w:rFonts w:ascii="{f}" w:cs="{f}" w:eastAsia="{f}" '
               f'w:hAnsi="{f}"/>{"<w:b/>" if negrita else ""}'
               f'<w:color w:val="{color}"/>'
               f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/><w:rtl w:val="0"/></w:rPr>')
        out.append(f'<w:r>{rpr}<w:t xml:space="preserve">{esc(t)}</w:t></w:r>')
    return "".join(out)


def p(texto: str, sz: int = 22, sangria: int = 427, colgante: int = 0,
      jc: str = "both", antes: int = 0, despues: int = 80, negrita: bool = False,
      color: str = "000000", sombra: str | None = None, tipo: str = TIPO,
      contenido: str | None = None) -> str:
    """Un párrafo con el formato directo que usa la pauta."""
    ind = f'<w:ind w:left="{sangria}" w:hanging="{colgante}"/>' if colgante \
        else f'<w:ind w:left="{sangria}" w:firstLine="0"/>'
    shd = f'<w:shd w:val="clear" w:color="auto" w:fill="{sombra}"/>' if sombra else ""
    cuerpo = contenido if contenido is not None else runs(texto, sz, color, negrita, tipo)
    # El orden de los hijos de w:pPr lo fija el esquema (CT_PPr) y no es
    # decorativo: widowControl, shd, spacing, ind, jc, rPr. Fuera de ese orden
    # Word abre el archivo como «contenido ilegible» y ofrece repararlo.
    return (f'<w:p><w:pPr><w:widowControl w:val="1"/>{shd}'
            f'<w:spacing w:before="{antes}" w:after="{despues}" w:line="264" '
            f'w:lineRule="auto"/>{ind}<w:jc w:val="{jc}"/>'
            f'<w:rPr><w:rFonts w:ascii="{TIPO}" w:cs="{TIPO}" w:eastAsia="{TIPO}" '
            f'w:hAnsi="{TIPO}"/><w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/></w:rPr>'
            f'</w:pPr>{cuerpo}</w:p>')


def tabla(filas: list[list[str]]) -> str:
    """Tabla con cabecera sombreada y bordes finos, ajustada al ancho útil."""
    if not filas:
        return ""
    ncol = max(len(f) for f in filas)
    ancho = ANCHO_TWIPS // ncol
    # El cuerpo va en 11 pt (comentario 4 de la revisión) y las tablas lo siguen
    # mientras el ancho de columna lo aguante. Pasadas las seis columnas, 11 pt
    # parte cada celda en cuatro líneas y se lee peor que un punto más chico.
    sz_celda = 22 if ncol <= 6 else (20 if ncol <= 8 else 18)
    bordes = "".join(
        f'<w:{lado} w:val="single" w:sz="4" w:space="0" w:color="{BORDE}"/>'
        for lado in ("top", "left", "bottom", "right", "insideH", "insideV"))
    grid = "".join(f'<w:gridCol w:w="{ancho}"/>' for _ in range(ncol))
    out = [f'<w:tbl><w:tblPr><w:tblW w:w="{ancho * ncol}" w:type="dxa"/>'
           f'<w:tblInd w:w="427" w:type="dxa"/><w:tblBorders>{bordes}</w:tblBorders>'
           f'<w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>{grid}</w:tblGrid>']
    for n, fila in enumerate(filas):
        cabecera = n == 0
        celdas = []
        for c in range(ncol):
            texto = fila[c] if c < len(fila) else ""
            parrafo = p(texto, sz=sz_celda, sangria=0, jc="left", despues=0,
                        negrita=cabecera)
            shd = (f'<w:shd w:val="clear" w:color="auto" w:fill="{GRIS_CAB}"/>'
                   if cabecera else "")
            celdas.append(f'<w:tc><w:tcPr><w:tcW w:w="{ancho}" w:type="dxa"/>'
                          f'{shd}<w:tcMar>'
                          f'<w:top w:w="40" w:type="dxa"/>'
                          f'<w:bottom w:w="40" w:type="dxa"/>'
                          f'<w:left w:w="80" w:type="dxa"/>'
                          f'<w:right w:w="80" w:type="dxa"/></w:tcMar>'
                          f'</w:tcPr>{parrafo}</w:tc>')
        cab = '<w:trPr><w:tblHeader/></w:trPr>' if cabecera else ""
        out.append(f'<w:tr>{cab}{"".join(celdas)}</w:tr>')
    out.append("</w:tbl>")
    # Un párrafo vacío después de la tabla: dos tablas seguidas se fusionan.
    out.append(p("", despues=80))
    return "".join(out)


# Los cuatro tonos de recuadro. El color no es decoración: dice de qué tipo es
# lo que hay dentro sin que el lector tenga que leerlo para saberlo.
RECUADROS = {
    "clave":  ("0d2240", "eef3fa", "EL HALLAZGO"),
    "trampa": ("b3382c", "fdf0ec", "LA TRAMPA"),
    "regla":  ("1a4a8a", "eef3fa", "REGLA DEL PROYECTO"),
    "limite": ("e85d1e", "fff3ec", "LO QUE NO SE PUEDE DECIR"),
}


def recuadro(tipo: str, titulo: str, lineas: list[str]) -> str:
    """Caja destacada: una tabla de una celda con barra lateral de color."""
    acento, fondo, rotulo = RECUADROS.get(tipo, RECUADROS["clave"])
    bordes = (f'<w:left w:val="single" w:sz="20" w:space="0" w:color="{acento}"/>'
              '<w:top w:val="nil"/><w:bottom w:val="nil"/><w:right w:val="nil"/>'
              '<w:insideH w:val="nil"/><w:insideV w:val="nil"/>')
    dentro = [p("", sz=17, sangria=0, jc="left", despues=30,
                contenido=runs(rotulo if not titulo else f"{rotulo}   ·   {titulo}",
                               17, acento, True, TIPO_N))]
    for bloque_tipo, dato in bloques(lineas):
        if bloque_tipo == "parrafo":
            dentro.append(p(dato, sz=22, sangria=0, despues=50))
        elif bloque_tipo == "lista":
            for it in dato:
                dentro.append(p("", sangria=280, colgante=200, sz=22, despues=30,
                                contenido=runs("•\t", 21) + runs(it, 21)))
        elif bloque_tipo == "codigo":
            for linea in dato:
                dentro.append(p(linea or " ", sz=18, sangria=140, jc="left",
                                despues=0, tipo=MONO))
    if dentro:
        # El último párrafo de la celda no lleva separación inferior.
        dentro[-1] = dentro[-1].replace('w:after="50"', 'w:after="0"')
    return (f'<w:tbl><w:tblPr><w:tblW w:w="{ANCHO_TWIPS}" w:type="dxa"/>'
            f'<w:tblInd w:w="427" w:type="dxa"/><w:tblBorders>{bordes}'
            f'</w:tblBorders><w:tblLayout w:type="fixed"/></w:tblPr>'
            f'<w:tblGrid><w:gridCol w:w="{ANCHO_TWIPS}"/></w:tblGrid><w:tr><w:tc>'
            f'<w:tcPr><w:tcW w:w="{ANCHO_TWIPS}" w:type="dxa"/>'
            f'<w:shd w:val="clear" w:color="auto" w:fill="{fondo}"/><w:tcMar>'
            f'<w:top w:w="140" w:type="dxa"/><w:bottom w:w="140" w:type="dxa"/>'
            f'<w:left w:w="200" w:type="dxa"/><w:right w:w="160" w:type="dxa"/>'
            f'</w:tcMar></w:tcPr>{"".join(dentro)}</w:tc></w:tr></w:tbl>'
            + p("", despues=100))


def cifras(pares: list[tuple[str, str]]) -> str:
    """Banda de cifras grandes: el titular numérico de una sección."""
    if not pares:
        return ""
    ancho = ANCHO_TWIPS // len(pares)
    celdas = []
    for valor, etiqueta in pares:
        celdas.append(
            f'<w:tc><w:tcPr><w:tcW w:w="{ancho}" w:type="dxa"/>'
            f'<w:tcMar><w:top w:w="60" w:type="dxa"/>'
            f'<w:bottom w:w="60" w:type="dxa"/></w:tcMar></w:tcPr>'
            + p("", sz=38, sangria=0, jc="left", despues=0,
                contenido=runs(valor.strip(), 38, "1a4a8a", True, TIPO_N))
            + p("", sz=17, sangria=0, jc="left", despues=0,
                contenido=runs(etiqueta.strip(), 17, "3d5a7a")))
        celdas[-1] += "</w:tc>"
    bordes = ('<w:top w:val="nil"/><w:left w:val="nil"/>'
              '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="c9dcf2"/>'
              '<w:right w:val="nil"/><w:insideH w:val="nil"/>'
              '<w:insideV w:val="nil"/>')
    grid = "".join(f'<w:gridCol w:w="{ancho}"/>' for _ in pares)
    return (f'<w:tbl><w:tblPr><w:tblW w:w="{ancho * len(pares)}" w:type="dxa"/>'
            f'<w:tblInd w:w="427" w:type="dxa"/><w:tblBorders>{bordes}'
            f'</w:tblBorders><w:tblLayout w:type="fixed"/></w:tblPr>'
            f'<w:tblGrid>{grid}</w:tblGrid><w:tr>{"".join(celdas)}</w:tr></w:tbl>'
            + p("", despues=120))


def medir_png(ruta: Path) -> tuple[int, int]:
    """Ancho y alto en píxeles, leídos del IHDR."""
    datos = ruta.read_bytes()
    if datos[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"{ruta} no es un PNG")
    ancho, alto = struct.unpack(">II", datos[16:24])
    return ancho, alto


def imagen(rid: str, idx: int, px: tuple[int, int], pie: str) -> str:
    """Imagen en línea, escalada al ancho útil, con su pie."""
    ancho_max = ANCHO_TWIPS * EMU_POR_TWIP
    cx, cy = px[0] * 9525, px[1] * 9525
    if cx > ancho_max:
        cy = int(cy * ancho_max / cx)
        cx = ancho_max
    dibujo = (
        f'<w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
        f'<wp:extent cx="{cx}" cy="{cy}"/>'
        f'<wp:effectExtent l="0" t="0" r="0" b="0"/>'
        f'<wp:docPr id="{900 + idx}" name="Figura {idx}" descr="{esc(pie)}"/>'
        f'<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/>'
        f'</wp:cNvGraphicFramePr><a:graphic>'
        f'<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{900 + idx}" name="Figura {idx}"/>'
        f'<pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="{rid}"/>'
        f'<a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr>'
        f'<a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
        f'</a:graphicData></a:graphic></wp:inline></w:drawing>')
    return (p("", jc="left", despues=40, contenido=f'<w:r>{dibujo}</w:r>') +
            p(f"Figura {idx}. {pie}", sz=18, jc="left", color="595959", despues=160))


def render(bs: list[tuple[str, object]], imagenes: list) -> str:
    """Convierte los bloques de una sección en XML."""
    out = []
    for tipo, dato in bs:
        if tipo == "h3":
            out.append(p(dato, sz=25, jc="left", antes=200, despues=70,
                         negrita=True, tipo=TIPO_N))
        elif tipo == "parrafo":
            out.append(p(dato))
        elif tipo == "cita":
            out.append(p(dato, sangria=700, jc="left", despues=100,
                         color="404040", sombra=GRIS))
        elif tipo == "lista":
            for it in dato:
                out.append(p("", sangria=760, colgante=220, despues=40,
                             contenido=runs("•\t", 22) + runs(it, 22)))
        elif tipo == "numerada":
            for it in dato:
                num, resto = it.split(". ", 1)
                out.append(p("", sangria=760, colgante=280, despues=40,
                             contenido=runs(f"{num}.\t", 22) + runs(resto, 22)))
        elif tipo == "tabla":
            out.append(tabla(dato))
        elif tipo == "recuadro":
            out.append(recuadro(*dato))
        elif tipo == "cifras":
            out.append(cifras(dato))
        elif tipo == "codigo":
            for n, linea in enumerate(dato):
                out.append(p(linea or " ", sz=18, sangria=560, jc="left",
                             despues=0 if n < len(dato) - 1 else 100,
                             sombra=GRIS, tipo=MONO))
        elif tipo == "img":
            ruta, pie = dato
            absoluta = RAIZ / ruta
            if not absoluta.exists():
                log.warning("figura ausente, se omite: %s", ruta)
                continue
            idx = len(imagenes) + 1
            rid = f"rIdFig{idx}"
            imagenes.append((rid, absoluta))
            out.append(imagen(rid, idx, medir_png(absoluta), pie))
    return "".join(out)


# ---------------------------------------------------------------------------
# Localización de los anclajes dentro del .docx
# ---------------------------------------------------------------------------

class Cuerpo:
    """Elementos de primer nivel de `w:body`, con su posición exacta en bytes."""

    def __init__(self, datos: bytes):
        self.elementos: list[dict] = []
        pila: list[str] = []
        actual: dict | None = None

        def inicio(nombre, _attrs):
            nonlocal actual
            pila.append(nombre)
            if len(pila) == 3 and pila[:2] == ["w:document", "w:body"]:
                actual = {"tag": nombre, "ini": par.CurrentByteIndex, "texto": []}

        def fin(nombre):
            nonlocal actual
            if len(pila) == 3 and actual is not None and actual["tag"] == nombre:
                i = par.CurrentByteIndex
                # Etiqueta vacía (<w:p/>): expat informa la misma posición.
                if i == actual["ini"]:
                    fin_tag = datos.index(b">", i) + 1
                else:
                    fin_tag = i + len(nombre.encode()) + 3
                actual["fin"] = fin_tag
                actual["texto"] = "".join(actual["texto"])
                self.elementos.append(actual)
                actual = None
            pila.pop()

        def texto(datos):
            if actual is not None:
                actual["texto"].append(datos)

        par = xml.parsers.expat.ParserCreate()
        par.StartElementHandler = inicio
        par.EndElementHandler = fin
        par.CharacterDataHandler = texto
        par.Parse(datos, True)

    def ultimo_que_empieza(self, prefijo: str) -> int | None:
        """Índice del último elemento cuyo texto empieza con `prefijo`.

        El último, no el primero: la misma cadena aparece antes en el índice de
        contenidos de la pauta, y ese no es el sitio donde va el texto.
        """
        norm = " ".join(prefijo.split())
        encontrado = None
        for n, el in enumerate(self.elementos):
            if " ".join(el["texto"].split()).startswith(norm):
                encontrado = n
        return encontrado


# ---------------------------------------------------------------------------
# Ensamblado
# ---------------------------------------------------------------------------

def portada(xml: str, meta: dict) -> str:
    """Rellena los marcadores de la portada por reemplazo directo."""
    integrantes = [x.strip() for x in meta.get("integrantes", "").split("|") if x.strip()]
    cambios = {
        "&lt; Título del Proyecto &gt;": meta.get("titulo", ""),
        "&lt; Fecha (DD/MM/AA) &gt;": meta.get("fecha", ""),
        "Nombre del Equipo": meta.get("equipo", ""),
    }
    for n in range(1, 6):
        nombre = integrantes[n - 1] if n <= len(integrantes) else ""
        cambios[f"&lt;Integrante {n}&gt;"] = nombre
    for viejo, nuevo in cambios.items():
        marca = f">{viejo}</w:t>"
        if marca not in xml:
            log.warning("marcador de portada no encontrado: %s", viejo)
            continue
        xml = xml.replace(marca, f">{esc(nuevo)}</w:t>", 1)
    return xml


def nombres_en_revision(xml: bytes, cuerpo: Cuerpo, integrantes: list[str]) -> bytes:
    """Escribe los nombres en la primera columna de la tabla de la sección 5."""
    idx = cuerpo.ultimo_que_empieza("NOMBRE")
    if idx is None:
        log.warning("no se encontró la tabla de revisión de integrantes")
        return xml
    el = cuerpo.elementos[idx]
    if el["tag"] != "w:tbl":
        return xml
    trozo = xml[el["ini"]:el["fin"]].decode("utf-8")
    filas = list(re.finditer(r"<w:tr\b.*?</w:tr>", trozo, re.S))
    # La primera fila es la cabecera; a partir de ahí, una fila por integrante.
    for n, nombre in enumerate(integrantes):
        if n + 1 >= len(filas):
            break
        fila = filas[n + 1]
        celda = re.search(r"<w:tc\b.*?</w:tc>", fila.group(0), re.S)
        if not celda:
            continue
        nueva_celda = celda.group(0).replace(
            "</w:p>", runs(nombre, 18) + "</w:p>", 1)
        nueva_fila = fila.group(0).replace(celda.group(0), nueva_celda, 1)
        trozo = trozo.replace(fila.group(0), nueva_fila, 1)
        filas = list(re.finditer(r"<w:tr\b.*?</w:tr>", trozo, re.S))
    return xml[:el["ini"]] + trozo.encode("utf-8") + xml[el["fin"]:]


def construir(args) -> int:
    meta, secciones = leer_fuente(FUENTE_MD)
    faltan = [s for s in SECCIONES if s not in secciones]
    if faltan:
        raise SystemExit("Al .md le faltan secciones:\n  " + "\n  ".join(faltan))

    with zipfile.ZipFile(PLANTILLA) as z:
        original = {n: z.read(n) for n in z.namelist()}
    xml = original["word/document.xml"]

    # 1. Portada y tabla de revisión, antes de mover offsets.
    xml = portada(xml.decode("utf-8"), meta).encode("utf-8")
    cuerpo = Cuerpo(xml)
    integrantes = [x.strip() for x in meta.get("integrantes", "").split("|") if x.strip()]
    xml = nombres_en_revision(xml, cuerpo, integrantes)

    # 2. Anclajes: se recalculan sobre el XML ya con la portada rellena.
    cuerpo = Cuerpo(xml)
    anclas: dict[str, int] = {}
    for clave in SECCIONES + CIERRES:
        idx = cuerpo.ultimo_que_empieza(clave)
        if idx is None:
            raise SystemExit(f"No se encontró en la pauta el encabezado: {clave!r}")
        anclas[clave] = idx
    orden = sorted(anclas.values())

    # 3. Se arma la lista de ediciones y se aplican de atrás hacia adelante, para
    #    que cada offset siga siendo válido cuando le toca su turno.
    imagenes: list[tuple[str, Path]] = []
    ediciones: list[tuple[int, int, bytes]] = []
    for clave in SECCIONES:
        idx = anclas[clave]
        el = cuerpo.elementos[idx]
        contenido = render(bloques(secciones[clave]), imagenes)
        # El relleno de la pauta son párrafos vacíos entre este encabezado y el
        # siguiente: se quitan, o el contenido nuevo queda flotando al final.
        siguiente = next((i for i in orden if i > idx), len(cuerpo.elementos))
        fin = el["fin"]
        for j in range(idx + 1, siguiente):
            otro = cuerpo.elementos[j]
            if otro["tag"] == "w:p" and not otro["texto"].strip():
                fin = otro["fin"]
            else:
                break
        ediciones.append((el["fin"], fin, contenido.encode("utf-8")))
        log.info("%-52s %5d bloques", clave, len(bloques(secciones[clave])))

    for ini, fin, datos in sorted(ediciones, reverse=True):
        xml = xml[:ini] + datos + xml[fin:]

    # 4. Las figuras: media, relaciones y tipo de contenido.
    rels = original["word/_rels/document.xml.rels"].decode("utf-8")
    nuevos: dict[str, bytes] = {}
    for n, (rid, ruta) in enumerate(imagenes, 1):
        # Nombre de parte propio y sin puntos intermedios: el del archivo de
        # origen puede traerlos (modelo_relacional_…_MP2.5.png) y no vale la pena
        # depender de cómo los interprete cada lector de OOXML.
        nombre = f"informe_{n}.png"
        nuevos[f"word/media/{nombre}"] = ruta.read_bytes()
        rels = rels.replace(
            "</Relationships>",
            f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships/image" '
            f'Target="media/{nombre}"/></Relationships>')
    tipos = original["[Content_Types].xml"].decode("utf-8")
    if 'Extension="png"' not in tipos:
        tipos = tipos.replace(
            "</Types>",
            '<Default Extension="png" ContentType="image/png"/></Types>')

    original["word/document.xml"] = xml
    original["word/_rels/document.xml.rels"] = rels.encode("utf-8")
    original["[Content_Types].xml"] = tipos.encode("utf-8")
    original.update(nuevos)

    salida = Path(args.salida) if args.salida else SALIDA
    try:
        with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
            for nombre, datos in original.items():
                if nombre.endswith("/"):
                    continue
                z.writestr(nombre, datos)
    except PermissionError:
        # En Windows, Word bloquea el archivo mientras lo tiene abierto, incluso
        # en modo de solo lectura, y el error de Python no dice cuál es la causa.
        raise SystemExit(
            f"No se pudo escribir {salida.name}: el archivo está abierto.\n"
            "Ciérralo en Word y vuelve a correr:\n"
            "    python -m src.informe.generar_docx construir") from None

    print(f"Escrito: {salida.name}  ({salida.stat().st_size / 1024:.0f} kB)")
    print(f"  secciones rellenas : {len(SECCIONES)}")
    print(f"  figuras incrustadas: {len(imagenes)}")
    print(f"  plantilla intacta  : {PLANTILLA.name}")
    pendientes = sum(1 for ls in secciones.values()
                     for linea in ls if "POR COMPLETAR" in linea)
    if pendientes:
        print(f"  · quedan {pendientes} marcas «POR COMPLETAR» en el .md, "
              "a la vista en el .docx")
    return 0


def verificar(args) -> int:
    """Relee el .docx escrito y comprueba que cada sección tenga contenido."""
    salida = Path(args.salida) if args.salida else SALIDA
    if not salida.exists():
        raise SystemExit(f"No existe {salida.name}.\n"
                         "Constrúyelo con: python -m src.informe.generar_docx construir")
    with zipfile.ZipFile(salida) as z:
        xml = z.read("word/document.xml")
        medios = [n for n in z.namelist() if n.startswith("word/media/")]
    cuerpo = Cuerpo(xml)

    problemas = []
    for clave in SECCIONES:
        idx = cuerpo.ultimo_que_empieza(clave)
        if idx is None:
            problemas.append(f"falta el encabezado {clave!r}")
            continue
        # Cuenta el texto de los elementos que siguen hasta el próximo encabezado.
        largo = 0
        for el in cuerpo.elementos[idx + 1:]:
            t = " ".join(el["texto"].split())
            if any(t.startswith(k) for k in SECCIONES + CIERRES):
                break
            largo += len(t)
        estado = "ok " if largo > 300 else "VACÍA"
        if largo <= 300:
            problemas.append(f"{clave!r} tiene solo {largo} caracteres")
        print(f"  {estado} {clave:<52} {largo:>6} caracteres")

    texto_completo = " ".join(el["texto"] for el in cuerpo.elementos)
    for marca in ("Título del Proyecto", "Fecha (DD/MM/AA)", "Integrante 1"):
        if marca in texto_completo:
            problemas.append(f"quedó sin rellenar el marcador {marca!r}")

    print(f"\n  figuras incrustadas: {len(medios) - 2} del informe "
          f"(+2 de la plantilla)")
    if problemas:
        print("\nProblemas:")
        for x in problemas:
            print(f"  · {x}")
        return 1
    print("\nTodas las secciones tienen contenido y la portada está rellena.")
    return 0


def main(argv=None):
    p_ = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p_.add_subparsers(dest="cmd", required=True)
    for nombre, fn in (("construir", construir), ("verificar", verificar)):
        s = sub.add_parser(nombre)
        s.add_argument("--salida", default=None, help="ruta del .docx a escribir")
        s.set_defaults(fn=fn)

    args = p_.parse_args(argv)
    # La consola de Windows viene en cp1252 y rompe los acentos de los mensajes.
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "generar_docx.log", encoding="utf-8")])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
