"""Figuras del informe final, dibujadas desde los datos que hay en el repositorio.

Por qué existe
--------------
Las figuras que había en `docs/reconocimiento/figuras/` son de la etapa de
reconocimiento —agosto, antes del modelo— y sus cifras están escritas a mano.
Servían para el informe de esa etapa; para el informe final quedaron viejas.

Estas se calculan cada vez desde `data/processed/` y desde los JSON publicados,
así que no pueden desincronizarse del resultado. Si una tabla cambia, la figura
cambia con ella.

Paleta
------
La del sitio del proyecto (`sitio/assets/css/estilo.css`), para que el informe y
la página publicada se vean como una sola cosa y no como dos trabajos distintos.

Iconos de AWS
-------------
Se dibujan aquí, no se descargan. Los oficiales viven tras CloudFront, que
devuelve 403 desde esta conexión (ver CLAUDE.md), y los del mirror de `awslabs`
son de 64 px: impresos se ven borrosos. Estos son representaciones estilizadas
con la silueta y el color de marca de cada servicio, en vector y a 300 dpi.

Uso
---
    python -m src.informe.figuras construir
    python -m src.informe.figuras verificar
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pyarrow.dataset as ds  # noqa: E402
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.rutas import DOCS, LOGS, PROCESSED, RAIZ, asegurar  # noqa: E402

log = logging.getLogger(__name__)

SALIDA = DOCS / "informe" / "figuras"
MODELO_JSON = RAIZ / "sitio" / "assets" / "datos" / "modelo.json"

# --- Paleta del sitio ------------------------------------------------------
NAVY = "#0d2240"
AZUL = "#1a4a8a"
AZUL_M = "#2563eb"
CELESTE = "#bfdbfe"
SENAL = "#e85d1e"
TINTA = "#0c1c30"
TINTA2 = "#3d5a7a"
TINTA3 = "#7a99b8"
FONDO = "#ffffff"
PANEL = "#f0f5fb"
LINEA = "#c9dcf2"

# --- Colores de marca de AWS ----------------------------------------------
AWS_S3 = "#e25444"        # el naranja rojizo del bucket clásico
AWS_S3_OSC = "#b3382c"
AWS_ANALITICA = "#8c4fff"  # la categoría a la que pertenecen Glue y Athena
AWS_ANALITICA_OSC = "#6b2fd6"

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
    "figure.facecolor": FONDO,
    "axes.facecolor": FONDO,
    "axes.edgecolor": LINEA,
    "axes.labelcolor": TINTA2,
    "text.color": TINTA,
    "xtick.color": TINTA3,
    "ytick.color": TINTA3,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 300,
    "savefig.dpi": 300,
})

CIUDADES = [("santiago", "Santiago"), ("talcahuano", "Talcahuano"),
            ("coyhaique", "Coyhaique")]


def guardar(fig, nombre: str) -> Path:
    asegurar(SALIDA)
    ruta = SALIDA / nombre
    fig.savefig(ruta, bbox_inches="tight", facecolor=FONDO, pad_inches=0.12)
    plt.close(fig)
    log.info("escrita %s", ruta.name)
    return ruta


# ---------------------------------------------------------------------------
# Piezas de dibujo reutilizables
# ---------------------------------------------------------------------------

def caja(ax, x, y, w, h, texto, sub=None, relleno=PANEL, borde=LINEA,
         color=TINTA, tam=8.5, negrita=True):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0,rounding_size=0.14",
        facecolor=relleno, edgecolor=borde, linewidth=1.1, zorder=2))
    cy = y + h / 2 + (0.09 if sub else 0)
    ax.text(x + w / 2, cy, texto, ha="center", va="center", fontsize=tam,
            color=color, fontweight="bold" if negrita else "normal", zorder=3)
    if sub:
        ax.text(x + w / 2, y + h / 2 - 0.17, sub, ha="center", va="center",
                fontsize=tam - 1.7, color=TINTA2, zorder=3)


def flecha(ax, p1, p2, color=TINTA3, ancho=1.4, estilo="-|>"):
    ax.add_patch(FancyArrowPatch(
        p1, p2, arrowstyle=estilo, mutation_scale=11, color=color,
        linewidth=ancho, shrinkA=2, shrinkB=2, zorder=1))


def icono_s3(ax, cx, cy, s=1.0):
    """El bucket de S3: cuerpo trapezoidal, tapa elíptica y las tres marcas."""
    w, h = 0.52 * s, 0.60 * s
    cuerpo = Polygon([(cx - w / 2, cy + h / 2), (cx + w / 2, cy + h / 2),
                      (cx + w / 2 * 0.72, cy - h / 2), (cx - w / 2 * 0.72, cy - h / 2)],
                     closed=True, facecolor=AWS_S3, edgecolor="none", zorder=3)
    ax.add_patch(cuerpo)
    # La tapa, un poco más oscura, es lo que hace que se lea como un balde.
    ax.add_patch(matplotlib.patches.Ellipse(
        (cx, cy + h / 2), w, 0.15 * s, facecolor=AWS_S3_OSC, edgecolor="none",
        zorder=4))
    ax.add_patch(matplotlib.patches.Ellipse(
        (cx, cy + h / 2), w * 0.80, 0.10 * s, facecolor="#f07a6a",
        edgecolor="none", zorder=5))
    for dx in (-0.11, 0.0, 0.11):
        ax.plot([cx + dx * s], [cy - 0.06 * s], marker="o", markersize=1.9 * s,
                color="#ffffff", zorder=6)


def icono_aws(ax, cx, cy, glifo: str, s=1.0, color=AWS_ANALITICA,
              osc=AWS_ANALITICA_OSC):
    """Cuadrado redondeado con degradado y un glifo blanco: la forma de AWS."""
    lado = 0.62 * s
    ax.add_patch(FancyBboxPatch(
        (cx - lado / 2, cy - lado / 2), lado, lado,
        boxstyle="round,pad=0,rounding_size=0.10", facecolor=osc,
        edgecolor="none", zorder=3))
    ax.add_patch(FancyBboxPatch(
        (cx - lado / 2, cy - lado / 2 + lado * 0.10), lado, lado * 0.90,
        boxstyle="round,pad=0,rounding_size=0.10", facecolor=color,
        edgecolor="none", zorder=4))
    if glifo == "atenea":
        # Columna clásica: capitel, fuste acanalado y basa.
        ax.plot([cx - 0.16 * s, cx + 0.16 * s], [cy + 0.16 * s] * 2,
                color="white", linewidth=2.4 * s, solid_capstyle="round", zorder=5)
        ax.plot([cx - 0.19 * s, cx + 0.19 * s], [cy - 0.17 * s] * 2,
                color="white", linewidth=2.4 * s, solid_capstyle="round", zorder=5)
        for dx in (-0.09, 0.0, 0.09):
            ax.plot([cx + dx * s] * 2, [cy - 0.15 * s, cy + 0.14 * s],
                    color="white", linewidth=1.6 * s, solid_capstyle="round",
                    zorder=5)
    elif glifo == "glue":
        # Tarro con gota: el catálogo que pega los esquemas.
        ax.add_patch(FancyBboxPatch(
            (cx - 0.13 * s, cy - 0.18 * s), 0.26 * s, 0.26 * s,
            boxstyle="round,pad=0,rounding_size=0.04", facecolor="white",
            edgecolor="none", zorder=5))
        ax.plot([cx - 0.05 * s, cx + 0.05 * s], [cy + 0.10 * s] * 2,
                color="white", linewidth=2.2 * s, solid_capstyle="round", zorder=5)
        ax.add_patch(Circle((cx + 0.13 * s, cy + 0.16 * s), 0.05 * s,
                            facecolor="white", edgecolor="none", zorder=5))


# ---------------------------------------------------------------------------
# Figura 1 — la arquitectura
# ---------------------------------------------------------------------------

def fig_arquitectura(cifras: dict) -> Path:
    fig, ax = plt.subplots(figsize=(11.2, 4.2))
    ax.set_xlim(0, 22)
    ax.set_ylim(0.6, 8.6)
    ax.axis("off")

    ax.text(0, 8.25, "De la fuente al análisis", fontsize=13.5,
            fontweight="bold", color=TINTA, ha="left")
    ax.text(0, 7.75, "El dato viaja en una sola dirección: se ingesta, se "
            "normaliza, se cataloga en la nube y se consulta desde ahí.",
            fontsize=8.6, color=TINTA2, ha="left")

    y, h = 4.3, 1.5
    etapas = [
        (0.0, 3.3, "Fuentes", "SINCA · DEIS · ISP\nINE · CASEN", PANEL, LINEA),
        (4.0, 3.3, "Ingesta", "scrapers propios\nDEIS · SINCA · ISP", "#e8f0fb",
         AZUL_M),
        (8.0, 3.3, "Procesamiento", "normaliza\ny valida", "#e8f0fb", AZUL_M),
        (16.6, 3.3, "Análisis", "case-crossover\ny series de tiempo", "#e8f0fb",
         AZUL_M),
    ]
    for x, w, titulo, sub, relleno, borde in etapas:
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0,rounding_size=0.18",
            facecolor=relleno, edgecolor=borde, linewidth=1.3, zorder=2))
        ax.text(x + w / 2, y + h - 0.42, titulo, ha="center", va="center",
                fontsize=9.5, fontweight="bold", color=NAVY, zorder=3)
        ax.text(x + w / 2, y + 0.46, sub, ha="center", va="center", fontsize=7.6,
                color=TINTA2, zorder=3, linespacing=1.5)

    # La nube: el bloque que sustituye a «que cada uno se baje los datos».
    ax.add_patch(FancyBboxPatch(
        (12.1, y - 0.45), 4.0, h + 0.9, boxstyle="round,pad=0,rounding_size=0.18",
        facecolor="#faf7ff", edgecolor=AWS_ANALITICA, linewidth=1.3,
        linestyle=(0, (4, 2)), zorder=2))
    ax.text(14.1, y + h + 0.18, "Nube  ·  AWS", ha="center", va="center",
            fontsize=8.4, fontweight="bold", color=AWS_ANALITICA_OSC, zorder=3)
    icono_s3(ax, 12.85, y + 0.92, s=1.35)
    icono_aws(ax, 14.1, y + 0.92, "glue", s=1.25)
    icono_aws(ax, 15.35, y + 0.92, "atenea", s=1.25)
    for cx, nombre in ((12.85, "S3"), (14.1, "Glue"), (15.35, "Athena")):
        ax.text(cx, y + 0.12, nombre, ha="center", va="center", fontsize=7.2,
                color=TINTA2, zorder=3)

    for x1, x2 in ((3.3, 4.0), (7.3, 8.0), (11.3, 12.1), (16.1, 16.6)):
        flecha(ax, (x1, y + h / 2), (x2, y + h / 2), color=TINTA3, ancho=1.6)

    # Las zonas de disco, colgando de la etapa que las escribe.
    zonas = [(5.65, "data/raw", "3,7 GB · inmutable"),
             (9.65, "data/processed", f"{cifras['filas_total']} filas · 209 MB")]
    for cx, nombre, sub in zonas:
        ax.add_patch(FancyBboxPatch(
            (cx - 1.55, 2.0), 3.1, 1.05,
            boxstyle="round,pad=0,rounding_size=0.14", facecolor=FONDO,
            edgecolor=LINEA, linewidth=1.1, zorder=2))
        ax.text(cx, 2.72, nombre, ha="center", va="center", fontsize=8.2,
                fontweight="bold", color=TINTA, zorder=3)
        ax.text(cx, 2.32, sub, ha="center", va="center", fontsize=7.2,
                color=SENAL, zorder=3)
        flecha(ax, (cx, y), (cx, 3.05), color=LINEA, ancho=1.2, estilo="-|>")

    ax.add_patch(FancyBboxPatch(
        (16.6, 2.0), 3.3, 1.05, boxstyle="round,pad=0,rounding_size=0.14",
        facecolor=FONDO, edgecolor=LINEA, linewidth=1.1, zorder=2))
    ax.text(18.25, 2.72, "Consulta SQL", ha="center", va="center", fontsize=8.2,
            fontweight="bold", color=TINTA, zorder=3)
    ax.text(18.25, 2.32, "sin copiar los datos", ha="center", va="center",
            fontsize=7.2, color=TINTA2, zorder=3)
    flecha(ax, (18.25, y), (18.25, 3.05), color=LINEA, ancho=1.2)
    return guardar(fig, "arquitectura.png")


# ---------------------------------------------------------------------------
# Figura 2 — el modelo en estrella, con las filas que tiene hoy
# ---------------------------------------------------------------------------

def fig_estrella(cifras: dict) -> Path:
    fig, ax = plt.subplots(figsize=(10.8, 6.0))
    ax.set_xlim(0, 20)
    ax.set_ylim(0, 12.2)
    ax.axis("off")
    f = cifras["filas"]

    def miles(n):
        return f"{n:,}".replace(",", ".")

    ax.text(0, 11.7, "El modelo en estrella de data/processed",
            fontsize=13.5, fontweight="bold", color=TINTA, ha="left")
    ax.text(0, 11.15, "Dos hechos con sus dimensiones, y una sola tabla "
            "analítica al final. El aire a la izquierda, la salud a la derecha, "
            "el calendario en medio.", fontsize=8.6, color=TINTA2, ha="left")

    # Dos columnas simétricas y una fila central: cada línea es vertical u
    # horizontal, así ninguna cruza a otra.
    CX_AIRE, CX_SALUD, CY = 3.6, 16.4, 6.7
    ANCHO_H, ALTO_H = 6.0, 1.9
    ANCHO_D, ALTO_D = 5.2, 1.05

    def dimension(cx, cy, nombre, filas, ancho=None):
        w = ancho or ANCHO_D
        ax.add_patch(FancyBboxPatch(
            (cx - w / 2, cy - ALTO_D / 2), w, ALTO_D,
            boxstyle="round,pad=0,rounding_size=0.13", facecolor=PANEL,
            edgecolor=AZUL_M, linewidth=1.0, zorder=3))
        ax.text(cx, cy + 0.17, nombre, ha="center", va="center", fontsize=8.2,
                fontweight="bold", color=NAVY, zorder=4)
        ax.text(cx, cy - 0.22, f"{miles(filas)} filas", ha="center", va="center",
                fontsize=7.2, color=TINTA2, zorder=4)

    def hecho(cx, nombre, grano, filas):
        ax.add_patch(FancyBboxPatch(
            (cx - ANCHO_H / 2, CY - ALTO_H / 2), ANCHO_H, ALTO_H,
            boxstyle="round,pad=0,rounding_size=0.16", facecolor=NAVY,
            edgecolor=NAVY, linewidth=1.2, zorder=3))
        ax.text(cx, CY + 0.48, nombre, ha="center", va="center", fontsize=10.2,
                fontweight="bold", color="white", zorder=4)
        ax.text(cx, CY + 0.04, grano, ha="center", va="center", fontsize=7.6,
                color=CELESTE, zorder=4)
        ax.text(cx, CY - 0.50, f"{miles(filas)} filas", ha="center", va="center",
                fontsize=9.0, fontweight="bold", color="#ffd9a8", zorder=4)

    hecho(CX_AIRE, "hecho_medicion", "estación × hora", f["hecho_medicion"])
    hecho(CX_SALUD, "hecho_urgencia", "establecimiento × día × causa",
          f["hecho_urgencia"])

    dimension(CX_AIRE, 9.9, "dim_estacion", f["dim_estacion"])
    dimension(CX_SALUD, 9.9, "dim_causa", f["dim_causa"])
    dimension(10.0, CY, "dim_tiempo", f["dim_tiempo"])

    # Fila inferior de dimensiones: las dos del grano de hecho a los extremos y
    # las dos que solo entran en la agregación final, al centro.
    for cx, nombre, filas in ((2.6, "dim_ciudad", f["dim_ciudad"]),
                              (7.5, "poblacion_ciudad_anio",
                               f["poblacion_ciudad_anio"]),
                              (12.5, "isp_virus_semana", f["isp_virus_semana"]),
                              (17.4, "dim_establecimiento",
                               f["dim_establecimiento"])):
        dimension(cx, 3.5, nombre, filas, ancho=4.4)

    for cx in (CX_AIRE, CX_SALUD):
        flecha(ax, (cx, 9.9 - ALTO_D / 2), (cx, CY + ALTO_H / 2),
               color=LINEA, ancho=1.1, estilo="-")
    for cx, destino in ((2.6, CX_AIRE), (17.4, CX_SALUD)):
        flecha(ax, (cx, 3.5 + ALTO_D / 2), (destino, CY - ALTO_H / 2),
               color=LINEA, ancho=1.1, estilo="-")
    flecha(ax, (10.0 - ANCHO_D / 2, CY), (CX_AIRE + ANCHO_H / 2, CY),
           color=LINEA, ancho=1.1, estilo="-")
    flecha(ax, (10.0 + ANCHO_D / 2, CY), (CX_SALUD - ANCHO_H / 2, CY),
           color=LINEA, ancho=1.1, estilo="-")

    ax.add_patch(FancyBboxPatch(
        (6.0, 0.15), 8.0, 1.40, boxstyle="round,pad=0,rounding_size=0.16",
        facecolor="#fff1e8", edgecolor=SENAL, linewidth=1.6, zorder=4))
    ax.text(10.0, 1.14, "analitico_ciudad_semana", ha="center", va="center",
            fontsize=9.8, fontweight="bold", color=SENAL, zorder=5)
    ax.text(10.0, 0.75, f"ciudad × semana epidemiológica  ·  "
            f"{miles(f['analitico_ciudad_semana'])} filas × 50 columnas",
            ha="center", va="center", fontsize=7.6, color=TINTA2, zorder=5)
    ax.text(10.0, 0.42, "el único recorte a tres ciudades de toda la cadena",
            ha="center", va="center", fontsize=7.0, color=TINTA3,
            style="italic", zorder=5)

    # Una sola flecha al final, y no seis: seis se cruzarían entre ellas y con
    # las cajas de la fila de abajo.
    flecha(ax, (10.0, 2.94), (10.0, 1.60), color=SENAL, ancho=2.0)
    ax.text(10.35, 2.28, "se cruza todo lo anterior", ha="left", va="center",
            fontsize=7.2, color=SENAL, style="italic", zorder=5)
    return guardar(fig, "estrella.png")


# ---------------------------------------------------------------------------
# Figura 3 — las dos series, con datos de la tabla analítica
# ---------------------------------------------------------------------------

def fig_series() -> Path:
    tabla = ds.dataset(PROCESSED / "analitico_ciudad_semana", format="parquet",
                       partitioning="hive").to_table().to_pandas()
    tabla = tabla.sort_values("semana_id")
    fig, ejes = plt.subplots(3, 1, figsize=(10.6, 6.4), sharex=True)
    fig.suptitle("Cada invierno suben las dos, y ese es justo el problema",
                 fontsize=13, fontweight="bold", color=TINTA, x=0.09, ha="left",
                 y=0.985)
    fig.text(0.09, 0.935, "MP2.5 semanal y consultas de urgencia respiratoria "
             "por 100.000 habitantes. Coinciden en el tiempo sin que una "
             "explique a la otra: el calendario mueve a las dos.",
             fontsize=8.4, color=TINTA2, ha="left")

    for ax, (cid, nombre) in zip(ejes, CIUDADES, strict=True):
        d = tabla[tabla.ciudad_id == cid]
        x = np.arange(len(d))
        ax.plot(x, d.mp25_media, color=SENAL, linewidth=1.0, zorder=3)
        ax.fill_between(x, 0, d.mp25_media, color=SENAL, alpha=0.13, zorder=2)
        ax.set_ylabel("MP2.5\nµg/m³", fontsize=7.6, color=SENAL, rotation=0,
                      ha="right", va="center", labelpad=14)
        ax.tick_params(labelsize=7)
        ax2 = ax.twinx()
        ax2.plot(x, d.tasa_resp_100k, color=AZUL_M, linewidth=1.0, zorder=3)
        ax2.set_ylabel("urgencias\npor 100k", fontsize=7.6, color=AZUL_M,
                       rotation=0, ha="left", va="center", labelpad=14)
        ax2.tick_params(labelsize=7, colors=TINTA3)
        ax2.spines["top"].set_visible(False)
        for eje in (ax, ax2):
            eje.spines["right"].set_visible(False)
        # Fondo bajo el rótulo: en Talcahuano la serie arranca alta y el
        # nombre de la ciudad quedaba encima de la línea.
        ax.text(0.006, 0.86, nombre, transform=ax.transAxes, fontsize=9.4,
                fontweight="bold", color=NAVY, ha="left",
                bbox=dict(facecolor=FONDO, edgecolor="none", pad=1.6,
                          alpha=0.85))
        ax.grid(axis="y", color=LINEA, linewidth=0.5, alpha=0.7)
        ax.set_axisbelow(True)

    d0 = tabla[tabla.ciudad_id == "santiago"]
    pos, eti = marcas_de_anio(d0.semana_id)
    ejes[-1].set_xticks(pos)
    ejes[-1].set_xticklabels(eti, fontsize=7.6)
    fig.text(0.09, 0.02, f"{len(d0)} semanas epidemiológicas por ciudad, "
             f"{tabla.semana_id.min()} a {tabla.semana_id.max()}.  "
             "Fuente: analitico_ciudad_semana.", fontsize=7.2, color=TINTA3,
             ha="left")
    fig.subplots_adjust(top=0.90, bottom=0.10, hspace=0.22)
    return guardar(fig, "series.png")


def marcas_de_anio(semanas) -> tuple[list[int], list[str]]:
    """Posición y etiqueta del primer punto de cada año, para el eje x.

    Las semanas son etiquetas (`2023-W26`), no fechas, así que el eje es un
    índice y las marcas hay que buscarlas: la primera semana que se ve de cada
    año es la que lleva el rótulo.
    """
    vistas: set[str] = set()
    pos: list[int] = []
    eti: list[str] = []
    for i, s in enumerate(semanas):
        anio = s[:4]
        if anio not in vistas:
            vistas.add(anio)
            pos.append(i)
            eti.append(anio)
    return pos, eti


# ---------------------------------------------------------------------------
# Figura 3b — solo las urgencias
# ---------------------------------------------------------------------------

def panel_una_serie(columna: str, color: str, titulo: str, bajada: str,
                    etiqueta: str, nombre: str, nota: str = "",
                    escala_comun: bool = False,
                    referencia: tuple[float, str] | None = None,
                    escala_texto: float = 1.0,
                    tamano: tuple[float, float] = (10.6, 6.4),
                    con_pie: bool = True) -> Path:
    """Tres paneles apilados con una sola serie por ciudad, línea y área.

    Es la mitad de `fig_series`: el mismo eje de tiempo y el mismo orden de
    ciudades, pero con una variable en vez de dos. Sirve para mirar la
    exposición y el desenlace por separado, sin que el eje gemelo sugiera una
    correspondencia punto a punto que el estudio no puede afirmar.

    `escala_comun` pone las tres ciudades en el mismo eje vertical. Cuesta
    detalle en la ciudad más baja y a cambio hace comparable la altura, que es
    la única forma de que una línea de referencia horizontal signifique lo mismo
    en los tres paneles: con un eje por ciudad quedaría a tres alturas
    distintas y no se podría leer como un umbral único.
    """
    tabla = ds.dataset(PROCESSED / "analitico_ciudad_semana", format="parquet",
                       partitioning="hive").to_table().to_pandas()
    tabla = tabla.sort_values("semana_id")
    t = escala_texto

    fig, ejes = plt.subplots(3, 1, figsize=tamano, sharex=True,
                             sharey=escala_comun)
    # La cabecera se posiciona en fracción de figura, así que al agrandar la
    # letra hay que recalcularla: con un desplazamiento fijo el subtítulo se
    # sube encima del título en cuanto `escala_texto` pasa de 1.
    # Una figura de diapositiva va sin bajada y sin pie: lo explica quien
    # presenta. `bajada=""` y `con_pie=False` los apagan, y el alto que ocupaban
    # se lo queda el gráfico.
    alto_titulo = (13 * t) / 72 / tamano[1] * 1.5
    alto_bajada = (8.4 * t) / 72 / tamano[1] * 1.45
    y_bajada = 0.985 - alto_titulo
    fig.suptitle(titulo, fontsize=13 * t, fontweight="bold", color=TINTA,
                 x=0.09, ha="left", y=0.985, va="top")
    if bajada:
        fig.text(0.09, y_bajada, bajada, fontsize=8.4 * t, color=TINTA2,
                 ha="left", va="top", linespacing=1.45)

    tope = tabla[columna].max() * 1.06 if escala_comun else None
    for ax, (cid, ciudad) in zip(ejes, CIUDADES, strict=True):
        d = tabla[tabla.ciudad_id == cid]
        x = np.arange(len(d))
        serie = d[columna]
        ax.fill_between(x, 0, serie, color=color, alpha=0.16, zorder=2)
        ax.plot(x, serie, color=color, linewidth=1.1, zorder=3)
        ax.set_ylabel(etiqueta, fontsize=7.6 * t, color=color, rotation=0,
                      ha="right", va="center", labelpad=16 * t)
        ax.set_ylim(0, tope)
        ax.set_xlim(0, len(d) - 1)
        ax.tick_params(labelsize=7 * t)
        if referencia:
            valor, rotulo = referencia
            ax.axhline(valor, color=NAVY, linewidth=1.4, linestyle=(0, (5, 3)),
                       zorder=4)
            # El rótulo se repite en los tres paneles a propósito. Con un eje
            # por ciudad la línea cae a distinta altura en cada uno, y esa
            # altura es el mensaje: en Santiago la serie la roza, en Coyhaique
            # queda abajo del todo. Rotularla una sola vez obligaría a deducir
            # que las tres rayas son la misma cifra.
            # Fuera del área de dibujo: dentro, en cualquier borde, terminaba
            # encima de la serie en alguna de las tres ciudades.
            ax.text(1.012, valor, rotulo, transform=ax.get_yaxis_transform(),
                    ha="left", va="center", fontsize=7.4 * t, color=NAVY,
                    fontweight="bold", zorder=5, clip_on=False)
        ax.text(0.006, 0.86, ciudad, transform=ax.transAxes,
                fontsize=9.4 * t, fontweight="bold", color=NAVY, ha="left",
                bbox=dict(facecolor=FONDO, edgecolor="none", pad=1.6,
                          alpha=0.85))
        ax.grid(axis="y", color=LINEA, linewidth=0.5, alpha=0.7)
        ax.set_axisbelow(True)

    d0 = tabla[tabla.ciudad_id == "santiago"]
    pos, eti = marcas_de_anio(d0.semana_id)
    ejes[-1].set_xticks(pos)
    ejes[-1].set_xticklabels(eti, fontsize=7.6 * t)
    if con_pie:
        pie = (f"{len(d0)} semanas epidemiológicas por ciudad, "
               f"{tabla.semana_id.min()} a {tabla.semana_id.max()}.  {nota}"
               "Fuente: analitico_ciudad_semana.")
        alto_pie = (7.2 * t) / 72 / tamano[1] * 1.45
        fig.text(0.09, 0.02, pie, fontsize=7.2 * t, color=TINTA3, ha="left",
                 va="bottom", linespacing=1.45)
        abajo = 0.055 + alto_pie * (pie.count("\n") + 1) + 0.03
    else:
        abajo = 0.07

    arriba = 0.985 - alto_titulo - 0.02
    if bajada:
        arriba = y_bajada - alto_bajada * (bajada.count("\n") + 1) - 0.025
    fig.subplots_adjust(top=arriba, bottom=abajo, hspace=0.22)
    return guardar(fig, nombre)


def fig_urgencias() -> Path:
    """Solo el desenlace: las consultas de urgencia respiratoria."""
    return panel_una_serie(
        "tasa_resp_100k", AZUL_M,
        "Las urgencias respiratorias, solas",
        "Consultas de urgencia por causa respiratoria, por 100.000 habitantes "
        "y semana epidemiológica. El pico de invierno se repite todos los años; "
        "el hueco de 2020-2021 es la pandemia.",
        "urgencias\npor 100k", "urgencias.png",
        nota="Cada ciudad tiene su propia escala: lo comparable es la forma, "
             "no la altura.  ")


def fig_mp25() -> Path:
    """Solo la exposición, cada ciudad en su escala y la norma como patrón.

    Pensada para proyectarse. La magnitud se lee contra una **constante** —la
    norma de 24 horas del D.S. 12/2011— y no contra el tamaño del dibujo: cada
    ciudad conserva su propio eje, y lo que cambia de panel a panel es dónde
    cae la raya de 50 µg/m³. En Santiago los máximos apenas la tocan; en
    Coyhaique queda pegada al piso y la serie la cuadruplica.

    Un eje común haría lo contrario: aplastaría a Santiago y Talcahuano hasta
    volverlos ilegibles, y la raya perdería su papel de patrón porque ya no
    habría nada que comparar contra ella.
    """
    return panel_una_serie(
        "mp25_media", SENAL,
        "MP2.5 semanal en las tres ciudades",
        "",                       # en una diapositiva, la bajada la dice quien habla
        "MP2.5\nµg/m³", "mp25.png",
        referencia=(50, "norma\n50 µg/m³"),
        escala_texto=1.35,
        tamano=(13.3, 7.0),
        con_pie=False)


# ---------------------------------------------------------------------------
# Figura 4 — el bosque, con los controles negativos dentro
# ---------------------------------------------------------------------------

def fig_bosque() -> Path:
    m = json.loads(MODELO_JSON.read_text(encoding="utf-8"))
    grupos = [
        ("EL RESULTADO PRINCIPAL", "clave",
         [(r["analisis"], r) for r in m["principal"]]),
        ("POR CIUDAD", "ciudad",
         [(r["ciudad"].capitalize(), r)
          for r in sorted(m["ciudad"], key=lambda x: -x["rr10"])]),
        ("CONTROLES NEGATIVOS — deberían dar cero", "control",
         [(r["etiqueta"], r) for r in m["controles_negativos"]]),
    ]
    n_filas = sum(len(g[2]) + 1 for g in grupos)
    fig, ax = plt.subplots(figsize=(10.2, 0.36 * n_filas + 2.0))
    color = {"clave": NAVY, "ciudad": AZUL_M, "control": SENAL}

    ys, etiquetas, y = [], [], n_filas
    for titulo, tipo, filas in grupos:
        y -= 1
        c = color[tipo]
        # El título del grupo va como etiqueta del eje, en versalitas de color.
        ys.append(y)
        etiquetas.append(titulo)
        for nombre, r in filas:
            y -= 1
            ys.append(y)
            etiquetas.append(nombre)
            ax.plot([r["ic_inf"], r["ic_sup"]], [y, y], color=c, linewidth=2.0,
                    solid_capstyle="round", zorder=3)
            ax.plot([r["rr10"]], [y], marker="D" if tipo == "clave" else "o",
                    markersize=6.5 if tipo == "clave" else 5.4, color=c,
                    zorder=4)
            ax.text(r["ic_sup"] + 0.0008, y, f'{(r["rr10"] - 1) * 100:+.2f} %',
                    va="center", ha="left", fontsize=7.8, color=c,
                    fontweight="bold")

    ax.axvline(1.0, color=TINTA3, linewidth=1.0, linestyle=(0, (4, 3)), zorder=2)
    ax.set_yticks(ys)
    ax.set_yticklabels(etiquetas, fontsize=8.4)
    for etiqueta, texto in zip(ax.get_yticklabels(), etiquetas, strict=True):
        for titulo, tipo, _ in grupos:
            if texto == titulo:
                etiqueta.set_fontsize(7.4)
                etiqueta.set_fontweight("bold")
                etiqueta.set_color(color[tipo])
    ax.set_ylim(-0.8, n_filas - 0.4)
    ax.set_xlabel("Riesgo relativo por cada +10 µg/m³ de MP2.5  (IC 95 %)",
                  fontsize=8.4)
    ax.tick_params(labelsize=7.6)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="x", color=LINEA, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.set_title("Los controles negativos dan más que el desenlace de interés",
                 fontsize=12.6, fontweight="bold", color=TINTA, loc="left",
                 pad=26)
    ax.text(0, 1.035, "Respirar partículas no fractura un hueso ni provoca un "
            "choque: esas dos barras deberían dar cero. Miden sesgo, no aire.",
            transform=ax.transAxes, fontsize=8.4, color=SENAL, ha="left")
    return guardar(fig, "bosque.png")


# ---------------------------------------------------------------------------
# Figura 5 — la curva de rezagos
# ---------------------------------------------------------------------------

def fig_rezagos() -> Path:
    m = json.loads(MODELO_JSON.read_text(encoding="utf-8"))
    lags = sorted(m["lags"], key=lambda r: r["lag"])
    x = [r["lag"] for r in lags]
    rr = [(r["rr10"] - 1) * 100 for r in lags]
    lo = [(r["ic_inf"] - 1) * 100 for r in lags]
    hi = [(r["ic_sup"] - 1) * 100 for r in lags]

    fig, ax = plt.subplots(figsize=(9.0, 3.7))
    ax.fill_between(x, lo, hi, color=AZUL_M, alpha=0.15, zorder=2)
    ax.plot(x, rr, color=AZUL_M, linewidth=1.8, marker="o", markersize=5,
            zorder=3)
    ax.axhline(0, color=TINTA3, linewidth=1.0, linestyle=(0, (4, 3)), zorder=1)
    ax.set_xticks(x)
    ax.set_xlabel("Días de rezago entre la exposición y la consulta", fontsize=8.4)
    ax.set_ylabel("Cambio por +10 µg/m³", fontsize=8.4)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:+.1f} %")
    ax.tick_params(labelsize=7.6)
    ax.grid(axis="y", color=LINEA, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.set_title("Casi todo está en el día 0, y se apaga al segundo",
                 fontsize=12.6, fontweight="bold", color=TINTA, loc="left",
                 pad=22)
    ax.text(0, 1.045, "Una respuesta que dura más de dos días no sería "
            "compatible con una exposición aguda.", transform=ax.transAxes,
            fontsize=8.4, color=TINTA2, ha="left")
    ax.annotate("día 0", xy=(0, rr[0]), xytext=(0.55, rr[0] + 0.16),
                fontsize=8, color=AZUL_M, fontweight="bold",
                arrowprops=dict(arrowstyle="-", color=AZUL_M, linewidth=0.9))
    return guardar(fig, "rezagos.png")


# ---------------------------------------------------------------------------
# Figura 6 — el embudo: de 3,7 GB a 1.350 filas
# ---------------------------------------------------------------------------

def fig_embudo(cifras: dict) -> Path:
    f = cifras["filas"]
    hechos = f["hecho_urgencia"] + f["hecho_medicion"]
    etapas = [
        ("Hechos en Parquet", "hecho_urgencia + hecho_medicion, Chile entero",
         hechos, NAVY),
        ("Panel diario del modelo", "tres ciudades × causas respiratorias",
         8_713, AZUL_M),
        ("analitico_ciudad_semana", "ciudad × semana epidemiológica",
         f["analitico_ciudad_semana"], SENAL),
    ]
    fig, ax = plt.subplots(figsize=(9.8, 3.6))
    ax.set_xlim(0, 12)
    ax.set_ylim(-0.9, len(etapas) + 0.85)
    ax.axis("off")
    ax.text(0, len(etapas) + 0.52, "El embudo: 70 millones de filas para "
            "responder con 1.350", fontsize=12.6, fontweight="bold", color=TINTA,
            ha="left")
    ax.text(0, len(etapas) + 0.10, "3,7 GB de zona cruda en siete formatos "
            "distintos entran por arriba; 209 MB de Parquet salen por abajo.",
            fontsize=8.4, color=TINTA2, ha="left")

    ancho_max, maximo = 7.4, max(e[2] for e in etapas)
    for i, (nombre, sub, n, c) in enumerate(etapas):
        y = len(etapas) - 1 - i
        # Raíz: en escala lineal, 1.350 sobre 70 millones no tendría ni un píxel.
        w = max(1.0, ancho_max * (n / maximo) ** 0.30)
        ax.add_patch(FancyBboxPatch(
            (0, y + 0.10), w, 0.62, boxstyle="round,pad=0,rounding_size=0.08",
            facecolor=c, edgecolor="none", zorder=2))
        # El rótulo va dentro solo si cabe; si no, al lado y en el color de barra.
        dentro = w > 0.14 * len(nombre) + 0.4
        ax.text(0.20 if dentro else w + 0.22, y + 0.41, nombre, va="center",
                ha="left", fontsize=8.4, fontweight="bold",
                color="white" if dentro else c, zorder=3)
        x_cifra = w + 0.22 if dentro else w + 0.30 + 0.135 * len(nombre)
        ax.text(x_cifra, y + 0.52, f"{n:,}".replace(",", ".") + " filas",
                va="center", ha="left", fontsize=8.8, color=c,
                fontweight="bold", zorder=3)
        ax.text(x_cifra, y + 0.22, sub, va="center", ha="left", fontsize=7.2,
                color=TINTA2, zorder=3)
        if i < len(etapas) - 1:
            reduccion = etapas[i + 1][2] / n
            ax.text(0.20, y - 0.10, f"↓  ×{1 / reduccion:,.0f}".replace(",", "."),
                    va="center", ha="left", fontsize=7.4, color=TINTA3,
                    zorder=3)
    ax.text(0, -0.62, "El ancho está en escala de raíz: en lineal las dos "
            "últimas barras no se verían. El recorte a tres ciudades ocurre al "
            "final de la cadena, no al principio.", fontsize=7.2, color=TINTA3,
            ha="left")
    return guardar(fig, "embudo.png")


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------

TABLAS = ["hecho_medicion", "hecho_urgencia", "dim_tiempo", "dim_estacion",
          "dim_ciudad", "dim_causa", "dim_establecimiento",
          "poblacion_comuna_anio", "poblacion_ciudad_anio", "isp_virus_dia",
          "isp_virus_semana", "analitico_ciudad_semana"]

FIGURAS = ["arquitectura.png", "estrella.png", "series.png", "urgencias.png",
           "mp25.png", "bosque.png", "rezagos.png", "embudo.png"]


def contar() -> dict:
    """Filas de cada tabla, leídas ahora y no escritas a mano."""
    faltan = [t for t in TABLAS if not (PROCESSED / t).exists()]
    if faltan:
        raise SystemExit(
            "Faltan tablas en data/processed: " + ", ".join(faltan) + "\n"
            "Bájalas con: python -m src.nube.sincronizar --bucket <bucket> "
            "--perfil <perfil> bajar --zona processed --aplicar")
    filas = {t: ds.dataset(PROCESSED / t, format="parquet",
                           partitioning="hive").count_rows() for t in TABLAS}
    total = sum(filas.values())
    return {"filas": filas, "filas_total": f"{total:,}".replace(",", ".")}


def construir(_args) -> int:
    if not MODELO_JSON.exists():
        raise SystemExit(
            f"No existe {MODELO_JSON.name}.\n"
            "Genéralo con: python -m src.sitio.exportar_modelo")
    cifras = contar()
    rutas = [fig_arquitectura(cifras), fig_estrella(cifras), fig_series(),
             fig_urgencias(), fig_mp25(), fig_bosque(), fig_rezagos(),
             fig_embudo(cifras)]
    print(f"Escritas {len(rutas)} figuras en {SALIDA.relative_to(RAIZ)}:")
    for r in rutas:
        print(f"  {r.name:<20} {r.stat().st_size / 1024:>7.0f} kB")
    return 0


def verificar(_args) -> int:
    faltan = [n for n in FIGURAS if not (SALIDA / n).exists()]
    for n in FIGURAS:
        ruta = SALIDA / n
        estado = "ok " if ruta.exists() else "FALTA"
        tam = f"{ruta.stat().st_size / 1024:.0f} kB" if ruta.exists() else "—"
        print(f"  {estado} {n:<20} {tam:>9}")
    if faltan:
        print("\nFaltan figuras. Constrúyelas con: "
              "python -m src.informe.figuras construir")
        return 1
    print(f"\nLas {len(FIGURAS)} figuras están.")
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
        handlers=[logging.FileHandler(LOGS / "figuras_informe.log",
                                      encoding="utf-8")])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
