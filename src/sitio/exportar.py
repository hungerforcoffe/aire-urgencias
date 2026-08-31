"""Exporta desde Athena los agregados que consume el sitio estático.

Por qué existe
--------------
GitHub Pages sirve archivos y nada más: no ejecuta Python, no abre conexiones a
AWS y **no puede guardar un secreto**. Una página que consultara Athena en vivo
tendría que llevar la llave de acceso escrita en su JavaScript, o sea publicarla.
Por eso el sitio no consulta la base: lee los JSON que escribe este script, que
sí corre con credenciales, pero en el computador de quien publica.

Qué sale y qué no
-----------------
Solo **agregados ya publicables**: medias mensuales por estación, medianas por
sector de viento, y la tabla analítica semanal por ciudad. Ningún registro
individual, ninguna fila de `hecho_urgencia`, ninguna atención de una persona.
El total ronda los 700 kB, del orden de las figuras de un informe.

Esto es lo que permite versionar `sitio/assets/datos/` sin romper la regla de
que se versiona el código y no los datos: lo que entra al repositorio no es la
zona de datos, es el resultado publicado. Las zonas `raw/`, `interim/` y
`processed/` siguen fuera.

La reja de cobertura
--------------------
Un año con pocos días no tiene media anual. El Bosque midió 59 días en 2025
—enero a marzo, puro verano— y su promedio da 14,6 µg/m³ contra 26,2 el año
anterior: leído sin mirar cobertura parece que la comuna se limpió, cuando lo
que pasó es que el equipo dejó de medir justo antes del invierno.

`MIN_DIAS_ANIO` marca esos años como parciales. El sitio los muestra tachados y
los deja fuera de los totales de ciudad. Ver `docs/calidad/cobertura_sitio.md`.

Uso
---
    python -m src.sitio.exportar
    python -m src.sitio.exportar --salida sitio/assets/datos --verificar
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

from src.nube.consultar import consultar  # noqa: E402
from src.rutas import LOGS, RAIZ, asegurar  # noqa: E402

SALIDA = RAIZ / "sitio" / "assets" / "datos"

# Un año necesita al menos este número de días con dato para que su media anual
# se muestre como tal. 300 de 365 es 82%: tolera un mes de mantención pero no
# tolera que falte una estación entera del año.
MIN_DIAS_ANIO = 300

# Horas válidas mínimas para que un día cuente. 18 de 24 es el criterio que ya
# usa `docs/calidad/cobertura_horaria_semanal.md`.
MIN_HORAS_DIA = 18

SECTORES = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]

log = logging.getLogger("sitio.exportar")


# --------------------------------------------------------------------------
# Consultas
# --------------------------------------------------------------------------

SQL_ROSA = """
WITH p AS (
  SELECT estacion_id, ciudad_id, fecha, hora,
         MAX(CASE WHEN parametro_id='mp25'       THEN valor END) AS mp25,
         MAX(CASE WHEN parametro_id='dir_viento' THEN valor END) AS dir,
         MAX(CASE WHEN parametro_id='vel_viento' THEN valor END) AS vel
  FROM hecho_medicion
  GROUP BY estacion_id, ciudad_id, fecha, hora
), s AS (
  SELECT estacion_id, mp25, vel, month(fecha) AS mes,
         CAST(FLOOR(MOD(dir + 22.5, 360.0) / 45.0) AS integer) AS sector
  FROM p
  WHERE mp25 IS NOT NULL AND dir IS NOT NULL
    AND mp25 >= 0 AND dir BETWEEN 0 AND 360
)
SELECT estacion_id, sector,
       COUNT(*)                                                  AS n_horas,
       approx_percentile(mp25, 0.5)                              AS med_anual,
       COUNT_IF(mes BETWEEN 5 AND 8)                             AS n_invierno,
       approx_percentile(CASE WHEN mes BETWEEN 5 AND 8 THEN mp25 END, 0.5) AS med_invierno,
       AVG(vel)                                                  AS vel_media
FROM s
GROUP BY estacion_id, sector
"""

SQL_DIARIO_BASE = f"""
SELECT estacion_id, ciudad_id, fecha, AVG(valor) AS mp25
FROM hecho_medicion
WHERE parametro_id = 'mp25' AND valor >= 0
GROUP BY estacion_id, ciudad_id, fecha
HAVING COUNT(*) >= {MIN_HORAS_DIA}
"""

SQL_MENSUAL = f"""
WITH d AS ({SQL_DIARIO_BASE})
SELECT estacion_id, year(fecha) AS anio, month(fecha) AS mes,
       COUNT(*) AS dias, AVG(mp25) AS media, MAX(mp25) AS maximo,
       COUNT_IF(mp25 > 50) AS sobre50
FROM d GROUP BY estacion_id, year(fecha), month(fecha)
"""

SQL_ANUAL = f"""
WITH d AS ({SQL_DIARIO_BASE})
SELECT estacion_id, year(fecha) AS anio, COUNT(*) AS dias,
       AVG(mp25) AS media, COUNT_IF(mp25 > 50) AS sobre50,
       approx_percentile(mp25, 0.98) AS p98
FROM d GROUP BY estacion_id, year(fecha)
"""

SQL_ESTACIONES = """
SELECT estacion_id, nombre_sinca, ciudad_id, comuna, region,
       latitud, longitud, cobertura_pct
FROM dim_estacion
WHERE ciudad_id IS NOT NULL AND latitud IS NOT NULL
"""

SQL_CIUDADES = """
SELECT ciudad_id, nombre, region, n_comunas, poblacion, pct_lena_casen
FROM dim_ciudad
"""

# Columnas de la tabla analítica que el sitio realmente usa. Se recortan a
# propósito: llevar las 49 al navegador sería mandar peso que nadie grafica.
COLS_SEMANAL = [
    "ciudad_id", "semana_id", "anio_epi", "semana_epi", "inicio_semana",
    "es_invierno", "periodo_pandemia",
    "mp25_media", "mp25_max_dia", "mp25_media_lag1", "mp25_media_lag2",
    "mp25_estaciones", "mp25_dias", "temp_media", "temp_min_dia",
    "urg_resp", "urg_totales", "tasa_resp_100k",
    "tasa_menores_1_100k", "tasa_de_65_y_mas_100k", "prop_resp",
    "urg_ira_alta", "urg_bronquitis", "urg_influenza", "urg_neumonia",
    "urg_obstructiva", "urg_resp_otras",
    "poblacion", "cobertura_ok",
]


# --------------------------------------------------------------------------
# Validación: un fallo nunca puede parecer un éxito
# --------------------------------------------------------------------------

class ExportacionInvalida(RuntimeError):
    """La consulta volvió, pero lo que trajo no sirve."""


def validar(df: pd.DataFrame, nombre: str, filas_min: int,
            columnas: tuple[str, ...] = ()) -> pd.DataFrame:
    """Comprueba que un resultado sea usable antes de escribirlo.

    Athena devuelve un DataFrame vacío sin levantar error cuando la tabla existe
    pero la partición no, y un `SELECT` mal escrito puede devolver una columna
    entera en nulo. Las dos cosas se ven como éxito desde arriba.
    """
    if df is None or df.empty:
        raise ExportacionInvalida(f"{nombre}: la consulta volvió vacía")
    if len(df) < filas_min:
        raise ExportacionInvalida(
            f"{nombre}: {len(df)} filas, se esperaban al menos {filas_min}")
    faltan = [c for c in columnas if c not in df.columns]
    if faltan:
        raise ExportacionInvalida(f"{nombre}: faltan columnas {faltan}")
    for c in columnas:
        if df[c].isna().all():
            raise ExportacionInvalida(f"{nombre}: la columna '{c}' vino toda nula")
    log.info("  %-12s %6d filas  ok", nombre, len(df))
    return df


def redondear(valor, decimales: int = 1):
    """Float listo para JSON: `None` en vez de NaN, y sin cola de decimales."""
    if valor is None or pd.isna(valor):
        return None
    return round(float(valor), decimales)


# --------------------------------------------------------------------------
# Armado
# --------------------------------------------------------------------------

def construir_estaciones(est, rosa, anual, con_dato: set[int]) -> list[dict]:
    """Una entrada por estación: geometría, rosa de contaminación y años.

    Solo entran las estaciones que efectivamente midieron. `dim_estacion`
    incluye estaciones que SINCA lista pero que nunca entregaron datos
    validados; ponerlas en el mapa como círculos permanentemente vacíos no
    informa nada. Cuáles quedaron fuera se anota en `meta.json`.
    """
    salida = []
    for fila in est.sort_values(["ciudad_id", "estacion_id"]).itertuples():
        eid = int(fila.estacion_id)
        if eid not in con_dato:
            continue

        g = rosa[rosa.estacion_id == eid].sort_values("sector")
        r = None
        if len(g) == len(SECTORES):
            r = {
                "invierno": [redondear(v) for v in g.med_invierno],
                "anual": [redondear(v) for v in g.med_anual],
                "horas_invierno": [int(v) for v in g.n_invierno],
                "horas": [int(v) for v in g.n_horas],
                "vel_media": [redondear(v) for v in g.vel_media],
            }

        a = anual[anual.estacion_id == eid].sort_values("anio")
        anios = {
            int(x.anio): {
                "dias": int(x.dias),
                "media": redondear(x.media),
                "sobre50": int(x.sobre50),
                "p98": redondear(x.p98),
                # La reja va calculada acá y no en el navegador: la regla es del
                # análisis, no de la presentación.
                "completo": bool(x.dias >= MIN_DIAS_ANIO),
            }
            for x in a.itertuples()
        }

        nombre = (fila.nombre_sinca or "").replace("Estación ", "").strip()
        salida.append({
            "id": eid,
            "nombre": nombre or f"Estación {eid}",
            "ciudad": fila.ciudad_id,
            "comuna": fila.comuna,
            "region": fila.region,
            "lat": round(float(fila.latitud), 5),
            "lon": round(float(fila.longitud), 5),
            "mide_viento": r is not None,
            "rosa": r,
            "anual": anios,
        })
    return salida


def construir_mensual(mens, ids: set[int]) -> dict:
    """`{"2018-01": {"190": [media, dias, sobre50], ...}, ...}`.

    Se indexa por mes y no por estación porque el mapa dibuja un mes completo
    por cuadro de la animación: así cada paso es una sola lectura.

    `ids` acota a las estaciones que el sitio muestra. `hecho_medicion` es
    nacional a propósito —la regla 2 dice acotar al final— así que trae
    estaciones fuera de las tres ciudades, como Talagante, que aquí sobran.
    """
    meses: dict[str, dict[str, list]] = {}
    for x in mens.itertuples():
        eid = int(x.estacion_id)
        if eid not in ids:
            continue
        clave = f"{int(x.anio)}-{int(x.mes):02d}"
        meses.setdefault(clave, {})[str(eid)] = [
            redondear(x.media), int(x.dias), int(x.sobre50)]
    return meses


def resumir_ciudades(ciudades, estaciones: list[dict], anio: int) -> list[dict]:
    """Cifra por ciudad con la reja aplicada: solo estaciones-año completas."""
    salida = []
    for fila in ciudades.itertuples():
        cid = fila.ciudad_id
        vals = [e["anual"][anio] for e in estaciones
                if e["ciudad"] == cid and anio in e["anual"]
                and e["anual"][anio]["completo"]]
        resumen = None
        if vals:
            resumen = {
                "media": redondear(sum(v["media"] for v in vals) / len(vals)),
                "sobre50": round(sum(v["sobre50"] for v in vals) / len(vals)),
                "estaciones": len(vals),
            }
        salida.append({
            "id": cid,
            "nombre": fila.nombre,
            "region": fila.region,
            "comunas": int(fila.n_comunas),
            "poblacion": int(fila.poblacion),
            "pct_lena_casen": redondear(fila.pct_lena_casen),
            "n_estaciones": sum(1 for e in estaciones if e["ciudad"] == cid),
            "resumen": resumen,
        })
    return salida


def escribir(destino: Path, nombre: str, objeto) -> int:
    """Escribe un JSON compacto y devuelve su tamaño en bytes."""
    ruta = destino / nombre
    texto = json.dumps(objeto, ensure_ascii=False, separators=(",", ":"))
    ruta.write_text(texto, encoding="utf-8")
    tam = ruta.stat().st_size
    log.info("  %-20s %8.1f kB", nombre, tam / 1024)
    return tam


def exportar(destino: Path, anio_resumen: int) -> dict:
    asegurar(destino)
    log.info("consultando Athena")

    est = validar(consultar(SQL_ESTACIONES), "estaciones", 10,
                  ("latitud", "longitud", "ciudad_id"))
    rosa = validar(consultar(SQL_ROSA), "rosa", 8 * 5, ("med_invierno",))
    mens = validar(consultar(SQL_MENSUAL), "mensual", 500, ("media",))
    anual = validar(consultar(SQL_ANUAL), "anual", 50, ("media", "dias"))
    ciu = validar(consultar(SQL_CIUDADES), "ciudades", 3, ("poblacion",))
    # El ORDER BY no es cosmético: el sitio calcula rezagos recorriendo el
    # arreglo, y Athena no garantiza orden salvo que se pida. Ordenado también
    # hace que el JSON no cambie de una corrida a otra, y el diff de git muestra
    # lo que realmente cambió.
    sem = validar(
        consultar("SELECT * FROM analitico_ciudad_semana ORDER BY ciudad_id, semana_id"),
        "semanal", 1000, ("mp25_media", "urg_resp", "tasa_resp_100k"))

    # Las estaciones del sitio son las que midieron y pertenecen a una de las
    # tres ciudades. `hecho_medicion` es nacional (regla 2) y `dim_estacion`
    # lista estaciones que nunca entregaron datos: ambas se descartan acá.
    con_dato = set(mens.estacion_id.astype(int))
    en_ciudad = set(est.estacion_id.astype(int))
    ids = con_dato & en_ciudad

    estaciones = construir_estaciones(est, rosa, anual, ids)
    if not any(e["rosa"] for e in estaciones):
        raise ExportacionInvalida("ninguna estación quedó con rosa de viento")

    meses = construir_mensual(mens, ids)
    ciudades = resumir_ciudades(ciu, estaciones, anio_resumen)

    sem = sem[[c for c in COLS_SEMANAL if c in sem.columns]].copy()
    for c in sem.select_dtypes("float").columns:
        sem[c] = sem[c].round(3)
    sem["inicio_semana"] = sem["inicio_semana"].astype(str)
    semanal = json.loads(sem.to_json(orient="records", date_format="iso"))

    ultimo = max(meses)
    meta = {
        "generado": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "ultimo_mes": ultimo,
        "min_dias_anio": MIN_DIAS_ANIO,
        "min_horas_dia": MIN_HORAS_DIA,
        "anio_resumen": anio_resumen,
        "sectores": SECTORES,
        "conteos": {
            "estaciones": len(estaciones),
            "estaciones_con_viento": sum(1 for e in estaciones if e["rosa"]),
            "meses": len(meses),
            "semanas": len(semanal),
        },
        # Se anota en vez de callarse: una estación ausente del mapa tiene que
        # tener un motivo escrito, no desaparecer sin más.
        "excluidas": {
            "sin_mediciones": sorted(en_ciudad - con_dato),
            "fuera_de_las_tres_ciudades": sorted(con_dato - en_ciudad),
        },
        "fuentes": {
            "aire": "SINCA — Sistema de Información Nacional de Calidad del Aire (MMA)",
            "salud": "DEIS — Departamento de Estadísticas e Información de Salud (MINSAL)",
            "poblacion": "INE — proyecciones comunales",
            "reanalisis": "Open-Meteo (ERA5) — se consulta desde el navegador",
        },
    }

    log.info("escribiendo en %s", destino)
    total = sum([
        escribir(destino, "meta.json", meta),
        escribir(destino, "estaciones.json", estaciones),
        escribir(destino, "mensual.json", meses),
        escribir(destino, "ciudades.json", ciudades),
        escribir(destino, "semanal.json", semanal),
    ])
    log.info("total %.1f kB", total / 1024)
    return meta


def verificar(destino: Path) -> int:
    """Relee lo escrito y comprueba que el navegador podrá usarlo."""
    problemas = []
    try:
        meta = json.loads((destino / "meta.json").read_text(encoding="utf-8"))
        estaciones = json.loads((destino / "estaciones.json").read_text(encoding="utf-8"))
        meses = json.loads((destino / "mensual.json").read_text(encoding="utf-8"))
        semanal = json.loads((destino / "semanal.json").read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        print(f"  falta un archivo: {e.filename}")
        return 1

    if len(estaciones) != meta["conteos"]["estaciones"]:
        problemas.append("estaciones.json no cuadra con meta.json")
    ids = {str(e["id"]) for e in estaciones}
    huerfanos = {k for mes in meses.values() for k in mes} - ids
    if huerfanos:
        problemas.append(f"mensual.json cita estaciones inexistentes: {sorted(huerfanos)}")
    for e in estaciones:
        if e["rosa"] and len(e["rosa"]["invierno"]) != 8:
            problemas.append(f"estación {e['id']}: la rosa no tiene 8 sectores")
        if not (-56 < e["lat"] < -17 and -110 < e["lon"] < -66):
            problemas.append(f"estación {e['id']}: coordenadas fuera de Chile")
    if not semanal:
        problemas.append("semanal.json vacío")

    for p in problemas:
        print(f"  {p}")
    if problemas:
        print(f"\n  {len(problemas)} problema(s)")
        return 1
    print(f"  {len(estaciones)} estaciones · {len(meses)} meses · "
          f"{len(semanal)} semanas · corte {meta['ultimo_mes']}")
    print("  todo consistente")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--salida", type=Path, default=SALIDA)
    p.add_argument("--anio-resumen", type=int, default=2024,
                   help="año de la cifra destacada por ciudad (por defecto el "
                        "último completo)")
    p.add_argument("--verificar", action="store_true",
                   help="revisar lo ya escrito, sin consultar Athena")
    args = p.parse_args(argv)

    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")

    if args.verificar:
        return verificar(args.salida)

    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S",
        handlers=[logging.FileHandler(LOGS / "sitio_exportar.log", encoding="utf-8"),
                  logging.StreamHandler()])
    try:
        exportar(args.salida, args.anio_resumen)
    except ExportacionInvalida as e:
        log.error("exportación abortada: %s", e)
        log.error("no se escribió nada; los JSON anteriores siguen intactos")
        return 1
    return verificar(args.salida)


if __name__ == "__main__":
    raise SystemExit(main())
