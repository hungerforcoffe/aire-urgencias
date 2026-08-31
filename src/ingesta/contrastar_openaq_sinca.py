"""Contraste de validacion: un mismo dia-estacion en OpenAQ y en SINCA.

Objetivo (tarea 2b del reconocimiento): decidir si OpenAQ replica exactamente el
dato de SINCA o si difiere. Si es identico, OpenAQ queda solo como marco de
referencia internacional. Si difiere de forma sistematica, la diferencia es en
si misma un hallazgo.

El script NO asume que las horas de ambas fuentes esten alineadas: prueba
desfases de -2 a +2 horas y reporta cual minimiza la discrepancia. Confundir un
desalineamiento horario con una diferencia de valores seria un error grave.

Uso
---
    python -m src.ingesta.contrastar_openaq_sinca \
        --openaq-id 25 --region RM --estacion D14 --desde 20230701 --hasta 20230731
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import logging
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.ingesta.reconocer_openaq import BUCKET, PREFIJO, cliente  # noqa: E402
from src.ingesta.sinca_cliente import (  # noqa: E402
    SincaVacio,
    construir_macro,
    descargar,
    parsear,
)
from src.rutas import LOGS, RAW, asegurar  # noqa: E402

log = logging.getLogger("contraste")


def dias(desde: str, hasta: str):
    d0 = date(int(desde[:4]), int(desde[4:6]), int(desde[6:8]))
    d1 = date(int(hasta[:4]), int(hasta[4:6]), int(hasta[6:8]))
    while d0 <= d1:
        yield d0
        d0 += timedelta(days=1)


# --------------------------------------------------------------------------
def leer_openaq(location_id: int, desde: str, hasta: str, parametro: str = "pm25",
                guardar: bool = True) -> dict[str, float]:
    """Devuelve {'AAAA-MM-DDTHH:MM': valor} desde el archivo S3 de OpenAQ."""
    s3 = cliente()
    destino = RAW / "openaq"
    if guardar:
        asegurar(destino)

    def un_dia(d: date):
        key = (f"{PREFIJO}locationid={location_id}/year={d:%Y}/month={d:%m}/"
               f"location-{location_id}-{d:%Y%m%d}.csv.gz")
        try:
            crudo = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
        except Exception:  # noqa: BLE001  -> dia ausente, no es error fatal
            return {}
        if guardar:
            (destino / f"openaq_loc{location_id}_{d:%Y%m%d}.csv.gz").write_bytes(crudo)
        texto = gzip.decompress(crudo).decode("utf-8", errors="replace")
        out = {}
        for fila in csv.DictReader(io.StringIO(texto)):
            if fila.get("parameter") != parametro:
                continue
            # 2023-07-14T01:00:00-04:00 -> 2023-07-14T01:00 (hora local chilena)
            out[fila["datetime"][:16]] = float(fila["value"])
        return out

    serie: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        for parcial in ex.map(un_dia, dias(desde, hasta)):
            serie.update(parcial)
    return serie


# --------------------------------------------------------------------------
def leer_sinca(region: str, estacion: str, desde: str, hasta: str,
               parametro: str = "PM25", guardar: bool = True) -> dict[str, dict]:
    """Devuelve {'AAAA-MM-DDTHH:MM': {'validado':..,'preliminar':..,'no_validado':..}}."""
    macro = construir_macro(region, estacion, parametro)
    d, h = desde[2:], hasta[2:]  # SINCA usa AAMMDD
    sesion = requests.Session()
    crudo = descargar(macro, d, h, sesion=sesion)

    if guardar:
        destino = RAW / "sinca"
        asegurar(destino)
        (destino / f"sinca_{region}{estacion}_{parametro}horario_{desde}_{hasta}.csv").write_bytes(crudo)

    serie: dict[str, dict] = {}
    for f in parsear(crudo, macro).filas:
        if not f["hora"]:
            continue
        hh = f["hora"]
        fecha = f["fecha"]
        if hh.startswith("24"):
            # La hora 2400 cierra el dia; pertenece a las 00:00 del dia siguiente.
            y, m, dd = (int(x) for x in fecha.split("-"))
            fecha = (date(y, m, dd) + timedelta(days=1)).isoformat()
            hh = "00:00"
        serie[f"{fecha}T{hh}"] = {
            "validado": f["validado"],
            "preliminar": f["preliminar"],
            "no_validado": f["no_validado"],
        }
    return serie


# --------------------------------------------------------------------------
def desplazar(marca: str, horas: int) -> str:
    from datetime import datetime

    t = datetime.fromisoformat(marca) + timedelta(hours=horas)
    return t.strftime("%Y-%m-%dT%H:%M")


def comparar(oaq: dict[str, float], sin: dict[str, dict], desfases=(-2, -1, 0, 1, 2)) -> dict:
    """Compara ambas series probando varios desfases horarios."""
    resultados = {}
    for k in desfases:
        pares = []
        for marca, v_oaq in oaq.items():
            ref = sin.get(desplazar(marca, k))
            if not ref:
                continue
            v_sin = ref["validado"]
            if v_sin is None:
                continue
            pares.append((marca, v_oaq, v_sin))
        if not pares:
            resultados[k] = {"pares": 0}
            continue
        difs = [a - b for _, a, b in pares]
        iguales = sum(1 for d in difs if abs(d) < 1e-9)
        resultados[k] = {
            "pares": len(pares),
            "identicos": iguales,
            "pct_identicos": round(100 * iguales / len(pares), 2),
            "dif_media": round(statistics.fmean(difs), 3),
            "dif_mediana": round(statistics.median(difs), 3),
            "dif_abs_media": round(statistics.fmean(abs(d) for d in difs), 3),
            "dif_min": round(min(difs), 2),
            "dif_max": round(max(difs), 2),
        }
    return resultados


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--openaq-id", type=int, required=True)
    p.add_argument("--region", required=True, help="codigo SINCA, ej. RM")
    p.add_argument("--estacion", required=True, help="codigo SINCA, ej. D14")
    p.add_argument("--desde", required=True, help="AAAAMMDD")
    p.add_argument("--hasta", required=True, help="AAAAMMDD")
    p.add_argument("--salida-json", type=Path)
    args = p.parse_args(argv)

    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "contraste_openaq_sinca.log", encoding="utf-8"),
                  logging.StreamHandler(sys.stderr)],
    )

    log.info("leyendo OpenAQ id=%s", args.openaq_id)
    oaq = leer_openaq(args.openaq_id, args.desde, args.hasta)
    log.info("  %s horas con pm25", len(oaq))

    log.info("leyendo SINCA %s/%s", args.region, args.estacion)
    try:
        sin = leer_sinca(args.region, args.estacion, args.desde, args.hasta)
    except SincaVacio as e:
        log.error("SINCA sin datos: %s", e)
        return 1
    log.info("  %s horas", len(sin))

    val = sum(1 for v in sin.values() if v["validado"] is not None)
    pre = sum(1 for v in sin.values() if v["preliminar"] is not None)
    nov = sum(1 for v in sin.values() if v["no_validado"] is not None)

    res = {
        "estacion_openaq": args.openaq_id,
        "estacion_sinca": f"{args.region}/{args.estacion}",
        "periodo": [args.desde, args.hasta],
        "horas_openaq": len(oaq),
        "horas_sinca": len(sin),
        "sinca_validados": val,
        "sinca_preliminares": pre,
        "sinca_no_validados": nov,
        "cobertura_relativa_openaq": round(len(oaq) / len(sin), 3) if sin else None,
        "por_desfase_horario": comparar(oaq, sin),
    }
    mejor = max(
        (k for k, v in res["por_desfase_horario"].items() if v.get("pares")),
        key=lambda k: res["por_desfase_horario"][k]["pct_identicos"],
        default=None,
    )
    res["mejor_desfase"] = mejor
    res["veredicto"] = (
        "IDENTICOS" if mejor is not None and res["por_desfase_horario"][mejor]["pct_identicos"] > 99
        else "DIFIEREN"
    )

    print(json.dumps(res, indent=2, ensure_ascii=False))
    if args.salida_json:
        asegurar(args.salida_json.parent)
        args.salida_json.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
