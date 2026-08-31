"""Construye la población por comuna y año, y la agrega a las tres ciudades.

Por qué por año y no un solo número
-----------------------------------
La ventana del estudio va de 2018 a 2026 y la población cambió dentro de ella.
Con una cifra fija, ese crecimiento se confunde con más urgencias: una ciudad
que crece un 8&nbsp;% muestra un 8&nbsp;% más de consultas sin que haya cambiado
nada del riesgo. Las proyecciones del INE dan un valor por comuna y por año, y
son el mismo denominador que usa MINSAL para publicar tasas.

Por qué en las mismas bandas etarias que el DEIS
------------------------------------------------
El archivo del INE trae población por **edad simple**, año a año. Eso permite
recomponer exactamente las cinco franjas que publica el DEIS —menores de 1, 1 a
4, 5 a 14, 15 a 64, 65 y más— en vez de conformarse con el total.

La consecuencia es que la tasa se puede calcular **por franja**, que es donde el
efecto respiratorio se ve: los menores de 1 año y los mayores de 65 son los
grupos sensibles, y diluirlos en el total los esconde.

Escala nacional, recorte al final
---------------------------------
Se construyen las 346 comunas del país (`poblacion_comuna_anio`) y de ahí se
derivan las tres ciudades (`poblacion_ciudad_anio`). Es la regla 2: el filtro
ocurre en el último paso, no en la lectura.

Uso
---
    python -m src.procesamiento.poblacion construir
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.procesamiento.geografia import CIUDADES  # noqa: E402
from src.procesamiento.tiempo import FIN, INICIO  # noqa: E402
from src.rutas import LOGS, PROCESSED, RAW, asegurar  # noqa: E402

log = logging.getLogger("poblacion")

ORIGEN = RAW / "ine" / "ine_proyecciones_comunas_2002-2035_base2017.xlsx"
HOJA = "Est. y Proy. de Pob. Comunal"

# Las mismas franjas que publica el DEIS, para que la tasa sea una division
# directa entre dos columnas que ya se llaman igual.
BANDAS = (
    ("menores_1",    lambda e: e == 0),
    ("de_1_a_4",     lambda e: 1 <= e <= 4),
    ("de_5_a_14",    lambda e: 5 <= e <= 14),
    ("de_15_a_64",   lambda e: 15 <= e <= 64),
    ("de_65_y_mas",  lambda e: e >= 65),
)

COL_COMUNA, COL_NOMBRE, COL_EDAD = 4, 5, 7


def _edad(valor) -> int | None:
    """La columna de edad puede traer «100 y más» o similares."""
    if valor is None:
        return None
    if isinstance(valor, int):
        return valor
    t = str(valor).strip()
    if t.isdigit():
        return int(t)
    digitos = "".join(c for c in t if c.isdigit())
    return int(digitos) if digitos else None


def leer(anios: range) -> tuple[dict, dict, list]:
    import openpyxl

    if not ORIGEN.exists():
        raise SystemExit(f"Falta {ORIGEN}.\n"
                         f"  Bájalo con: python -m src.ingesta.reconocer_ine descargar")
    wb = openpyxl.load_workbook(ORIGEN, read_only=True, data_only=True)
    ws = wb[HOJA]
    filas = ws.iter_rows(values_only=True)
    cabecera = [str(c).strip() if c is not None else "" for c in next(filas)]
    # Posicion de cada anio pedido dentro de la fila.
    columnas = {}
    for a in anios:
        etiqueta = f"Poblacion {a}"
        if etiqueta not in cabecera:
            raise SystemExit(f"el archivo no trae la columna {etiqueta!r}")
        columnas[a] = cabecera.index(etiqueta)

    # (comuna, anio) -> {banda: poblacion}
    acumulado: dict[tuple[int, int], dict[str, int]] = {}
    nombres: dict[int, str] = {}
    edades_raras: list = []
    for fila in filas:
        try:
            comuna = int(fila[COL_COMUNA])
        except (TypeError, ValueError):
            continue
        edad = _edad(fila[COL_EDAD])
        if edad is None:
            edades_raras.append(fila[COL_EDAD])
            continue
        nombres.setdefault(comuna, str(fila[COL_NOMBRE]).strip())
        for a, col in columnas.items():
            v = fila[col]
            if not isinstance(v, (int, float)):
                continue
            v = int(v)
            celda = acumulado.setdefault((comuna, a), dict.fromkeys(
                [b for b, _ in BANDAS] + ["total"], 0))
            celda["total"] += v
            for banda, cae in BANDAS:
                if cae(edad):
                    celda[banda] += v
                    break
    return acumulado, nombres, edades_raras


def cmd_construir(args) -> int:
    import pandas as pd

    anios = range(INICIO.year, FIN.year + 1)
    acumulado, nombres, raras = leer(anios)
    if raras:
        print(f"  edades no numéricas encontradas: {len(raras)}  "
              f"ejemplos {list(dict.fromkeys(map(str, raras)))[:4]}")

    filas = [{"comuna_codigo": c, "comuna": nombres[c], "anio": a, **v}
             for (c, a), v in sorted(acumulado.items())]
    nac = pd.DataFrame(filas)
    asegurar(PROCESSED / "poblacion_comuna_anio")
    nac.to_parquet(PROCESSED / "poblacion_comuna_anio" /
                   "poblacion_comuna_anio.parquet", index=False)
    print(f"  poblacion_comuna_anio : {len(nac):,} filas "
          f"({nac.comuna_codigo.nunique()} comunas x {nac.anio.nunique()} años)")
    print(f"    control: población total del país en 2026 = "
          f"{nac[nac.anio == 2026].total.sum():,}")

    # --- el recorte a las tres ciudades, en el ultimo paso (regla 2) ---
    mapa = {cod: cid for cid, c in CIUDADES.items() for cod in c["comunas"]}
    nac["ciudad_id"] = nac.comuna_codigo.map(mapa)
    ciu = (nac.dropna(subset=["ciudad_id"])
              .groupby(["ciudad_id", "anio"], as_index=False)
              [["total", *[b for b, _ in BANDAS]]].sum())
    asegurar(PROCESSED / "poblacion_ciudad_anio")
    ciu.to_parquet(PROCESSED / "poblacion_ciudad_anio" /
                   "poblacion_ciudad_anio.parquet", index=False)
    print(f"  poblacion_ciudad_anio : {len(ciu)} filas\n")

    piv = ciu.pivot(index="anio", columns="ciudad_id", values="total")
    print("  población total por ciudad y año")
    print(f"  {'año':<8}" + "".join(f"{c:>14}" for c in piv.columns))
    for a, r in piv.iterrows():
        print(f"  {a:<8}" + "".join(f"{int(v):>14,}" for v in r))
    cre = 100 * (piv.iloc[-1] / piv.iloc[0] - 1)
    print(f"  {'cambio':<8}" + "".join(f"{v:>13.1f}%" for v in cre))

    ult = ciu[ciu.anio == FIN.year].set_index("ciudad_id")
    print(f"\n  reparto etario en {FIN.year}")
    print(f"  {'ciudad':<12}{'<1':>9}{'1-4':>10}{'5-14':>11}{'15-64':>12}{'65+':>11}")
    for cid, r in ult.iterrows():
        print(f"  {cid:<12}{int(r.menores_1):>9,}{int(r.de_1_a_4):>10,}"
              f"{int(r.de_5_a_14):>11,}{int(r.de_15_a_64):>12,}{int(r.de_65_y_mas):>11,}")

    # --- valor de referencia en dim_ciudad ---
    ruta = PROCESSED / "dim_ciudad" / "dim_ciudad.parquet"
    if ruta.exists():
        dim = pd.read_parquet(ruta)
        ref = dict(zip(ult.index, ult.total, strict=True))
        dim["poblacion"] = dim.ciudad_id.map(ref).astype("Int64")
        dim["poblacion_anio"] = FIN.year
        dim["fuente_poblacion"] = ("INE, estimaciones y proyecciones 2002-2035, "
                                   "base Censo 2017, agregadas por comuna")
        dim.to_parquet(ruta, index=False)
        print(f"\n  dim_ciudad: columna poblacion actualizada con el año {FIN.year}")
        print("  (para tasas usa poblacion_ciudad_anio: cambia año a año)")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("construir").set_defaults(fn=cmd_construir)

    args = p.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "poblacion.log", encoding="utf-8")])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
