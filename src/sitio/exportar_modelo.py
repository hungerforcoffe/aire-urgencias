"""Publica en el sitio los resultados del modelo de asociación.

Por qué es un exportador aparte
-------------------------------
`exportar.py` consulta Athena y agrega. Este no: los resultados inferenciales
—los RR, sus intervalos, los rezagos, las sensibilidades— salen del cuaderno de
análisis del equipo y llegan como CSV. Acá no se ajusta ningún modelo ni se
recalcula ningún intervalo; se valida lo que llegó y se publica.

Esa separación es deliberada. GitHub Pages sirve archivos y nada más, así que el
sitio no puede ajustar una Poisson condicional aunque quisiera. Que los
resultados vengan precomputados no es una limitación: es lo que hace que el
sitio pueda mostrarlos sin backend.

Qué se publica
--------------
Los CSV se vuelven un JSON de ~20 kB. Son estimaciones agregadas de ciudad, no
registros: la misma frontera que ya respeta `exportar.py`.

Dos entregas, un solo JSON
--------------------------
El material llegó en dos tandas de la misma persona, y cada una vive en su
carpeta de la zona cruda porque la regla 3 no deja reescribir lo que llegó:

    data/raw/modelo/                    entrega 1 — el resultado principal
    data/raw/modelo_viz/visualizaciones/ entrega 2 — las extensiones anunciadas

La segunda es la continuación que la primera dejó escrita en su
`00_README_HANDOFF.md` («qué todavía puede cambiar o agregarse»): el análisis
por diagnóstico y la comparación territorial dentro de la Región Metropolitana.
**Los valores compartidos entre ambas coinciden dígito a dígito** —se comprobó
en ciudades, edad y la curva de rezagos—, así que la segunda amplía y no
corrige. Se publican juntas porque son el mismo diseño, la misma persona y la
misma unidad; partirlas en dos JSON solo trasladaría al navegador un accidente
de calendario.

Dos archivos de la entrega 2 no se publican, y no por olvido:

* `02_rezagos.csv` es `05_resultados_lags.csv` más una fila con el acumulado
  0–7, que ya viaja en `02_resultado_principal.csv`. Nada nuevo.
* `03_ciudades.csv` y `05_edad.csv` son idénticos a los de la entrega 1.
* `09_series_temporales.csv` son 9.468 días; el sitio ya publica la serie
  semanal en `semanal.json` y la dibuja `analisis.js`.

Sobre `escala`
--------------
Es el factor de sobredispersión cuasi-Poisson del ajuste, y **los intervalos ya
vienen escalados por él**. Se comprobó contra los propios números: al dividir el
error estándar por su raíz, los cinco grupos etarios —que comparten exposición y
estratos— colapsan a un mismo valor con 6 % de dispersión, contra 140 % sin la
corrección. Se publica la columna porque es lo que respalda el ancho de los IC.

Lo que este módulo NO hace
--------------------------
No interpreta. En particular, los controles negativos de `10_...` **no dieron
nulos** y salen tal cual: son el diagnóstico de que parte de la asociación es
estructura temporal compartida, y esconderlos sería exactamente el fallo
silencioso que prohíbe la regla 5.

Uso
---
    python -m src.sitio.exportar_modelo
    python -m src.sitio.exportar_modelo --verificar
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

from src.rutas import LOGS, RAIZ, RAW, asegurar  # noqa: E402

log = logging.getLogger("exportar-modelo")

# Dos entregas de la misma persona, en carpetas distintas de la zona cruda. No
# se fusionan en una: cada una es lo que llegó, y la regla 3 dice que eso no se
# reescribe. El exportador las lee por separado y publica un solo JSON.
ORIGEN = RAW / "modelo"                               # entrega 1
ORIGEN_VIS = RAW / "modelo_viz" / "visualizaciones"   # entrega 2
SALIDA = RAIZ / "sitio" / "assets" / "datos"
NOMBRE = "modelo.json"

CIUDADES = {"coyhaique", "santiago", "talcahuano"}
ZONAS_RM = 6
PERIODOS_RM = 2

# Un RR por +10 µg/m³ vive en centésimas. Cualquier cosa fuera de esta ventana
# no es un hallazgo sorprendente: es que alguien cambió la unidad de la
# exposición y el número dejó de significar lo que dice la etiqueta.
RR_MIN, RR_MAX = 0.90, 1.20

# clave en el JSON -> (carpeta, archivo, filas esperadas)
#
# La clave manda porque es lo que consume el sitio; el archivo y su carpeta son
# de dónde salió. Agregar un bloque a la página es agregar una línea acá.
PIEZAS = {
    "principal": (ORIGEN, "02_resultado_principal.csv", 2),
    "ciudad": (ORIGEN, "03_resultados_ciudad.csv", 3),
    "edad": (ORIGEN, "04_resultados_edad.csv", 5),
    "lags": (ORIGEN, "05_resultados_lags.csv", 8),
    "lags_ciudad": (ORIGEN, "06_resultados_lags_ciudad.csv", 24),
    "lags_acum_ciudad": (ORIGEN, "07_resultados_lags_acumulados_ciudad.csv", 3),
    "placebo": (ORIGEN, "09_placebo_temporal.csv", 7),
    "controles_negativos": (ORIGEN, "10_controles_negativos.csv", 2),
    "diccionario": (ORIGEN, "01_diccionario_variables.csv", 12),
    # Entrega 2. `sensibilidades` viene de acá y no del `08_` de la entrega 1:
    # son las mismas seis filas más dos de ponderación territorial, con una
    # columna `etiqueta` abreviada para que quepa en el eje del gráfico.
    "ajuste": (ORIGEN_VIS, "01_modelos_ajuste.csv", 4),
    "zonas_rm": (ORIGEN_VIS, "04_zonas_rm.csv", ZONAS_RM * PERIODOS_RM),
    "diagnosticos": (ORIGEN_VIS, "06_diagnosticos.csv", 6),
    "sensibilidades": (ORIGEN_VIS, "07_sensibilidades.csv", 8),
    "cobertura_rm": (ORIGEN_VIS, "08_cobertura_rm.csv", 54),
}


class Rechazado(Exception):
    """Lo que llegó no es publicable."""


def leer(origen: Path, archivo: str) -> pd.DataFrame:
    ruta = origen / archivo
    if not ruta.exists():
        raise Rechazado(f"falta {ruta.name} en {origen}")
    d = pd.read_csv(ruta)
    if d.empty:
        raise Rechazado(f"{archivo}: llego vacio")
    return d


def validar(d: pd.DataFrame, archivo: str, filas: int) -> None:
    """Regla 5: un CSV que se lee no es un CSV que sirva."""
    if len(d) != filas:
        raise Rechazado(f"{archivo}: {len(d)} filas, se esperaban {filas}")

    if "rr10" in d.columns:
        fuera = d[(d.rr10 < RR_MIN) | (d.rr10 > RR_MAX)]
        if not fuera.empty:
            raise Rechazado(f"{archivo}: {len(fuera)} RR fuera de [{RR_MIN}, {RR_MAX}]; "
                            f"revisar la unidad de la exposicion")
        # Un intervalo que no contiene a su propia estimación es un error de
        # armado del CSV, y a ojo no se nota: los tres números se ven normales.
        malos = d[(d.ic_inf > d.rr10) | (d.ic_sup < d.rr10)]
        if not malos.empty:
            raise Rechazado(f"{archivo}: {len(malos)} filas donde el IC no contiene al RR")

    if "convergio" in d.columns and not d.convergio.all():
        cuantos = int((~d.convergio).sum())
        raise Rechazado(f"{archivo}: {cuantos} modelo(s) no convergieron")

    if "ciudad" in d.columns and set(d.ciudad) != CIUDADES:
        raise Rechazado(f"{archivo}: ciudades {sorted(set(d.ciudad))}, "
                        f"se esperaban {sorted(CIUDADES)}")

    # La cobertura es lo que justifica que la ventana principal termine en 2024:
    # la zona Sur cae al 16 % en 2025. Si el porcentaje no cuadra con su propio
    # numerador, el argumento de la página se apoya en un número inventado.
    if "cobertura_pct" in d.columns:
        fuera = d[(d.cobertura_pct < 0) | (d.cobertura_pct > 100)]
        if not fuera.empty:
            raise Rechazado(f"{archivo}: {len(fuera)} coberturas fuera de [0, 100]")
        if (d.dias_con_mp25 > d.dias).any():
            raise Rechazado(f"{archivo}: dias_con_mp25 mayor que dias")
        desvio = (d.dias_con_mp25 / d.dias * 100 - d.cobertura_pct).abs().max()
        if desvio > 0.01:
            raise Rechazado(f"{archivo}: cobertura_pct no cuadra con "
                            f"dias_con_mp25/dias (desvio {desvio:.3f} pp)")

    # Las dos ventanas de la comparación territorial tienen que traer las mismas
    # zonas: un selector que cambie de período y además de zonas no compara nada.
    if "periodo" in d.columns and "zona_id" in d.columns:
        por_periodo = d.groupby("periodo").zona_id.apply(frozenset)
        if len(set(por_periodo)) != 1:
            raise Rechazado(f"{archivo}: las ventanas no traen las mismas zonas")
        if len(por_periodo.iloc[0]) != ZONAS_RM:
            raise Rechazado(f"{archivo}: {len(por_periodo.iloc[0])} zonas, "
                            f"se esperaban {ZONAS_RM}")


def limpiar(d: pd.DataFrame) -> list[dict]:
    """A lista de dicts, con los RR a cinco decimales y NaN como None.

    Cinco decimales no es coquetería: la asociación contemporánea es 1,00808 y
    a cuatro decimales el límite inferior del intervalo (1,00472) se acerca
    demasiado al punto. Lo que se muestra en pantalla se redondea allá.
    """
    d = d.copy()
    for c in d.columns:
        if d[c].dtype.kind == "f":
            d[c] = d[c].round(5 if c.startswith(("rr", "ic_")) else 3)
    return json.loads(d.to_json(orient="records"))


def exportar(destino: Path) -> dict:
    asegurar(destino)
    datos: dict = {
        "generado": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "origen": "cuaderno de analisis del equipo, entregas 1 y 2 (2026-09-06)",
        "diseno": "case-crossover estratificado por tiempo, Poisson condicional "
                  "sobre conteos diarios",
        "ajustes": "temperatura por spline natural, humedad, actividad viral "
                   "nacional del ISP",
        "exposicion": "MP2.5 diario; RR por cada +10 ug/m3",
        "escala": "los intervalos vienen escalados por la sobredispersion "
                  "cuasi-Poisson de cada ajuste (columna escala)",
    }
    for clave, (origen, archivo, filas) in PIEZAS.items():
        d = leer(origen, archivo)
        validar(d, archivo, filas)
        datos[clave] = limpiar(d)
        log.info("  %-38s %3d filas  (%s)", archivo, len(d), origen.name)

    ruta = destino / NOMBRE
    ruta.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")),
                    encoding="utf-8")
    tam = ruta.stat().st_size
    filas_tot = sum(len(v) for v in datos.values() if isinstance(v, list))
    print(f"  {NOMBRE:<14} {tam / 1024:6.1f} kB   {filas_tot} filas")
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

    pr = {f["analisis"]: f for f in datos["principal"]}
    con = pr["Asociación contemporánea"]
    acu = pr["Asociación acumulada"]
    print(f"  contemporanea   RR {con['rr10']:.4f}  "
          f"({con['ic_inf']:.4f} - {con['ic_sup']:.4f})")
    print(f"  acumulada 0-7   RR {acu['rr10']:.4f}  "
          f"({acu['ic_inf']:.4f} - {acu['ic_sup']:.4f})")

    # El control negativo es la prueba del metodo, no del aire: si mide MAS que
    # el desenlace de interes, el sitio no puede presentar el RR como limpio.
    peor = max(datos["controles_negativos"], key=lambda f: f["rr10"])
    aviso = "POR ENCIMA del respiratorio" if peor["rr10"] > con["rr10"] else "por debajo"
    print(f"  control negativo mayor: {peor['etiqueta']} RR {peor['rr10']:.4f} ({aviso})")

    # La escalera de ajuste es el argumento central de la pagina: si el RR no
    # bajara al sumar controles, no habria nada que contar sobre confusion.
    esc = datos["ajuste"]
    print(f"  escalera de ajuste: {esc[0]['especificacion']} RR {esc[0]['rr10']:.4f}"
          f"  ->  {esc[-1]['especificacion']} RR {esc[-1]['rr10']:.4f}")

    peor_cob = min(datos["cobertura_rm"], key=lambda f: f["cobertura_pct"])
    print(f"  cobertura RM minima: zona {peor_cob['zona_id']} en {peor_cob['anio']}, "
          f"{peor_cob['cobertura_pct']:.1f} %")
    print(f"  bloques: {len(datos['ciudad'])} ciudades, {len(datos['edad'])} grupos de "
          f"edad, {len(datos['lags'])} rezagos, "
          f"{len(datos['sensibilidades'])} sensibilidades, "
          f"{len(datos['diagnosticos'])} diagnosticos, "
          f"{len(datos['zonas_rm'])} filas de zonas RM")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--salida", type=Path, default=SALIDA)
    p.add_argument("--verificar", action="store_true")
    args = p.parse_args(argv)
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "exportar_modelo.log", encoding="utf-8")])
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
