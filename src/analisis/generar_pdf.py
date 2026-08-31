"""Genera el PDF del informe a partir del HTML, embebiendo las figuras.

Las imagenes se incrustan como data URI para que el PDF no dependa de rutas
locales. La conversion usa el navegador del sistema en modo headless, que es lo
unico disponible en este entorno sin instalar binarios adicionales.
"""

from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.rutas import RAIZ  # noqa: E402

DOCS = RAIZ / "docs" / "reconocimiento"
FIGURAS = DOCS / "figuras"
HTML_ORIGEN = DOCS / "informe_etapa1.html"
HTML_ARMADO = FIGURAS / "_informe_armado.html"
PDF = DOCS / "Informe_Etapa1_Reconocimiento_de_Fuentes.pdf"

NAVEGADORES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]

FIGS = {
    "{{FIG1}}": "fig1_correlacion_ventana.png",
    "{{FIG2}}": "fig2_urgencias_ciudad.png",
    "{{FIG3}}": "fig3_validacion_talcahuano.png",
}


def incrustar() -> Path:
    html = HTML_ORIGEN.read_text(encoding="utf-8")
    for marca, nombre in FIGS.items():
        p = FIGURAS / nombre
        if not p.exists():
            raise FileNotFoundError(f"falta la figura {p}; correr src.analisis.graficos_reporte")
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        html = html.replace(marca, f"data:image/png;base64,{b64}")
    faltan = [m for m in FIGS if m in html]
    if faltan:
        raise RuntimeError(f"marcas sin sustituir: {faltan}")
    HTML_ARMADO.write_text(html, encoding="utf-8")
    return HTML_ARMADO


def navegador() -> Path:
    for p in NAVEGADORES:
        if p.exists():
            return p
    raise RuntimeError("no se encontro Edge ni Chrome para imprimir a PDF")


def main():
    armado = incrustar()
    print(f"HTML armado: {armado.stat().st_size / 1024:.0f} KB")

    exe = navegador()
    print(f"navegador  : {exe.name}")

    if PDF.exists():
        PDF.unlink()

    cmd = [
        str(exe),
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        f"--print-to-pdf={PDF}",
        armado.resolve().as_uri(),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if not PDF.exists():
        print("FALLO. salida del navegador:")
        print(r.stdout[-2000:])
        print(r.stderr[-2000:])
        return 1
    print(f"PDF        : {PDF}  ({PDF.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
