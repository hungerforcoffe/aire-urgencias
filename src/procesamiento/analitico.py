"""Construye `analitico_ciudad_semana`: una fila por ciudad y semana epidemiológica.

Es la última etapa del modelo y el único sitio donde el recorte a tres ciudades
es legítimo (regla 2). Todo lo anterior —lectura de SINCA, lectura del DEIS,
población— opera a escala nacional. Aquí se cruza y se acota.

Qué junta
---------
De `hecho_medicion` sale la exposición (MP2.5) y los controles meteorológicos;
de `hecho_urgencia` el desenlace; de `poblacion_ciudad_anio` el denominador; de
`dim_tiempo` la semana MMWR, el invierno y el período de pandemia.

Asociación, nunca causalidad
----------------------------
La tabla pone en la misma fila una exposición y un desenlace agregados por
ciudad. Eso permite describir cómo covarían, y nada más: es un diseño ecológico
observacional y la fila no dice qué persona respiró qué aire. Ningún nombre de
columna afirma efecto: `mp25_media_lag1` es «el MP2.5 de la semana anterior»,
no «el MP2.5 que provocó estas consultas».

El promedio del aire: media de medias, no media de horas
--------------------------------------------------------
El MP2.5 de la ciudad es el promedio de los promedios de sus estaciones, no el
promedio de todas las horas juntas. Con la segunda forma, la estación que más
horas reportó pesa más, y en Santiago eso significa que unas comunas mandan
sobre otras por un accidente de mantenimiento. La diferencia entre ambas no es
cosmética: llega a 10,3 µg/m³ en la peor semana. Se guarda `mp25_media_pool`
con la versión agrupada para que quien quiera pueda medir esa sensibilidad.

Cobertura mínima
----------------
Un día de estación vale si tiene al menos 18 de 24 horas; una semana de
estación, si tiene al menos 5 de 7 días válidos. Es el criterio del 75 % que se
usa habitualmente en calidad del aire. Se documenta en
`docs/calidad/cobertura_semanal.md` con su efecto medido.

Un control negativo, a propósito
--------------------------------
`urg_diarrea` es diarrea aguda: una urgencia aguda que comparte estación del
año y conducta de consulta con las respiratorias, pero que no tiene por qué
seguir al MP2.5. Si apareciera asociada igual de fuerte que las respiratorias,
lo que estaríamos midiendo es la propensión a consultar, no el aire. Está para
poder desmentir el resultado, no para adornarlo.

Uso
---
    python -m src.procesamiento.analitico construir
    python -m src.procesamiento.analitico verificar
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.procesamiento.geografia import CIUDADES, ciudad_de_codigo  # noqa: E402
from src.rutas import LOGS, PROCESSED, asegurar  # noqa: E402

log = logging.getLogger("analitico")

SALIDA = PROCESSED / "analitico_ciudad_semana"

# --- Umbrales de cobertura. Ver docs/calidad/cobertura_semanal.md ---
HORAS_MINIMAS_DIA = 18      # de 24
DIAS_MINIMOS_SEMANA = 5     # de 7

# --- Causas del DEIS. Los identificadores vienen de dim_causa. ---
CAUSAS_RESP = {
    10: "ira_alta",        # J00-J06
    3: "bronquitis",       # J20-J21
    4: "influenza",        # J09-J11
    5: "neumonia",         # J12-J18
    11: "obstructiva",     # J40-J46
    6: "resp_otras",       # J22, J30-J39, J47, J60-J98
}
CAUSA_TOTAL = 1            # SECCIÓN 1. TOTAL ATENCIONES DE URGENCIA
CAUSA_RESP_AGREGADA = 2    # TOTAL CAUSA SISTEMA RESPIRATORIO (J00-J98)
CAUSA_DIARREA = 29         # control negativo
CAUSAS_COVID = (30, 31)    # virus identificado y no identificado

EDADES = ["menores_1", "de_1_a_4", "de_5_a_14", "de_15_a_64", "de_65_y_mas"]


# --------------------------------------------------------------------------
# Lado del aire
# --------------------------------------------------------------------------
def _agregar_parametro(med: pd.DataFrame, parametro: str) -> pd.DataFrame:
    """Lleva un parámetro horario a ciudad-semana aplicando la cobertura mínima.

    Tres escalones, y cada uno descarta antes de promediar: hora -> día de
    estación -> semana de estación -> semana de ciudad. Promediar primero y
    filtrar después dejaría entrar un día de tres horas con el mismo peso que
    uno completo.
    """
    d = med[med.parametro_id == parametro]
    if d.empty:
        return pd.DataFrame()

    dia = (d.groupby(["ciudad_id", "estacion_id", "semana_id", "fecha"])
             .valor.agg(media="mean", horas="count"))
    dia = dia[dia.horas >= HORAS_MINIMAS_DIA]

    sem = (dia.groupby(level=["ciudad_id", "estacion_id", "semana_id"])
              .media.agg(media="mean", minimo="min", maximo="max", dias="count"))
    sem = sem[sem.dias >= DIAS_MINIMOS_SEMANA]

    ciu = (sem.groupby(level=["ciudad_id", "semana_id"])
              .agg(media=("media", "mean"),
                   mediana=("media", "median"),
                   max_dia=("maximo", "max"),
                   min_dia=("minimo", "min"),
                   estaciones=("media", "size"),
                   dias=("dias", "max")))
    return ciu


def lado_aire(med: pd.DataFrame) -> pd.DataFrame:
    """Exposición y meteorología por ciudad-semana."""
    mp = _agregar_parametro(med, "mp25")
    salida = pd.DataFrame({
        "mp25_media": mp.media,
        "mp25_mediana": mp.mediana,
        "mp25_max_dia": mp.max_dia,
        "mp25_estaciones": mp.estaciones,
        "mp25_dias": mp.dias,
    })

    # Version agrupada, solo para medir la sensibilidad de la decision de
    # promediado. No es la columna que usa el analisis.
    pool = (med[med.parametro_id == "mp25"]
            .groupby(["ciudad_id", "semana_id"]).valor.mean().rename("mp25_media_pool"))
    salida = salida.join(pool)

    tmp = _agregar_parametro(med, "temperatura")
    salida = salida.join(pd.DataFrame({
        "temp_media": tmp.media,
        "temp_min_dia": tmp.min_dia,
        "temp_estaciones": tmp.estaciones,
    }))
    for par, col in [("humedad", "humedad_media"), ("vel_viento", "viento_media")]:
        otro = _agregar_parametro(med, par)
        salida = salida.join(otro.media.rename(col) if not otro.empty
                             else pd.Series(dtype=float, name=col))
    return salida


# --------------------------------------------------------------------------
# Lado de la salud
# --------------------------------------------------------------------------
def lado_salud(fecha_a_semana: dict, completas: set) -> tuple[pd.DataFrame, dict]:
    """Urgencias por ciudad-semana, leyendo `hecho_urgencia` partición a partición.

    El cruce establecimiento -> ciudad se hace por **código de comuna**
    (`ciudad_de_codigo`). Por nombre se perdería Coyhaique entera: el DEIS
    escribe «Coihaique» y el catálogo de aire «Coyhaique».
    """
    est = pq.read_table(PROCESSED / "dim_establecimiento").to_pandas()
    est["ciudad_id"] = est.comuna_codigo.map(ciudad_de_codigo)
    mapa = dict(zip(est.establecimiento_id, est.ciudad_id, strict=True))
    del est

    de_interes = set(CAUSAS_RESP) | {CAUSA_TOTAL, CAUSA_RESP_AGREGADA,
                                     CAUSA_DIARREA, *CAUSAS_COVID}
    partes = []
    for archivo in sorted((PROCESSED / "hecho_urgencia").rglob("*.parquet")):
        t = pq.read_table(archivo, columns=["establecimiento_id", "fecha", "causa_id",
                                            "total", *EDADES]).to_pandas()
        t["ciudad_id"] = t.establecimiento_id.map(mapa)
        t = t[t.ciudad_id.notna() & t.causa_id.isin(de_interes)]
        t["semana_id"] = pd.to_datetime(t.fecha).map(fecha_a_semana)
        t = t[t.semana_id.isin(completas)]
        partes.append(t.groupby(["ciudad_id", "semana_id", "causa_id"])[
            ["total", *EDADES]].sum())
        log.info("%s: %s filas agregadas", archivo.parent.name, f"{len(t):,}")
    bruto = pd.concat(partes).groupby(level=[0, 1, 2]).sum()

    def por_causa(causas, columna) -> pd.Series:
        sel = bruto[bruto.index.get_level_values("causa_id").isin(causas)]
        return sel.groupby(level=[0, 1]).total.sum().rename(columna)

    resp = bruto[bruto.index.get_level_values("causa_id").isin(CAUSAS_RESP)]
    salida = resp.groupby(level=[0, 1])[["total", *EDADES]].sum()
    salida.columns = ["urg_resp"] + [f"urg_resp_{e}" for e in EDADES]

    for cid, nombre in CAUSAS_RESP.items():
        salida = salida.join(por_causa([cid], f"urg_{nombre}"))
    salida = salida.join(por_causa([CAUSA_TOTAL], "urg_totales"))
    salida = salida.join(por_causa([CAUSA_DIARREA], "urg_diarrea"))
    salida = salida.join(por_causa(CAUSAS_COVID, "urg_covid"))

    # Control interno: el agregado que publica el DEIS debe ser la suma de sus
    # seis detalles. Si no lo fuera, el desenlace estaria mal armado.
    agregada = por_causa([CAUSA_RESP_AGREGADA], "agregada")
    dif = (salida.urg_resp - agregada.reindex(salida.index)).abs()
    control = {"filas": int(len(salida)),
               "discrepancia_maxima": int(dif.max()) if len(dif) else 0,
               "filas_discrepantes": int((dif > 0).sum())}
    return salida.fillna(0).astype("int64"), control


# --------------------------------------------------------------------------
def construir() -> tuple[pd.DataFrame, dict]:
    tie = pq.read_table(PROCESSED / "dim_tiempo").to_pandas()
    tie["fecha"] = pd.to_datetime(tie.fecha)
    completas = set(tie.loc[tie.semana_completa, "semana_id"])
    semanas = (tie[tie.semana_completa]
               .drop_duplicates("semana_id")
               .set_index("semana_id")[["anio_epi", "semana_epi", "inicio_semana",
                                        "fin_semana", "estacion_anio", "es_invierno",
                                        "periodo_pandemia"]])

    med = pq.read_table(PROCESSED / "hecho_medicion").to_pandas()
    med["fecha"] = pd.to_datetime(med.fecha)
    med = med.merge(tie[["fecha", "semana_id"]], on="fecha", how="left")
    med = med[med.semana_id.isin(completas)]
    aire = lado_aire(med)
    del med

    salud, control = lado_salud(dict(zip(tie.fecha, tie.semana_id, strict=True)),
                                completas)

    # Marco completo: las tres ciudades por las 450 semanas. Una ciudad-semana
    # sin dato tiene que existir como fila con nulos, no desaparecer: si falta
    # la fila, el hueco es invisible.
    idx = pd.MultiIndex.from_product([sorted(CIUDADES), sorted(completas)],
                                     names=["ciudad_id", "semana_id"])
    df = pd.DataFrame(index=idx).join(aire).join(salud).reset_index()
    df = df.merge(semanas, left_on="semana_id", right_index=True, how="left")
    df["ciudad"] = df.ciudad_id.map(lambda c: CIUDADES[c]["nombre"])

    # --- denominador ---
    pob = pq.read_table(PROCESSED / "poblacion_ciudad_anio").to_pandas()
    pob = pob.rename(columns={"total": "poblacion",
                              **{e: f"poblacion_{e}" for e in EDADES}})
    df = df.merge(pob, left_on=["ciudad_id", "anio_epi"],
                  right_on=["ciudad_id", "anio"], how="left").drop(columns="anio")

    # --- rezagos, hasta dos semanas ---
    df = df.sort_values(["ciudad_id", "inicio_semana"]).reset_index(drop=True)
    for k in (1, 2):
        g = df.groupby("ciudad_id")
        # El rezago solo vale si la semana anterior es la contigua: se comprueba
        # que la fecha de inicio esté exactamente 7*k días antes.
        esperado = df.inicio_semana - pd.Timedelta(days=7 * k)
        previo = g.inicio_semana.shift(k)
        df[f"mp25_media_lag{k}"] = g.mp25_media.shift(k).where(previo == esperado)

    # --- tasas ---
    df["tasa_resp_100k"] = 1e5 * df.urg_resp / df.poblacion
    df["tasa_menores_1_100k"] = 1e5 * df.urg_resp_menores_1 / df.poblacion_menores_1
    df["tasa_de_65_y_mas_100k"] = 1e5 * df.urg_resp_de_65_y_mas / df.poblacion_de_65_y_mas
    # Proporcion respiratoria sobre el total de urgencias. Absorbe los cambios
    # de conducta de consulta, que en 2020 fueron enormes.
    df["prop_resp"] = df.urg_resp / df.urg_totales.replace(0, pd.NA)

    # --- banderas de calidad ---
    df["temp_completa"] = df.temp_media.notna()
    df["cobertura_ok"] = df.mp25_media.notna() & df.temp_media.notna()

    orden = (["ciudad_id", "ciudad", "semana_id", "anio_epi", "semana_epi",
              "inicio_semana", "fin_semana", "estacion_anio", "es_invierno",
              "periodo_pandemia",
              "mp25_media", "mp25_mediana", "mp25_max_dia", "mp25_media_pool",
              "mp25_media_lag1", "mp25_media_lag2", "mp25_estaciones", "mp25_dias",
              "temp_media", "temp_min_dia", "temp_estaciones",
              "humedad_media", "viento_media",
              "urg_resp"] + [f"urg_resp_{e}" for e in EDADES]
             + [f"urg_{n}" for n in CAUSAS_RESP.values()]
             + ["urg_totales", "urg_diarrea", "urg_covid",
                "poblacion"] + [f"poblacion_{e}" for e in EDADES]
             + ["tasa_resp_100k", "tasa_menores_1_100k", "tasa_de_65_y_mas_100k",
                "prop_resp", "temp_completa", "cobertura_ok"])
    return df[orden], control


def cmd_construir(args) -> int:
    df, control = construir()

    if control["filas_discrepantes"]:
        raise SystemExit(
            f"El total respiratorio del DEIS no cuadra con la suma de sus seis "
            f"detalles en {control['filas_discrepantes']} filas "
            f"(máx {control['discrepancia_maxima']}). No se escribe la tabla.")

    faltan = df.mp25_media.isna().sum()
    if faltan:
        raise SystemExit(f"{faltan} semanas-ciudad sin MP2.5. La exposición no "
                         f"puede faltar: revisar antes de escribir.")

    asegurar(SALIDA)
    ruta = SALIDA / "analitico_ciudad_semana.parquet"
    df.to_parquet(ruta, index=False)

    print(f"\n  {ruta}")
    print(f"  {len(df):,} filas · {len(df.columns)} columnas · "
          f"{ruta.stat().st_size / 1024:,.1f} KB")
    print(f"  agregado respiratorio del DEIS = suma de los seis detalles "
          f"en las {control['filas']:,} filas")
    print(f"\n  {'ciudad':<12}{'semanas':>9}{'MP2.5':>9}{'temp':>8}"
          f"{'urg/sem':>10}{'por 100k':>10}{'sin temp':>10}")
    for cid, g in df.groupby("ciudad_id"):
        print(f"  {cid:<12}{len(g):>9}{g.mp25_media.mean():>9.1f}"
              f"{g.temp_media.mean():>8.1f}{g.urg_resp.mean():>10,.0f}"
              f"{g.tasa_resp_100k.mean():>10.1f}{(~g.temp_completa).sum():>10}")
    print(f"\n  filas con cobertura completa: {int(df.cobertura_ok.sum()):,} "
          f"de {len(df):,}")
    print(f"  filas con rezago de 2 semanas: {int(df.mp25_media_lag2.notna().sum()):,}")
    return 0


def cmd_verificar(args) -> int:
    ruta = SALIDA / "analitico_ciudad_semana.parquet"
    if not ruta.exists():
        raise SystemExit(f"No existe {ruta}. Correr primero `construir`.")
    df = pd.read_parquet(ruta)

    print(f"  {len(df):,} filas, {len(df.columns)} columnas\n")
    problemas = []
    if len(df) != 3 * 450:
        problemas.append(f"se esperaban 1.350 filas y hay {len(df)}")
    if df.duplicated(["ciudad_id", "semana_id"]).any():
        problemas.append("hay pares ciudad-semana repetidos")
    if (df.mp25_media < 0).any() or (df.mp25_media > 1000).any():
        problemas.append("MP2.5 fuera de rango plausible")
    if (df.urg_resp > df.urg_totales).any():
        problemas.append("hay semanas con más urgencias respiratorias que totales")
    if df.poblacion.isna().any():
        problemas.append("hay filas sin denominador")

    dif = (df.mp25_media - df.mp25_media_pool).abs()
    print(f"  media de medias vs media agrupada: media {dif.mean():.3f}, "
          f"máx {dif.max():.3f} µg/m³")
    print("  nulos por columna (solo las que tienen):")
    nul = df.isna().sum()
    for col, n in nul[nul > 0].items():
        print(f"    {col:<26}{n:>6}")

    print("\n  " + ("PROBLEMAS:" if problemas else "sin problemas"))
    for p in problemas:
        print(f"    - {p}")
    return 1 if problemas else 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("construir").set_defaults(fn=cmd_construir)
    sub.add_parser("verificar").set_defaults(fn=cmd_verificar)

    args = p.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "analitico.log", encoding="utf-8")])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
