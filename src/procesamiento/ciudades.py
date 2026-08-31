"""Construye `dim_ciudad` y comprueba que aire y salud hablen de lo mismo.

Una ciudad no existe en los datos: existe como un conjunto de comunas del lado
de la salud y como un conjunto de estaciones del lado del aire. Si los dos
conjuntos no describen el mismo territorio, el estudio correlaciona el MP2.5 de
un sitio con las urgencias de otro, y nada en el resultado lo delata.

Este módulo fija esa correspondencia y la verifica: para cada estación de
`dim_estacion`, comprueba que su comuna esté entre las que definen su ciudad.

Uso
---
    python -m src.procesamiento.ciudades auditar
    python -m src.procesamiento.ciudades construir
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.ingesta.reconocer_deis import COMUNAS_ALTERNATIVAS  # noqa: E402
from src.procesamiento.geografia import (  # noqa: E402
    CIUDADES,
    COD_COMUNA,
    FUERA_DE_ALCANCE,
    habria_sido,
    normalizar_nombre,
)
from src.rutas import LOGS, PROCESSED, asegurar  # noqa: E402

log = logging.getLogger("ciudades")

# --- POBLACION: DECISION PENDIENTE DEL EQUIPO --------------------------------
# Sin denominador no se comparan 1,4 millones de urgencias en Santiago con 24 mil
# en Coyhaique: la ciudad grande gana siempre y el resultado no dice nada. Hace
# falta poblacion por comuna para agregarla al conjunto de cada ciudad.
#
# Ninguna fuente del proyecto la tiene todavia:
#   * CASEN es una encuesta y su representatividad comunal es limitada; el propio
#     docs/reconocimiento/casen.md lo advierte. Sirve para el % de lena regional,
#     no para poblacion comunal.
#   * El Censo 2017 del INE la tiene, y no esta descargado.
#
# Se deja en None a proposito. Una poblacion inventada seria peor que ninguna:
# las tasas por 100.000 saldrian plausibles y estarian mal.
POBLACION: dict[str, int | None] = {"santiago": None, "talcahuano": None, "coyhaique": None}
FUENTE_POBLACION = "pendiente: Censo 2017 (INE), sin descargar"


def auditar(estaciones: list[dict]) -> tuple[list[str], list[tuple[str, str]]]:
    """Comprueba que cada estación caiga en una comuna de su ciudad.

    Devuelve (problemas, fuera_de_alcance). Una estación con `ciudad_id` nulo
    **no es un problema**: es una exclusión decidida y registrada. Confundir las
    dos cosas haría que la auditoría no volviera a pasar nunca, y una auditoría
    que siempre suena en rojo deja de leerse.
    """
    problemas, fuera = [], []
    for e in estaciones:
        ciudad = e["ciudad_id"]
        clave = normalizar_nombre(e["comuna"])
        if ciudad is None:
            entrada = FUERA_DE_ALCANCE.get(clave)
            if entrada:
                fuera.append((e["nombre_sinca"], entrada["motivo"]))
            else:
                problemas.append(
                    f"{e['nombre_sinca']}: comuna {e['comuna']!r} no pertenece a ninguna "
                    f"ciudad y no está en FUERA_DE_ALCANCE. O se añade a las comunas de "
                    f"su ciudad, o se declara la exclusión con su motivo.")
            continue
        if ciudad not in CIUDADES:
            problemas.append(f"{e['nombre_sinca']}: ciudad_id {ciudad!r} desconocida")
            continue
        cod = COD_COMUNA.get(clave)
        if cod is None:
            problemas.append(f"{e['nombre_sinca']}: comuna {e['comuna']!r} "
                             f"sin código en COD_COMUNA")
            continue
        if cod not in CIUDADES[ciudad]["comunas"]:
            problemas.append(
                f"{e['nombre_sinca']}: está en {e['comuna']} ({cod}), que NO es una de "
                f"las {len(CIUDADES[ciudad]['comunas'])} comunas de {ciudad}")
    return problemas, fuera


def _estaciones() -> list[dict]:
    import pandas as pd
    ruta = PROCESSED / "dim_estacion" / "dim_estacion.parquet"
    if not ruta.exists():
        raise SystemExit(f"Falta {ruta}. Corre antes:\n"
                         f"  python -m src.procesamiento.estaciones construir --bucket <bucket>")
    df = pd.read_parquet(ruta)
    # pandas devuelve NaN donde el Parquet trae null, y `NaN is None` es False:
    # sin esto una estación fuera de alcance se leería como «ciudad desconocida».
    # Hace falta pasar por `object` primero; sobre el dtype original, `where`
    # vuelve a meter NaN.
    df = df.astype(object).where(pd.notna(df), None)
    return df[df["tiene_datos"].astype(bool)].to_dict("records")


def cmd_auditar(args) -> int:
    est = _estaciones()
    print(f"  estaciones con datos: {len(est)}\n")
    for cid, c in CIUDADES.items():
        suyas = [e for e in est if e["ciudad_id"] == cid]
        print(f"  {c['nombre']:<12} {len(c['comunas']):>3} comuna(s) · "
              f"{len(suyas)} estación(es) · leña {c['pct_lena_casen']}%")

    problemas, fuera = auditar(est)
    if fuera:
        print(f"\n  fuera de alcance por decisión del equipo: {len(fuera)}")
        for nombre, motivo in fuera:
            print(f"    · {nombre}")
            print(f"        {motivo}")
    print(f"\n  cruce comuna-ciudad: {len(problemas)} problema(s)")
    for p in problemas:
        print(f"    · {p}")

    if COMUNAS_ALTERNATIVAS:
        print("\n  definiciones alternativas contempladas en reconocer_deis.py:")
        for k, v in COMUNAS_ALTERNATIVAS.items():
            print(f"    · {k}: {sorted(v)}")

    faltan = [c for c, p in POBLACION.items() if p is None]
    if faltan:
        print(f"\n  SIN POBLACIÓN: {', '.join(faltan)}")
        print(f"    fuente prevista: {FUENTE_POBLACION}")
        print("    Sin denominador no hay tasas por 100.000 y las ciudades no se comparan.")
    return 1 if problemas else 0


def cmd_construir(args) -> int:
    import pandas as pd

    est = _estaciones()
    problemas, fuera = auditar(est)
    if problemas and not args.forzar:
        print("  No se construye con el cruce comuna-ciudad en rojo:")
        for p in problemas:
            print(f"    · {p}")
        print("\n  Si es una decisión y no un error, decláralo en FUERA_DE_ALCANCE")
        print("  (geografia.py) con su motivo, o añade la comuna a su ciudad.")
        print("  Para escribir igual, usa --forzar: queda en la columna 'auditoria_ok'.")
        return 1

    filas = []
    for cid, c in CIUDADES.items():
        suyas = [e for e in est if e["ciudad_id"] == cid]
        filas.append({
            "ciudad_id": cid,
            "nombre": c["nombre"],
            "region_codigo": c["region_codigo"],
            "region": c["region"],
            "n_comunas": len(c["comunas"]),
            "comunas": ",".join(str(x) for x in sorted(c["comunas"])),
            "n_estaciones": len(suyas),
            "poblacion": POBLACION[cid],
            "fuente_poblacion": FUENTE_POBLACION if POBLACION[cid] is None else "",
            "pct_lena_casen": c["pct_lena_casen"],
            "auditoria_ok": not problemas,
            # Estaciones que un criterio de cercanía habría metido aquí y que el
            # equipo decidió dejar fuera. Que la cifra viaje en la dimensión evita
            # que la decisión se olvide al leer la tabla dentro de seis meses.
            "n_estaciones_excluidas": sum(
                1 for e in est if habria_sido(e["comuna"]) == cid),
        })

    df = pd.DataFrame(filas)
    # Sin esto, una columna entera de nulos se escribe en Parquet con tipo
    # `null`, que Athena no sabe declarar. `Int64` (con mayúscula) es el entero
    # nulable de pandas: deja la columna en int64 y los valores en null, que es
    # lo que hay que decir — «no sabemos la población», no «no hay columna».
    df["poblacion"] = df["poblacion"].astype("Int64")
    destino = PROCESSED / "dim_ciudad"
    asegurar(destino)
    salida = destino / "dim_ciudad.parquet"
    df.to_parquet(salida, index=False)
    print(df[["ciudad_id", "nombre", "n_comunas", "n_estaciones",
              "poblacion", "pct_lena_casen", "auditoria_ok"]].to_string(index=False))
    print(f"\n  escrito en: {salida.relative_to(PROCESSED.parent.parent)}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auditar").set_defaults(fn=cmd_auditar, forzar=False)
    c = sub.add_parser("construir")
    c.add_argument("--forzar", action="store_true",
                   help="escribe aunque el cruce comuna-ciudad tenga problemas")
    c.set_defaults(fn=cmd_construir)

    args = p.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "ciudades.log", encoding="utf-8")])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
