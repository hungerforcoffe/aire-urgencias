"""Lee los nueve años del DEIS y escribe `hecho_urgencia`, `dim_causa` y
`dim_establecimiento`.

Los cuatro casos especiales, y por qué solo quedan dos
------------------------------------------------------
El DEIS cambió de formato varias veces entre 2018 y 2026. Al mirar las cabeceras
completas de los nueve años aparece algo que simplifica mucho el lector:

    **Las posiciones 0 a 14 son idénticas en TODOS los años.**

Las seis columnas que 2023 añadió —región, dependencia, comuna— van al final,
de la 15 a la 20. Y el `Idcausa` en minúscula de 2022 solo estorba si se cruza
por nombre. **Leyendo por posición, dos de los cuatro casos desaparecen.**

Quedan dos, y ambos en 2020:

  * no tiene fila de cabecera: la primera línea ya es un dato;
  * la fecha viene como `Date.toString()` de Java —
    `Wed Sep 23 00:00:00 GMT-04:00 2020`— en vez de `dd/mm/aaaa`.

Ninguno se supone: la cabecera se detecta mirando si el primer campo dice
`IdEstablecimiento`, y el formato de fecha probando las dos formas conocidas y
registrando cuál se encontró (regla 6).

Los grupos etarios van en columnas, no en filas
-----------------------------------------------
El modelo proponía `hecho_urgencia` con un `grupo_id` en el grano, es decir con
las cinco edades despivotadas a filas. **Se descartó**: multiplicaría 66 millones
de filas por cinco. En Parquet, que es columnar, tener las edades como columnas
cuesta lo mismo en disco y **menos** al consultar — pedir una franja etaria lee
solo esa columna. Despivotar sigue siendo posible en Athena con `UNNEST` si
alguna vez hace falta.

Escala nacional, recorte al final
---------------------------------
Se cargan **los nueve años completos, todo el país y las 40 causas**. El filtro a
tres ciudades y a las seis causas respiratorias ocurre en los agregados, no aquí.
Es la regla 2 del proyecto.

Uso
---
    python -m src.procesamiento.deis construir
    python -m src.procesamiento.deis construir --anios 2018,2019
    python -m src.procesamiento.deis verificar
"""

from __future__ import annotations

import argparse
import csv as _csv
import datetime as dt
import glob
import io
import logging
import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.ingesta.reconocer_deis import (  # noqa: E402
    IDCAUSA_AGREGADAS,
    IDCAUSA_RESPIRATORIA_DETALLE,
)
from src.rutas import INTERIM, LOGS, PROCESSED, RAW, asegurar  # noqa: E402

log = logging.getLogger("deis")

MESES = {m: i for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), start=1)}

# Posiciones fijas en los nueve años. No se cruzan por nombre a propósito:
# 2022 escribe `Idcausa` y los demás `IdCausa`, y 2020 no tiene cabecera.
EST, NEST, CAUSA, GLOSA = 0, 1, 2, 3
TOTAL, M1, A1_4, A5_14, A15_64, A65 = 4, 5, 6, 7, 8, 9
FECHA, SEMANA, TIPOEST, TIPOATN, CAMPANA = 10, 11, 12, 13, 14
# Solo desde 2023:
COD_REGION, N_REGION, COD_DEP, N_DEP, COD_COMUNA, N_COMUNA = 15, 16, 17, 18, 19, 20

LOTE_LINEAS = 500_000


class Rechazo(Exception):
    pass


def fuentes(anios: set[int] | None = None) -> dict[int, Path]:
    """Un archivo por año: el CSV de interim si existe, si no el ZIP crudo.

    2018 y 2019 solo existen como CSV convertido desde Access; el resto vive en
    su ZIP. Ver `docs/calidad/conversion_access_deis.md`.
    """
    out: dict[int, Path] = {}
    for ruta in sorted(glob.glob(str(RAW / "deis" / "*.zip"))):
        nombre = os.path.basename(ruta)
        digitos = [t[:4] for t in nombre.replace(".", "_").split("_") if t[:2] == "20"]
        if digitos:
            out[int(digitos[0])] = Path(ruta)
    for ruta in sorted(glob.glob(str(INTERIM / "deis" / "AtencionesUrgencia*.csv"))):
        a = int(os.path.basename(ruta)[-8:-4])
        out[a] = Path(ruta)           # el CSV manda: el ZIP de ese año no trae uno
    if anios:
        out = {a: r for a, r in out.items() if a in anios}
    return dict(sorted(out.items()))


def abrir(ruta: Path):
    if ruta.suffix.lower() == ".csv":
        return open(ruta, "rb"), ruta.name
    z = zipfile.ZipFile(ruta)
    csvs = [i.filename for i in z.infolist() if i.filename.lower().endswith(".csv")]
    if not csvs:
        dentro = ", ".join(i.filename for i in z.infolist())
        z.close()
        raise Rechazo(f"sin CSV dentro; contiene {dentro}")
    return z.open(csvs[0]), csvs[0]


def _entero(txt: str) -> int:
    t = txt.strip()
    if not t:
        return 0
    try:
        return int(t)
    except ValueError:
        return 0


def leer_anio(anio: int, ruta: Path):
    """Genera lotes de filas ya tipadas, junto con el informe del año."""
    flujo, nombre = abrir(ruta)
    cache_fecha: dict[str, dt.date] = {}
    informe = {"archivo": nombre, "variante_fecha": None, "con_cabecera": None,
               "campos": None, "filas": 0, "sin_fecha": 0, "fuera_anio": 0}
    establecimientos: dict[str, tuple] = {}
    causas: dict[int, str] = {}

    def fecha_de(cru: str) -> dt.date | None:
        f = cache_fecha.get(cru)
        if f is not None:
            return f
        try:
            if len(cru) == 10 and cru[2] == "/" and cru[5] == "/":
                f = dt.date(int(cru[6:10]), int(cru[3:5]), int(cru[0:2]))
                informe["variante_fecha"] = informe["variante_fecha"] or "dd/mm/aaaa"
            else:
                p = cru.split()
                f = dt.date(int(p[5]), MESES[p[1]], int(p[2]))
                informe["variante_fecha"] = informe["variante_fecha"] or "java_date"
        except (ValueError, IndexError, KeyError):
            return None
        cache_fecha[cru] = f
        return f

    lote: list[tuple] = []
    with io.TextIOWrapper(flujo, encoding="latin-1", newline="") as texto:
        lector = _csv.reader(texto, delimiter=";")
        for i, campos in enumerate(lector):
            if not campos or len(campos) < 15:
                continue
            if i == 0:
                informe["campos"] = len(campos)
                informe["con_cabecera"] = campos[EST].strip() == "IdEstablecimiento"
                if informe["con_cabecera"]:
                    continue
            f = fecha_de(campos[FECHA].strip())
            if f is None:
                informe["sin_fecha"] += 1
                continue
            if f.year != anio:
                informe["fuera_anio"] += 1
                continue
            try:
                causa = int(campos[CAUSA])
            except ValueError:
                informe["sin_fecha"] += 1
                continue

            est = campos[EST].strip()
            if est not in establecimientos:
                establecimientos[est] = (
                    campos[NEST].strip(), campos[TIPOEST].strip(),
                    _entero(campos[COD_REGION]) if len(campos) > COD_REGION else 0,
                    campos[N_REGION].strip() if len(campos) > N_REGION else "",
                    _entero(campos[COD_COMUNA]) if len(campos) > COD_COMUNA else 0,
                    campos[N_COMUNA].strip() if len(campos) > N_COMUNA else "")
            if causa not in causas:
                causas[causa] = campos[GLOSA].strip()

            lote.append((est, f, _entero(campos[SEMANA]), causa,
                         campos[TIPOATN].strip(), campos[CAMPANA].strip(),
                         _entero(campos[TOTAL]), _entero(campos[M1]),
                         _entero(campos[A1_4]), _entero(campos[A5_14]),
                         _entero(campos[A15_64]), _entero(campos[A65])))
            informe["filas"] += 1
            if len(lote) >= LOTE_LINEAS:
                yield lote, None
                lote = []
    flujo.close()
    if lote:
        yield lote, None
    informe["establecimientos"] = establecimientos
    informe["causas"] = causas
    yield None, informe


def escribir_anio(anio: int, lotes, destino: Path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    esquema = pa.schema([
        ("establecimiento_id", pa.string()), ("fecha", pa.date32()),
        ("semana_deis", pa.int8()), ("causa_id", pa.int16()),
        ("tipo_atencion", pa.string()), ("tipo_campana", pa.string()),
        ("total", pa.int32()), ("menores_1", pa.int32()), ("de_1_a_4", pa.int32()),
        ("de_5_a_14", pa.int32()), ("de_15_a_64", pa.int32()), ("de_65_y_mas", pa.int32()),
    ])
    carpeta = destino / f"anio={anio}"
    if carpeta.exists():
        for viejo in carpeta.glob("*.parquet"):
            viejo.unlink()
    asegurar(carpeta)
    escritor = pq.ParquetWriter(carpeta / f"parte-{anio}.parquet", esquema,
                                compression="snappy")
    informe = None
    try:
        for lote, inf in lotes:
            if inf is not None:
                informe = inf
                break
            cols = list(zip(*lote, strict=True))
            escritor.write_table(pa.Table.from_arrays(
                [pa.array(c, t) for c, t in zip(cols, esquema.types, strict=True)],
                schema=esquema))
    finally:
        escritor.close()
    return informe


def cmd_construir(args) -> int:
    anios = {int(a) for a in args.anios.split(",")} if args.anios else None
    origenes = fuentes(anios)
    if not origenes:
        raise SystemExit("no hay archivos del DEIS")

    destino = PROCESSED / "hecho_urgencia"
    asegurar(destino)
    todos_est: dict[str, tuple] = {}
    todas_causas: dict[int, str] = {}
    resumen = []

    for anio, ruta in origenes.items():
        print(f"  {anio} · {ruta.name[:52]}", flush=True)
        try:
            inf = escribir_anio(anio, leer_anio(anio, ruta), destino)
        except Rechazo as e:
            print(f"      SALTADO — {e}")
            continue
        # El establecimiento y la causa de un año no pisan a los de otro salvo
        # que traigan más información: 2023+ añade región y comuna.
        for k, v in inf.pop("establecimientos").items():
            if k not in todos_est or (v[2] and not todos_est[k][2]):
                todos_est[k] = v
        todas_causas.update(inf.pop("causas"))
        inf["anio"] = anio
        resumen.append(inf)
        print(f"      {inf['filas']:>10,} filas · {inf['campos']} campos · "
              f"cabecera {'sí' if inf['con_cabecera'] else 'NO'} · "
              f"fecha {inf['variante_fecha']}", flush=True)
        if inf["sin_fecha"]:
            print(f"      {inf['sin_fecha']:,} líneas sin fecha utilizable")
        if inf["fuera_anio"]:
            print(f"      {inf['fuera_anio']:,} filas de otro año, descartadas")
        log.info("%s: %s", anio, inf)

    if not resumen:
        raise SystemExit("no se leyó ningún año")

    import pandas as pd
    dc = pd.DataFrame([{
        "causa_id": c, "glosa": g,
        "es_agregado": c in IDCAUSA_AGREGADAS,
        "es_respiratoria_detalle": c in IDCAUSA_RESPIRATORIA_DETALLE,
    } for c, g in sorted(todas_causas.items())])
    asegurar(PROCESSED / "dim_causa")
    dc.to_parquet(PROCESSED / "dim_causa" / "dim_causa.parquet", index=False)

    de = pd.DataFrame([{
        "establecimiento_id": k, "nombre": v[0], "tipo": v[1],
        "region_codigo": v[2] or None, "region": v[3] or None,
        "comuna_codigo": v[4] or None, "comuna": v[5] or None,
    } for k, v in sorted(todos_est.items())])
    de["region_codigo"] = de["region_codigo"].astype("Int64")
    de["comuna_codigo"] = de["comuna_codigo"].astype("Int64")
    asegurar(PROCESSED / "dim_establecimiento")
    de.to_parquet(PROCESSED / "dim_establecimiento" / "dim_establecimiento.parquet",
                  index=False)

    total = sum(r["filas"] for r in resumen)
    print(f"\n  años leídos          : {len(resumen)}")
    print(f"  filas en hecho_urgencia: {total:,}")
    print(f"  dim_causa            : {len(dc)} causas "
          f"({int(dc.es_agregado.sum())} agregados, "
          f"{int(dc.es_respiratoria_detalle.sum())} respiratorias de detalle)")
    print(f"  dim_establecimiento  : {len(de)} establecimientos, "
          f"{int(de.comuna_codigo.notna().sum())} con comuna")
    return 0


def cmd_verificar(args) -> int:
    """Comprueba identidades que el propio archivo declara.

    El DEIS publica totales junto al detalle. Si un total no cuadra con la suma
    de sus partes, la carga perdio filas o duplico alguna, y ninguna consulta
    posterior lo notaria.

    Se recorre por lotes con pyarrow y no con pandas: 66 millones de filas en un
    DataFrame son varios gigabytes, y aqui solo hacen falta sumas.
    """
    import pandas as pd
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.dataset as ds

    ruta = PROCESSED / "hecho_urgencia"
    if not ruta.exists():
        raise SystemExit(f"Falta {ruta}. Corre antes «deis construir».")
    dc = pd.read_parquet(PROCESSED / "dim_causa" / "dim_causa.parquet")
    glosa = dict(zip(dc.causa_id, dc.glosa, strict=True))

    edades = ["menores_1", "de_1_a_4", "de_5_a_14", "de_15_a_64", "de_65_y_mas"]
    datos = ds.dataset(ruta, format="parquet", partitioning="hive")

    filas = descuadran = 0
    por_causa: dict[int, int] = {}
    for lote in datos.to_batches(columns=["causa_id", "total", *edades]):
        filas += lote.num_rows
        suma = lote.column("menores_1")
        for c in edades[1:]:
            suma = pc.add(suma, lote.column(c))
        descuadran += pc.sum(pc.not_equal(suma, lote.column("total"))).as_py() or 0
        # group_by vive en Table, no en RecordBatch: hay que envolver el lote.
        tab = (pa.Table.from_batches([lote]).select(["causa_id", "total"])
               .group_by("causa_id").aggregate([("total", "sum")]))
        for c, v in zip(tab.column("causa_id").to_pylist(),
                        tab.column("total_sum").to_pylist(), strict=True):
            por_causa[c] = por_causa.get(c, 0) + (v or 0)

    print(f"  filas recorridas: {filas:,}\n")
    print("  1. total == suma de las cinco edades")
    print(f"     filas que no cuadran: {descuadran:,} de {filas:,}"
          f"   {'(perfecto)' if descuadran == 0 else '<-- REVISAR'}\n")

    def g(c):
        return f"{c} {glosa.get(c, '?')[:46]}"

    print("  2. el subtotal respiratorio contra la suma de sus seis detalles")
    detalle = sum(por_causa.get(c, 0) for c in sorted(IDCAUSA_RESPIRATORIA_DETALLE))
    sub = por_causa.get(2, 0)
    print(f"     IdCausa 2            {sub:>14,}   {glosa.get(2, '')[:40]}")
    print(f"     suma 3,4,5,6,10,11   {detalle:>14,}")
    print(f"     diferencia           {sub - detalle:>+14,}"
          f"   {'(cuadra exacto)' if sub == detalle else '<-- no cuadran'}\n")

    print("  3. las diez causas con mas atenciones")
    agg = set(dc[dc.es_agregado].causa_id)
    resp = set(dc[dc.es_respiratoria_detalle].causa_id)
    for c, v in sorted(por_causa.items(), key=lambda x: -x[1])[:10]:
        marca = "AGREGADO" if c in agg else ("respiratoria" if c in resp else "detalle")
        print(f"     {v:>14,}  {marca:<13} {g(c)}")

    print("\n  4. las seis causas del estudio, por separado")
    for c in sorted(IDCAUSA_RESPIRATORIA_DETALLE):
        print(f"     {por_causa.get(c, 0):>14,}  {g(c)}")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("construir")
    c.add_argument("--anios", default=None, help="lista separada por comas")
    c.set_defaults(fn=cmd_construir)
    sub.add_parser("verificar").set_defaults(fn=cmd_verificar)

    args = p.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "deis.log", encoding="utf-8")])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
