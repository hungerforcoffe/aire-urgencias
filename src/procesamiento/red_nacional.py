"""Construye la red nacional de SINCA: dimensión de estaciones y medias mensuales.

Lee lo que dejó `src/ingesta/red_nacional.py` en la zona cruda y escribe dos
tablas en `data/processed/red_nacional_*`. Es la capa de contexto del mapa: la
red completa del país, con la que se ve dónde hay medición y dónde no.

No toca `hecho_medicion`
------------------------
Esa tabla es horaria, conserva los tres estados de validación por separado y es
la que sostiene el análisis. Esta serie viene ya promediada a día por el propio
Airviro, así que no es la misma clase de dato y no se mezcla. Quien consulte
`hecho_medicion` sigue leyendo horas medidas; quien consulte `red_nacional_mes`
lee medias diarias agregadas a mes, y lo sabe por el nombre de la tabla.

Qué estación es «del estudio»
-----------------------------
Las 16 estaciones del estudio también están en la red nacional, y dibujarlas dos
veces en el mapa sería contar dos veces. Se cruzan **por coordenada**, no por
nombre: SINCA escribe el mismo sitio de varias formas —«Coyhaique» y
«Coihaique», «Parque O'Higgins» y «P. O'Higgins»— y un cruce por texto pierde
estaciones sin avisar. Dos posiciones a menos de 300 m son la misma estación.

La reja de cobertura es la misma del resto del sitio
----------------------------------------------------
Un mes necesita 20 días con dato para mostrar media; un año, 300. Son los mismos
umbrales que ya aplica `src/sitio/exportar.py`, y por la misma razón: El Bosque
midió 59 días en 2025 y su promedio parecía una mejora de la calidad del aire.

Uso
---
    python -m src.procesamiento.red_nacional construir
    python -m src.procesamiento.red_nacional verificar
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.ingesta.red_nacional import CATALOGO, SERIES, Rechazada, validar  # noqa: E402
from src.procesamiento.geografia import ciudad_de  # noqa: E402
from src.rutas import LOGS, PROCESSED, asegurar  # noqa: E402

log = logging.getLogger("red-nacional-proc")

SALIDA_EST = PROCESSED / "red_nacional_estacion"
SALIDA_MES = PROCESSED / "red_nacional_mes"
SALIDA_ANIO = PROCESSED / "red_nacional_anio"

# Misma reja que el resto del sitio. Ver docs/calidad/cobertura_sitio.md.
MIN_DIAS_MES = 20
MIN_DIAS_ANIO = 300

# Dos estaciones a menos de esto son la misma. 300 m es holgado para una
# diferencia de redondeo y estrecho para dos estaciones distintas: las dos más
# cercanas del estudio (Talcahuano) están a 1,3 km.
MISMA_ESTACION_KM = 0.3

# El código romano que usa SINCA y el nombre de la región. El orden es el del
# recorrido de norte a sur, y es también el orden en que conviene listarlas: un
# chileno busca su región por dónde queda, no por su número.
REGIONES_NOMBRE = {
    "XV": "Arica y Parinacota", "I": "Tarapacá", "II": "Antofagasta",
    "III": "Atacama", "IV": "Coquimbo", "V": "Valparaíso",
    "M": "Metropolitana de Santiago", "VI": "O'Higgins", "VII": "Maule",
    "XVI": "Ñuble", "VIII": "Biobío", "IX": "La Araucanía", "XIV": "Los Ríos",
    "X": "Los Lagos", "XI": "Aysén", "XII": "Magallanes",
}
ORDEN_REGION = {r: i for i, r in enumerate(REGIONES_NOMBRE)}


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine. Se implementa acá para no arrastrar una dependencia por esto."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def cargar_estudio() -> pd.DataFrame:
    """Las estaciones del estudio, para saber cuáles ya están en el mapa."""
    ruta = PROCESSED / "dim_estacion"
    if not ruta.exists():
        log.warning("no hay dim_estacion; ninguna estación quedará marcada como del estudio")
        return pd.DataFrame(columns=["estacion_id", "latitud", "longitud"])
    return pq.read_table(ruta).to_pandas()


def cmd_construir(args) -> int:
    if not CATALOGO.exists():
        raise SystemExit(f"No hay catálogo en {CATALOGO}.\n"
                         f"  Constrúyelo con: python -m src.ingesta.red_nacional catalogo")

    ficha = json.loads(CATALOGO.read_text(encoding="utf-8"))
    catalogo = {f"{e['region_macro']}:{e['codigo']}": e for e in ficha["estaciones"]}
    estudio = cargar_estudio()

    filas_dia: list[dict] = []
    estaciones: list[dict] = []
    sin_serie, rechazadas = [], []

    for clave, e in catalogo.items():
        if e["lat"] is None:
            continue
        ruta = SERIES / f"sinca_{e['region_macro']}_{e['codigo']}_mp25_diario.csv"
        if not ruta.exists():
            sin_serie.append(clave)
            continue
        try:
            # Se revalida al leer, no solo al descargar: un archivo de la zona
            # cruda puede haberse truncado al copiarse entre máquinas.
            filas = validar(ruta.read_bytes(), "application/csv")
        except Rechazada as ex:
            rechazadas.append({"estacion": clave, "motivo": str(ex)})
            log.error("%s: %s", clave, ex)
            continue

        for f in filas:
            if f["mp25"] is not None:
                filas_dia.append({"estacion_id": clave, "fecha": f["fecha"],
                                  "mp25": f["mp25"], "estado": f["estado"]})

        # ¿Es una de las 16 del estudio? Se decide por distancia.
        en_estudio, id_estudio = False, None
        for _, r in estudio.iterrows():
            if pd.isna(r.get("latitud")) or pd.isna(r.get("longitud")):
                continue
            if distancia_km(e["lat"], e["lon"], r["latitud"], r["longitud"]) <= MISMA_ESTACION_KM:
                en_estudio, id_estudio = True, int(r["estacion_id"])
                break

        estaciones.append({
            "estacion_id": clave,
            "codigo": e["codigo"],
            "region_macro": e["region_macro"],
            "region_romana": e["region_romana"],
            "region": REGIONES_NOMBRE.get(e["region_romana"], e["region_romana"]),
            "orden_region": ORDEN_REGION.get(e["region_romana"], 99),
            "nombre": e["nombre"],
            "comuna": e["comuna"],
            "lat": e["lat"],
            "lon": e["lon"],
            "ciudad_estudio": ciudad_de(e["comuna"]) if e["comuna"] else None,
            "en_estudio": en_estudio,
            "estacion_id_estudio": id_estudio,
        })

    if not filas_dia:
        log.error("no se pudo leer ninguna serie; no se escribe nada")
        return 1

    dia = pd.DataFrame(filas_dia)
    dia["fecha"] = pd.to_datetime(dia["fecha"])
    dia["anio"] = dia["fecha"].dt.year
    dia["mes"] = dia["fecha"].dt.month

    mes = (dia.groupby(["estacion_id", "anio", "mes"], as_index=False)
              .agg(dias=("mp25", "size"), media=("mp25", "mean"),
                   maximo=("mp25", "max"), sobre50=("mp25", lambda s: int((s > 50).sum()))))
    mes["media"] = mes["media"].round(2)
    mes["maximo"] = mes["maximo"].round(2)
    mes["suficiente"] = mes["dias"] >= MIN_DIAS_MES

    # Las mismas cuatro columnas que trae el bloque `anual` de las 16 del
    # estudio, y calculadas igual, para que el panel de detalle no tenga que
    # saber de qué colección viene la estación que está dibujando.
    anio = (dia.groupby(["estacion_id", "anio"], as_index=False)
               .agg(dias=("mp25", "size"), media=("mp25", "mean"),
                    sobre50=("mp25", lambda s: int((s > 50).sum())),
                    p98=("mp25", lambda s: s.quantile(0.98))))
    anio["media"] = anio["media"].round(2)
    anio["p98"] = anio["p98"].round(2)
    anio["completo"] = anio["dias"] >= MIN_DIAS_ANIO

    est = pd.DataFrame(estaciones)
    resumen_dia = (dia.groupby("estacion_id")
                      .agg(dias_totales=("mp25", "size"),
                           primer_dia=("fecha", "min"), ultimo_dia=("fecha", "max"))
                      .reset_index())
    est = est.merge(resumen_dia, on="estacion_id", how="left")
    est["dias_totales"] = est["dias_totales"].fillna(0).astype(int)

    asegurar(SALIDA_EST, SALIDA_MES, SALIDA_ANIO)
    est.to_parquet(SALIDA_EST / "red_nacional_estacion.parquet", index=False)
    mes.to_parquet(SALIDA_MES / "red_nacional_mes.parquet", index=False)
    anio.to_parquet(SALIDA_ANIO / "red_nacional_anio.parquet", index=False)

    print(f"  estaciones con serie : {len(est)}")
    print(f"    de ellas del estudio: {int(est['en_estudio'].sum())}")
    print(f"    nuevas para el mapa : {int((~est['en_estudio']).sum())}")
    print(f"  días con dato        : {len(dia):,}")
    print(f"  filas estación-mes   : {len(mes):,}  ({int(mes['suficiente'].sum())} con "
          f"{MIN_DIAS_MES}+ días)")
    print(f"  años completos       : {int(anio['completo'].sum())} de {len(anio)}")
    print(f"  regiones cubiertas   : {est['region_romana'].nunique()} de 16")
    if sin_serie:
        print(f"  sin serie descargada : {len(sin_serie)}")
    if rechazadas:
        print(f"  archivos rechazados  : {len(rechazadas)}")
        for r in rechazadas[:5]:
            print(f"    · {r['estacion']}: {r['motivo']}")
    return 0


def cmd_verificar(args) -> int:
    for ruta in (SALIDA_EST, SALIDA_MES, SALIDA_ANIO):
        if not ruta.exists():
            raise SystemExit(f"Falta {ruta}. Corre primero `construir`.")
    est = pq.read_table(SALIDA_EST).to_pandas()
    mes = pq.read_table(SALIDA_MES).to_pandas()
    anio = pq.read_table(SALIDA_ANIO).to_pandas()

    problemas = []
    if est["lat"].isna().any() or est["lon"].isna().any():
        problemas.append("hay estaciones sin coordenada")
    fuera = est[(est["lat"] > -17.3) | (est["lat"] < -56) |
                (est["lon"] > -66) | (est["lon"] < -110)]
    if len(fuera):
        problemas.append(f"{len(fuera)} coordenadas fuera de Chile")
    if est["estacion_id"].duplicated().any():
        problemas.append("hay estacion_id repetidos")
    huerfanas = set(mes["estacion_id"]) - set(est["estacion_id"])
    if huerfanas:
        problemas.append(f"{len(huerfanas)} estaciones en el mensual sin ficha")
    negativos = mes[mes["media"] < 0]
    if len(negativos):
        problemas.append(f"{len(negativos)} medias negativas")
    sin_ficha_anio = set(anio["estacion_id"]) - set(est["estacion_id"])
    if sin_ficha_anio:
        problemas.append(f"{len(sin_ficha_anio)} estaciones en el anual sin ficha")
    # El p98 no puede ser menor que la media: si lo es, el percentil se calculó
    # sobre otro conjunto de filas que la media.
    incoherentes = anio[anio["p98"] < anio["media"]]
    if len(incoherentes):
        problemas.append(f"{len(incoherentes)} años con p98 menor que la media")

    print(f"  estaciones {len(est)}   filas mes {len(mes)}   filas año {len(anio)}")
    print(f"  rango de medias mensuales: {mes['media'].min():.1f} a {mes['media'].max():.1f} µg/m³")
    print(f"  periodo: {mes['anio'].min()} a {mes['anio'].max()}")
    print("  problemas:", "ninguno" if not problemas else "")
    for p in problemas:
        print(f"    · {p}")
    return 1 if problemas else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("construir").set_defaults(fn=cmd_construir)
    sub.add_parser("verificar").set_defaults(fn=cmd_verificar)
    args = p.parse_args(argv)
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "red_nacional.log", encoding="utf-8")])
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
