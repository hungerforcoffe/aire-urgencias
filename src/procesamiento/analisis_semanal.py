"""Extrae a CSV los resultados del análisis semanal, que llegaron en notebooks.

Por qué hace falta
------------------
El otro cuerpo de análisis del proyecto llegó como seis notebooks de Colab, sin
el handoff de CSV que sí acompañó al modelo diario (`data/raw/modelo/`). Los
números viven dentro de las salidas guardadas de las celdas, en HTML.

El proyecto no publica notebooks: `src/sitio/exportar_modelo.py` publica CSV que
alguien validó. Este módulo produce esos CSV, y lo hace **leyendo las salidas
guardadas**, no copiándolas a mano. Un número transcrito no se puede auditar; uno
extraído se vuelve a extraer y se compara.

Es el mismo movimiento que `deis_access.py` hace con los `.mdb`: pasar de un
formato que nadie más lee a uno que sí, sin tocar la zona cruda. Y escribe donde
aquel escribe, en `data/interim/`, por la misma razón (regla 3).

El informe .md del autor NO es la fuente
----------------------------------------
Junto a los notebooks llegaron dos informes en Markdown con los mismos
resultados tabulados. **No coinciden con los notebooks**, y las diferencias no
son de redondeo:

    Granger Santiago lag 3        informe p = 0,843   notebook p = 0,9778
    Importancia MP2.5 Coyhaique   informe 13,5 %      notebook 5,3 %
    Recall MP2.5 Santiago         informe 66,7 %      notebook 0,0 %
    Médicos de refuerzo Santiago  informe 115-140     notebook 183-247

El informe se escribió sobre una corrida anterior. Manda el notebook, que es la
corrida cuyo resultado quedó guardado y se puede volver a mirar. Las diferencias
quedan anotadas en `docs/calidad/analisis_semanal.md`; publicar las del informe
habría sido imposible de detectar después.

La fase 4 no se extrae
----------------------
`fase4_analisis_comparativo_ciudades.ipynb` tiene siete celdas de código y
**ninguna con salida guardada**. Su «Matriz Maestra de Indicadores» solo existe
en el informe .md, sin respaldo ejecutable. No se publica: sería exactamente el
vacío silencioso que prohíbe la regla 5.

Asociación, nunca causalidad
----------------------------
El material de origen titula «Pruebas de Causalidad» y llama al test de Granger
«test de causalidad». Es la nomenclatura del test, no una afirmación causal:
Granger mide **precedencia temporal predictiva** —si el pasado de una serie
ayuda a predecir otra— y nada más. Acá y en el sitio se nombra así.

Uso
---
    python -m src.procesamiento.analisis_semanal extraer
    python -m src.procesamiento.analisis_semanal verificar
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.rutas import INTERIM, LOGS, RAW, asegurar  # noqa: E402

log = logging.getLogger("analisis-semanal")

ORIGEN = RAW / "analisis_semanal"
DESTINO = INTERIM / "analisis_semanal"

CIUDADES = ["coyhaique", "santiago", "talcahuano"]
NOMBRE = {"Coyhaique": "coyhaique", "Santiago": "santiago", "Talcahuano": "talcahuano"}

# De qué celda de qué notebook sale cada tabla. La celda se identifica además
# por un fragmento de su código: si alguien reordena el notebook, el índice deja
# de apuntar a lo mismo y el ancla lo detecta en vez de extraer otra cosa.
FUENTES = {
    "adf": ("fase3-0_modelado_asociacion.ipynb", 4, "adfuller"),
    "granger": ("fase3-0_modelado_asociacion.ipynb", 8, "grangercausalitytests"),
    "multivariado": ("fase3-0_modelado_asociacion.ipynb", 10, "modelos_res"),
    "distancias": ("fase3-5_analisis_espacial.ipynb", 4, "haversine_km"),
    "higueras": ("fase3-5_analisis_espacial.ipynb", 16, "df_hig"),
    "mp25_t1": ("fase5-0_proyeccion_alertas_ml.ipynb", 5, "FEATS_MP25"),
    "ablacion": ("fase5-0_proyeccion_alertas_ml.ipynb", 8, "FEATS_A_INERCIA"),
    "importancias": ("fase5-0_proyeccion_alertas_ml.ipynb", 11, "Inercia Sanitaria"),
    "semaforo": ("fase5-0_proyeccion_alertas_ml.ipynb", 13, "umbrales_locales"),
    "dotacion": ("fase5-5_proyeccion_estrategica_2030.ipynb", 12, "dotaciones"),
}


class Rechazado(Exception):
    """El notebook no contiene lo que se esperaba."""


class _Tabla(HTMLParser):
    """Las tablas que escribe pandas son regulares; no hace falta lxml."""

    def __init__(self):
        super().__init__()
        self.filas: list[list[str]] = []
        self.fila: list[str] = []
        self.celda: list[str] = []
        self.dentro = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.fila = []
        elif tag in ("td", "th"):
            self.dentro, self.celda = True, []

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self.fila.append("".join(self.celda).strip())
            self.dentro = False
        elif tag == "tr" and self.fila:
            self.filas.append(self.fila)

    def handle_data(self, dato):
        if self.dentro:
            self.celda.append(dato)


def _celda(clave: str) -> dict:
    archivo, indice, ancla = FUENTES[clave]
    ruta = ORIGEN / archivo
    if not ruta.exists():
        raise Rechazado(f"falta {archivo} en {ORIGEN}")
    celdas = json.loads(ruta.read_text(encoding="utf-8"))["cells"]
    if indice >= len(celdas):
        raise Rechazado(f"{archivo}: no tiene celda {indice}")
    celda = celdas[indice]
    if ancla not in "".join(celda["source"]):
        raise Rechazado(f"{archivo} celda {indice}: no contiene '{ancla}'; "
                        f"el notebook cambio de orden")
    return celda


def tablas(clave: str) -> list[list[list[str]]]:
    """Las tablas HTML de una celda, como listas de filas de texto."""
    out = []
    for salida in _celda(clave).get("outputs", []):
        html = salida.get("data", {}).get("text/html")
        if html:
            p = _Tabla()
            p.feed("".join(html))
            if p.filas:
                out.append(p.filas)
    if not out:
        raise Rechazado(f"{clave}: la celda no tiene ninguna tabla guardada")
    return out


def texto(clave: str) -> str:
    return "".join("".join(o.get("text", []))
                   for o in _celda(clave).get("outputs", [])
                   if o.get("output_type") == "stream")


def _num(v: str) -> float | None:
    """Texto a número. `NaN` vuelve como None: en el pivote de la ablación marca
    una combinación que no se ajustó, y dejarlo como float('nan') haría que
    cualquier comparación posterior mintiera en silencio."""
    try:
        n = float(v.replace(",", ""))
    except ValueError:
        return None
    return None if n != n else n


# --- una función por tabla ---------------------------------------------------

def t_adf() -> pd.DataFrame:
    """Estacionariedad: la serie en nivel y su primera diferencia."""
    filas = tablas("adf")[0]
    out = []
    for f in filas[1:]:
        out.append({
            "ciudad_id": NOMBRE[f[1]],
            "p_mp25_nivel": _num(f[2]), "p_urgencias_nivel": _num(f[3]),
            "p_mp25_diff": _num(f[6]), "p_urgencias_diff": _num(f[7]),
        })
    return pd.DataFrame(out)


def t_granger() -> pd.DataFrame:
    """Precedencia temporal: 3 ciudades x 4 rezagos semanales."""
    filas = tablas("granger")[0]
    out = []
    for f in filas[1:]:
        out.append({
            "ciudad_id": NOMBRE[f[1]], "lag_semanas": int(f[2]),
            "f_stat": _num(f[3]), "p_valor": _num(f[4]),
        })
    return pd.DataFrame(out)


def t_multivariado() -> pd.DataFrame:
    """El coeficiente de MP2.5 crudo, con clima, y con clima + inercia AR(1)."""
    filas = tablas("multivariado")[0]
    out = []
    for f in filas[1:]:
        out.append({
            "ciudad_id": NOMBRE[f[1]],
            "coef_crudo": _num(f[2]), "p_crudo": _num(f[3]),
            "coef_clima": _num(f[4]), "p_clima": _num(f[5]),
            "coef_clima_ar1": _num(f[6]), "p_clima_ar1": _num(f[7]),
        })
    return pd.DataFrame(out)


def t_distancias() -> pd.DataFrame:
    """Distancia establecimiento-estación y reparto por zona de confianza."""
    resumen, zonas = tablas("distancias")[0], tablas("distancias")[1]
    por_ciudad = {}
    for f in resumen[2:]:
        por_ciudad[f[0]] = {
            "ciudad_id": f[0], "establecimientos": int(float(f[1])),
            "km_media": _num(f[2]), "km_min": _num(f[4]),
            "km_mediana": _num(f[6]), "km_max": _num(f[8]),
        }
    # La cabecera dice en qué orden vienen las tres zonas; no se supone.
    orden = [c.split("(")[0].strip().lower() for c in zonas[0][1:]]
    for f in zonas[2:]:
        for nombre, valor in zip(orden, f[1:], strict=True):
            por_ciudad[f[0]][f"n_{nombre}"] = int(float(valor))
    return pd.DataFrame([por_ciudad[c] for c in CIUDADES])


def t_higueras() -> pd.DataFrame:
    """El caso de Talcahuano: la estación lejana correlaciona más con viento oeste."""
    bruto = texto("higueras")
    out = []
    for linea in bruto.splitlines():
        if "Correlación Global Estrategia A" in linea:
            out.append({"escenario": "Global, monitor más cercano (Inpesca)",
                        "n_dias": None, "r": _num(linea.split("=")[-1])})
        elif "Correlación Global Estrategia C" in linea:
            out.append({"escenario": "Global, ponderado por viento",
                        "n_dias": None, "r": _num(linea.split("=")[-1])})
        elif "Viento Oeste" in linea:
            n = int(linea.split("n=")[1].split(")")[0])
            sv = _num(linea.split("San Vicente r =")[1].split("|")[0])
            inp = _num(linea.split("Inpesca r =")[1].split("(")[0])
            out.append({"escenario": "Viento oeste, San Vicente (2,26 km)",
                        "n_dias": n, "r": sv})
            out.append({"escenario": "Viento oeste, Inpesca (0,50 km)",
                        "n_dias": n, "r": inp})
    if len(out) != 4:
        raise Rechazado(f"higueras: se leyeron {len(out)} escenarios, se esperaban 4")
    return pd.DataFrame(out)


def t_mp25_t1() -> pd.DataFrame:
    """Proyección de MP2.5 de la semana siguiente, prueba ciega 2024."""
    filas = tablas("mp25_t1")[0]
    out = []
    for f in filas[1:]:
        out.append({
            "ciudad_id": NOMBRE[f[1]], "r2": _num(f[2]), "mae": _num(f[3]),
            "rmse": _num(f[4]), "semanas_reales": int(f[5]),
            "semanas_predichas": int(f[6]), "recall_alerta": _num(f[7]),
        })
    return pd.DataFrame(out)


def t_ablacion() -> pd.DataFrame:
    """Cuánto aporta cada familia de variables sobre la inercia epidemiológica.

    La celda guarda un pivote de doble índice (ciudad, configuración) y doble
    cabecera (métrica, modelo). Se aplana a formato **largo, con todos los
    modelos**, y no al mejor de cada configuración: el mejor cambia de familia
    entre A y C, y comparar un Ridge contra un Random Forest no mide el aporte
    del MP2.5 sino la diferencia entre dos algoritmos. La comparación que
    responde la pregunta es a modelo fijo, y se hace en el sitio.

    Las combinaciones sin ajustar vienen como `NaN` en el pivote y se descartan;
    quedan 10 filas por ciudad (la persistencia solo existe en el basal).
    """
    filas = tablas("ablacion")[0]
    # La cabecera arranca con una celda vacía del índice: se cuenta desde el
    # final, donde las ocho columnas de datos sí están alineadas con las filas.
    modelos = filas[1][-8:][:4]
    ciudad, out = None, []
    for f in filas[3:]:
        idx = f[:-8]                 # una celda si hereda la ciudad, dos si no
        vals = f[-8:]
        if len(idx) == 2:
            ciudad = idx[0]
        config = idx[-1]
        for i, modelo in enumerate(modelos):
            r2, wape = _num(vals[i]), _num(vals[i + 4])
            if r2 is None:
                continue
            out.append({
                "ciudad_id": NOMBRE[ciudad], "configuracion": config,
                "modelo": modelo, "r2": r2, "wape": wape,
            })
    if len(out) != 30:
        raise Rechazado(f"ablacion: {len(out)} filas ajustadas, se esperaban 30")
    return pd.DataFrame(out)


def t_importancias() -> pd.DataFrame:
    """Reparto de la importancia entre inercia sanitaria, clima y MP2.5."""
    filas = tablas("importancias")[0]
    out = []
    for f in filas[1:]:
        out.append({
            "ciudad_id": NOMBRE[f[0]], "inercia": _num(f[1]),
            "clima": _num(f[2]), "mp25": _num(f[3]),
        })
    return pd.DataFrame(out)


def t_semaforo() -> pd.DataFrame:
    """Umbrales por percentil local y desempeño de la detección en 2024."""
    umbrales, desempeno = tablas("semaforo")[0], tablas("semaforo")[1]
    por_ciudad = {}
    for f in umbrales[1:]:
        por_ciudad[f[0]] = {
            "ciudad_id": f[0], "p50": _num(f[1]), "p75": _num(f[2]),
            "p90": _num(f[3]), "consultas_p90": _num(f[6]),
        }
    for f in desempeno[1:]:
        por_ciudad[NOMBRE[f[1]]].update({
            "semanas_saturacion": int(f[3]), "semanas_detectadas": int(f[4]),
            "recall": _num(f[5]), "precision": _num(f[6]),
        })
    return pd.DataFrame([por_ciudad[c] for c in CIUDADES])


def t_dotacion() -> pd.DataFrame:
    """Dotación de refuerzo estimada, escenario tendencial y de invierno severo."""
    filas = tablas("dotacion")[0]
    out = []
    for f in filas[1:]:
        out.append({
            "ciudad_id": NOMBRE[f[1]], "anio": int(f[2]),
            "consultas_peak": int(f[3]), "medicos": int(f[4]),
            "kinesiologos": int(f[5]), "camas": int(f[6]),
            "consultas_peak_severo": int(f[7]), "medicos_severo": int(f[8]),
            "kinesiologos_severo": int(f[9]), "camas_severo": int(f[10]),
        })
    return pd.DataFrame(out)


TABLAS = {
    "01_estacionariedad.csv": t_adf,
    "02_granger.csv": t_granger,
    "03_multivariado.csv": t_multivariado,
    "04_distancias.csv": t_distancias,
    "05_talcahuano_viento.csv": t_higueras,
    "06_proyeccion_mp25.csv": t_mp25_t1,
    "07_ablacion.csv": t_ablacion,
    "08_importancias.csv": t_importancias,
    "09_semaforo.csv": t_semaforo,
    "10_dotacion.csv": t_dotacion,
}


def cmd_extraer(args) -> int:
    asegurar(DESTINO)
    for archivo, fn in TABLAS.items():
        d = fn()
        if d.empty:
            raise Rechazado(f"{archivo}: quedo vacio")
        d.to_csv(DESTINO / archivo, index=False, encoding="utf-8")
        log.info("%-28s %2d filas", archivo, len(d))
        print(f"  {archivo:<28} {len(d):>3} filas   {list(d.columns)[:4]}...")
    print(f"\n  escrito en {DESTINO}")
    return 0


def cmd_verificar(args) -> int:
    """Relee lo escrito y contrasta lo que tiene que ser cierto."""
    faltan = [a for a in TABLAS if not (DESTINO / a).exists()]
    if faltan:
        print(f"  faltan {faltan}; corre primero 'extraer'")
        return 1
    lee = {a: pd.read_csv(DESTINO / a) for a in TABLAS}
    fallos = []

    # Un p-valor vive en [0, 1] y un porcentaje en [0, 100]. Se separan por
    # nombre exacto y no por prefijo: `precision` empieza con «p» y no es un
    # p-valor, y confundirlos hace que la comprobación falle donde no debe.
    P_VALORES = {"p_mp25_nivel", "p_urgencias_nivel", "p_mp25_diff",
                 "p_urgencias_diff", "p_valor", "p_crudo", "p_clima", "p_clima_ar1"}
    PORCENTAJES = {"recall", "precision", "recall_alerta", "inercia", "clima", "mp25"}

    for archivo, d in lee.items():
        if "ciudad_id" in d.columns and not set(d.ciudad_id) <= set(CIUDADES):
            fallos.append(f"{archivo}: ciudades inesperadas {set(d.ciudad_id)}")
        for col, tope in [(c, 1) for c in P_VALORES] + [(c, 100) for c in PORCENTAJES]:
            if col not in d.columns:
                continue
            malos = d[(d[col] < 0) | (d[col] > tope)]
            if not malos.empty:
                fallos.append(f"{archivo}: {len(malos)} valores fuera de "
                              f"[0, {tope}] en {col}")

    imp = lee["08_importancias.csv"]
    suma = (imp.inercia + imp.clima + imp.mp25)
    if (suma - 100).abs().max() > 0.5:
        fallos.append(f"08_importancias: no suman 100 (max {suma.max():.1f})")

    r2 = lee["07_ablacion.csv"]
    if not r2.r2.between(-1, 1).all():
        fallos.append("07_ablacion: R2 fuera de [-1, 1]")

    if fallos:
        for f in fallos:
            print(f"  FALLO  {f}")
        return 1

    g = lee["02_granger.csv"]
    sig = g[g.p_valor < 0.05]
    print(f"  granger: {len(sig)} de {len(g)} pruebas bajo 0,05 — "
          f"{', '.join(f'{r.ciudad_id} lag {r.lag_semanas}' for r in sig.itertuples())}")
    # El aporte del MP2.5 se mide a modelo fijo: B contra C con el mismo
    # algoritmo. Entre familias distintas la diferencia mide otra cosa.
    ab = lee["07_ablacion.csv"]
    for c in CIUDADES:
        sub = ab[ab.ciudad_id == c]
        b = sub[sub.configuracion.str.startswith("B")].set_index("modelo").r2
        cc = sub[sub.configuracion.str.startswith("C")].set_index("modelo").r2
        delta = (cc - b).dropna()
        detalle = ", ".join(f"{m.split()[0]} {v:+.3f}" for m, v in delta.items())
        print(f"  ablacion {c:<11} B -> C al sumar MP2.5:  {detalle}")
    print(f"  importancia MP2.5: "
          f"{', '.join(f'{r.ciudad_id} {r.mp25:.1f} %' for r in imp.itertuples())}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("extraer").set_defaults(fn=cmd_extraer)
    sub.add_parser("verificar").set_defaults(fn=cmd_verificar)
    args = p.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "analisis_semanal.log", encoding="utf-8")])
    try:
        return args.fn(args)
    except Rechazado as e:
        log.error("no se extrae: %s", e)
        print(f"  ABORTADO - {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
