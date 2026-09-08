"""Publica en el sitio los resultados del análisis semanal.

Qué es este análisis y por qué va aparte
----------------------------------------
Es el segundo cuerpo de análisis del proyecto, hecho por otra persona del equipo
y con otro diseño: la unidad es **ciudad-semana**, no ciudad-día, y las
preguntas son de series de tiempo —estacionariedad, correlación cruzada,
precedencia temporal— más un bloque espacial y uno de proyección.

Vive en su propio JSON y no dentro de `modelo.json` porque **no comparte
unidad**: allá todo es un RR por +10 µg/m³ con su intervalo, y acá hay
p-valores, coeficientes, R² y kilómetros. Mezclarlos en un mismo bloque
invitaría a compararlos como si fueran la misma medida.

De dónde salen los números
--------------------------
De `data/interim/analisis_semanal/`, que escribe
`src/procesamiento/analisis_semanal.py` leyendo las salidas guardadas de los
notebooks. Ese módulo documenta por qué no se usa el informe .md del autor: sus
tablas corresponden a una corrida anterior y difieren de los notebooks.

Acá no se ajusta ni se recalcula nada, igual que en `exportar_modelo.py`.

Los dos análisis no se contradicen
----------------------------------
El modelo diario encuentra asociación en Santiago; este, a escala semanal
diferenciada, no encuentra precedencia de Granger en Santiago. Son preguntas
distintas a resoluciones distintas, y juntas sostienen lo que
`docs/calidad/resultados_modelo.md` ya defendía: la resolución temporal decide
el resultado. El sitio lo dice explícitamente en vez de dejar que el lector
descubra dos números que parecen pelearse.

Precedencia, no causalidad
--------------------------
El test de Granger se llama «de causalidad» por convención estadística. Mide si
el pasado de una serie mejora la predicción de otra: precedencia temporal
predictiva. Ni acá ni en el sitio se nombra de otra forma (regla 1).

Uso
---
    python -m src.sitio.exportar_semanal
    python -m src.sitio.exportar_semanal --verificar
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.rutas import INTERIM, LOGS, RAIZ, asegurar  # noqa: E402

log = logging.getLogger("exportar-semanal")

ORIGEN = INTERIM / "analisis_semanal"
SALIDA = RAIZ / "sitio" / "assets" / "datos"
NOMBRE = "semanal_nt.json"

CIUDADES = {"coyhaique", "santiago", "talcahuano"}

# clave en el JSON -> (archivo, filas esperadas)
PIEZAS = {
    "estacionariedad": ("01_estacionariedad.csv", 3),
    "granger": ("02_granger.csv", 12),
    "multivariado": ("03_multivariado.csv", 3),
    "distancias": ("04_distancias.csv", 3),
    "talcahuano_viento": ("05_talcahuano_viento.csv", 4),
    "proyeccion_mp25": ("06_proyeccion_mp25.csv", 3),
    "ablacion": ("07_ablacion.csv", 30),
    "importancias": ("08_importancias.csv", 3),
    "semaforo": ("09_semaforo.csv", 3),
    "dotacion": ("10_dotacion.csv", 9),
}

# Nombres de columna cuyo rango se conoce y se comprueba. Se listan uno a uno y
# no por prefijo: `precision` empieza con «p» y no es un p-valor.
P_VALORES = {"p_mp25_nivel", "p_urgencias_nivel", "p_mp25_diff", "p_urgencias_diff",
             "p_valor", "p_crudo", "p_clima", "p_clima_ar1"}
PORCENTAJES = {"recall", "precision", "recall_alerta", "inercia", "clima", "mp25"}
CORRELACIONES = {"r"}


class Rechazado(Exception):
    """Lo que llegó no es publicable."""


def leer(archivo: str) -> pd.DataFrame:
    ruta = ORIGEN / archivo
    if not ruta.exists():
        raise Rechazado(f"falta {ruta.name} en {ORIGEN}; corre primero "
                        f"'python -m src.procesamiento.analisis_semanal extraer'")
    d = pd.read_csv(ruta)
    if d.empty:
        raise Rechazado(f"{archivo}: llego vacio")
    return d


def validar(d: pd.DataFrame, archivo: str, filas: int) -> None:
    """Regla 5: un CSV que se lee no es un CSV que sirva."""
    if len(d) != filas:
        raise Rechazado(f"{archivo}: {len(d)} filas, se esperaban {filas}")

    if "ciudad_id" in d.columns and not set(d.ciudad_id) <= CIUDADES:
        raise Rechazado(f"{archivo}: ciudades {sorted(set(d.ciudad_id))}, "
                        f"fuera de {sorted(CIUDADES)}")

    for col, lo, hi in ([(c, 0, 1) for c in P_VALORES]
                        + [(c, 0, 100) for c in PORCENTAJES]
                        + [(c, -1, 1) for c in CORRELACIONES]):
        if col in d.columns:
            malos = d[(d[col] < lo) | (d[col] > hi)]
            if not malos.empty:
                raise Rechazado(f"{archivo}: {len(malos)} valores fuera de "
                                f"[{lo}, {hi}] en {col}")

    # Un R² por encima de 1 no es un modelo bueno: es una métrica mal calculada.
    if "r2" in d.columns and not d.r2.between(-1, 1).all():
        raise Rechazado(f"{archivo}: R2 fuera de [-1, 1]")

    # El reparto de importancia es una partición: si no suma 100, falta un
    # bloque de variables y el gráfico de barras mentiría por omisión.
    if {"inercia", "clima", "mp25"} <= set(d.columns):
        desvio = (d.inercia + d.clima + d.mp25 - 100).abs().max()
        if desvio > 0.5:
            raise Rechazado(f"{archivo}: las importancias no suman 100 "
                            f"(desvio {desvio:.2f} pp)")

    # Detectar menos episodios de los que hubo se puede; más, no.
    if {"semanas_saturacion", "semanas_detectadas"} <= set(d.columns):
        if (d.semanas_detectadas > d.semanas_saturacion).any():
            raise Rechazado(f"{archivo}: mas semanas detectadas que reales")


def limpiar(d: pd.DataFrame) -> list[dict]:
    """A lista de dicts, con NaN como None.

    Cuatro decimales: acá el número más fino es un p-valor de 0,0090 y un
    coeficiente de correlación de 0,2752. No hay RR que pida cinco.
    """
    d = d.copy()
    for c in d.columns:
        if d[c].dtype.kind == "f":
            d[c] = d[c].round(4)
    return json.loads(d.to_json(orient="records"))


def exportar(destino: Path) -> dict:
    asegurar(destino)
    datos: dict = {
        "generado": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "origen": "notebooks del analisis semanal del equipo, fases 2 a 5.5",
        "unidad": "ciudad-semana epidemiologica",
        "diseno": "series de tiempo: estacionariedad ADF, correlacion cruzada, "
                  "precedencia de Granger, analisis espacial y proyeccion",
        "nota_granger": "Granger mide precedencia temporal predictiva, no causalidad",
        "fase4": "la sintesis cross-city no se publica: sus celdas no tienen "
                 "salida guardada en el notebook",
    }
    for clave, (archivo, filas) in PIEZAS.items():
        d = leer(archivo)
        validar(d, archivo, filas)
        datos[clave] = limpiar(d)
        log.info("  %-28s %3d filas", archivo, len(d))

    ruta = destino / NOMBRE
    ruta.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    tam = ruta.stat().st_size
    filas_tot = sum(len(v) for v in datos.values() if isinstance(v, list))
    print(f"  {NOMBRE:<18} {tam / 1024:6.1f} kB   {filas_tot} filas")
    return datos


def cmd_verificar(destino: Path) -> int:
    ruta = destino / NOMBRE
    if not ruta.exists():
        print(f"  falta {ruta}; corre primero el exportador")
        return 1
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    faltan = [c for c in PIEZAS if c not in datos]
    if faltan:
        print(f"  faltan bloques en {NOMBRE}: {faltan}")
        return 1

    sig = [f for f in datos["granger"] if f["p_valor"] < 0.05]
    donde = ", ".join("{} lag {}".format(f["ciudad_id"], f["lag_semanas"]) for f in sig)
    print(f"  precedencia: {len(sig)} de {len(datos['granger'])} pruebas bajo 0,05"
          + (f" — {donde}" if sig else ""))

    # El punto del bloque multivariado: el coeficiente crudo es grande y
    # significativo, y al controlar clima e inercia deja de serlo.
    for f in datos["multivariado"]:
        print(f"  {f['ciudad_id']:<11} coef crudo {f['coef_crudo']:>7.3f} "
              f"(p {f['p_crudo']:.4f})  ->  con clima+AR(1) {f['coef_clima_ar1']:>7.3f} "
              f"(p {f['p_clima_ar1']:.4f})")

    imp = {f["ciudad_id"]: f["mp25"] for f in datos["importancias"]}
    print(f"  importancia del MP2.5: "
          f"{', '.join(f'{c} {imp[c]:.1f} %' for c in sorted(imp, key=imp.get))}")
    print(f"  bloques: {len(datos['ablacion'])} filas de ablacion, "
          f"{len(datos['distancias'])} de distancias, "
          f"{len(datos['dotacion'])} de dotacion")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--salida", type=Path, default=SALIDA)
    p.add_argument("--verificar", action="store_true")
    args = p.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "exportar_semanal.log", encoding="utf-8")])
    try:
        if args.verificar:
            return cmd_verificar(args.salida)
        exportar(args.salida)
        return cmd_verificar(args.salida)
    except Rechazado as e:
        log.error("no se publica: %s", e)
        print(f"  ABORTADO - {e}\n  El {NOMBRE} anterior queda intacto.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
