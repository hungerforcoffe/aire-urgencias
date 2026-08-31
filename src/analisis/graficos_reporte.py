"""Graficos del informe de cierre de la etapa de reconocimiento.

Todos los valores estan codificados a mano a proposito: provienen de las
mediciones ya verificadas y registradas en docs/reconocimiento/hallazgos.md y en
los JSON de evidencia. Nada aqui se recalcula ni se estima.

Paleta: instancia de referencia del sistema de visualizacion, modo claro.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.rutas import RAIZ, asegurar  # noqa: E402

SALIDA = RAIZ / "docs" / "reconocimiento" / "figuras"

# --- paleta (modo claro) -------------------------------------------------
SUP = "#fcfcfb"        # superficie del grafico
TINTA = "#0b0b0b"      # tinta primaria
TINTA2 = "#52514e"     # tinta secundaria
MUTED = "#898781"      # ejes y etiquetas
REJILLA = "#e1e0d9"    # linea de rejilla
BASE = "#c3c2b7"       # linea base
S1 = "#2a78d6"         # categorico 1 - azul
S2 = "#eb6834"         # categorico 2 - naranja
S3 = "#1baf7a"         # categorico 3 - aqua

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
    "figure.facecolor": SUP,
    "axes.facecolor": SUP,
    "axes.edgecolor": BASE,
    "axes.labelcolor": TINTA2,
    "text.color": TINTA,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 200,
})

miles = FuncFormatter(lambda v, _: f"{int(v):,}".replace(",", "."))


def fig_correlacion_ventana():
    """OpenAQ contra medias moviles de SINCA. Fuente: hallazgos.md 1.5."""
    ventanas = ["1 h\n(dato horario)", "3 h", "6 h", "8 h", "12 h", "24 h"]
    corr = [0.596, 0.655, 0.734, 0.784, 0.872, 0.9998]

    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    y = range(len(ventanas))
    ax.barh(list(y), corr, height=0.5, color=S1, zorder=3)
    ax.set_yticks(list(y))
    ax.set_yticklabels(ventanas, fontsize=9, color=TINTA2)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.08)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.xaxis.grid(True, color=REJILLA, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)

    for i, v in enumerate(corr):
        # Sin redondear a 1,000: el valor es 0,9998 y la diferencia importa.
        etiqueta = f"{v:.4f}".replace(".", ",") if v > 0.99 else f"{v:.3f}".replace(".", ",")
        ax.text(v + 0.015, i, etiqueta, va="center", ha="left",
                fontsize=9, color=TINTA, fontweight="bold" if v > 0.99 else "normal")

    ax.set_xlabel("Correlación con el valor publicado por OpenAQ", fontsize=9, color=TINTA2)
    ax.set_title("OpenAQ no publica el dato horario de SINCA, sino su media móvil de 24 h",
                 fontsize=11, color=TINTA, loc="left", pad=12, fontweight="bold")
    fig.text(0.005, -0.02,
             "Estación Parque O'Higgins (SINCA RM/D14), julio 2023, 680 horas comparadas. "
             "Con ventana de 24 h el único residuo que queda\nes el del redondeo a entero.",
             fontsize=7.5, color=MUTED)
    fig.tight_layout()
    fig.savefig(SALIDA / "fig1_correlacion_ventana.png", bbox_inches="tight", facecolor=SUP)
    plt.close(fig)


def fig_urgencias_ciudad():
    """Serie anual por ciudad. Escalas propias: los niveles son incomparables."""
    anios = [2018, 2019, 2020, 2021, 2022, 2023, 2024]
    datos = [
        ("Santiago", [1461977, 1484576, 368052, 382439, 1173996, 1427298, 1440931]),
        ("Talcahuano", [75568, 70439, 13992, 13671, 54804, 59084, 52853]),
        ("Coyhaique", [21719, 20578, 4388, 4695, 17147, 21978, 23894]),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(9.6, 3.1))
    for ax, (ciudad, serie) in zip(axes, datos):
        # Franja de pandemia: sombreado recesivo, nunca una serie mas.
        ax.axvspan(2019.5, 2021.5, color=REJILLA, alpha=0.7, zorder=0, linewidth=0)
        ax.plot(anios, serie, color=S1, linewidth=2, zorder=3,
                marker="o", markersize=4, markerfacecolor=S1, markeredgecolor=SUP,
                markeredgewidth=1.2)
        ax.set_title(ciudad, fontsize=10, color=TINTA, loc="left", fontweight="bold", pad=8)
        ax.set_ylim(0, max(serie) * 1.22)
        ax.yaxis.set_major_formatter(miles)
        ax.yaxis.grid(True, color=REJILLA, linewidth=0.8, zorder=0)
        ax.set_axisbelow(True)
        ax.set_xticks([2018, 2020, 2022, 2024])
        ax.tick_params(labelsize=8, length=0)
        ax.set_xlim(2017.6, 2024.4)
        # Etiqueta directa solo en el minimo: el punto que cuenta la historia.
        j = serie.index(min(serie))
        ax.annotate(f"{min(serie):,}".replace(",", "."), xy=(anios[j], serie[j]),
                    xytext=(0, -14), textcoords="offset points",
                    fontsize=8, color=TINTA2, ha="center")

    axes[0].set_ylabel("Urgencias respiratorias", fontsize=9, color=TINTA2)
    fig.suptitle("La pandemia hunde la consulta de urgencia en las tres ciudades "
                 "(franja gris: 2020-2021)",
                 fontsize=11, color=TINTA, x=0.005, ha="left", y=1.04, fontweight="bold")
    fig.text(0.005, -0.06,
             "Solo causas de detalle (IdCausa 3, 4, 5, 6, 10, 11); se excluyen los totales "
             "agregados. Cada panel tiene su propia escala:\nlos niveles entre ciudades no son "
             "comparables entre sí. Fuente: DEIS, Atenciones de Urgencia 2018-2024.",
             fontsize=7.5, color=MUTED)
    fig.tight_layout()
    fig.savefig(SALIDA / "fig2_urgencias_ciudad.png", bbox_inches="tight", facecolor=SUP)
    plt.close(fig)


def fig_validacion_talcahuano():
    """Dias por marca de validacion en las 5 estaciones de Talcahuano."""
    est = ["RVIII/802\nConsultorio - San Vicente", "RVIII/837\nNueva Libertad",
           "RVIII/806\nInpesca", "RVIII/807\nIndura", "RVIII/803\nLibertad"]
    validados = [2427, 0, 0, 0, 0]
    preliminares = [52, 0, 0, 0, 0]
    no_validados = [31, 2522, 2519, 2504, 0]

    fig, ax = plt.subplots(figsize=(7.6, 3.3))
    y = list(range(len(est)))
    h = 0.5
    # separacion de 2px entre segmentos: se logra con un borde del color de la superficie
    borde = dict(edgecolor=SUP, linewidth=1.5)
    ax.barh(y, validados, height=h, color=S1, label="Validados", zorder=3, **borde)
    ax.barh(y, preliminares, height=h, left=validados, color=S2,
            label="Preliminares", zorder=3, **borde)
    izq = [a + b for a, b in zip(validados, preliminares)]
    ax.barh(y, no_validados, height=h, left=izq, color=S3,
            label="No validados", zorder=3, **borde)

    ax.set_yticks(y)
    ax.set_yticklabels(est, fontsize=8, color=TINTA2)
    ax.invert_yaxis()
    ax.xaxis.grid(True, color=REJILLA, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=0, labelsize=8)
    ax.set_xlabel("Días con dato, 2018-2024 (máximo posible: 2.556)", fontsize=9, color=TINTA2)
    ax.set_xlim(0, 2900)

    ax.text(2427 + 130, 0, "2.427 días validados", va="center", fontsize=8.5,
            color=TINTA, fontweight="bold")
    for i, v in [(1, 2522), (2, 2519), (3, 2504)]:
        ax.text(v + 60, i, f"{v:,}".replace(",", "."), va="center", fontsize=8, color=TINTA2)
    ax.text(60, 4, "sin serie publicada", va="center", fontsize=8, color=MUTED, style="italic")

    ax.legend(loc="lower right", frameon=False, fontsize=8, ncols=3,
              bbox_to_anchor=(1.0, -0.42), labelcolor=TINTA2)
    ax.set_title("De las cinco estaciones de MP2.5 de Talcahuano, solo una publica datos validados",
                 fontsize=11, color=TINTA, loc="left", pad=12, fontweight="bold")
    fig.text(0.005, -0.10,
             "Serie diaria de MP2.5 descargada de SINCA para cada estación. Las tres estaciones "
             "cuyo registro completo cae en\n«no validados» pertenecen a la red industrial.",
             fontsize=7.5, color=MUTED)
    fig.tight_layout()
    fig.savefig(SALIDA / "fig3_validacion_talcahuano.png", bbox_inches="tight", facecolor=SUP)
    plt.close(fig)


def main():
    asegurar(SALIDA)
    fig_correlacion_ventana()
    fig_urgencias_ciudad()
    fig_validacion_talcahuano()
    for p in sorted(SALIDA.glob("*.png")):
        print(f"  {p.name}  {p.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
