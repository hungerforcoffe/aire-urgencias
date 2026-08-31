"""Reconocimiento de la encuesta CASEN (Observatorio Social, MDSF).

CASEN no mide aire. Aporta el ÚNICO dato del proyecto sobre la fuente de MP2.5
que está dentro de la vivienda: qué combustible usa cada hogar para
calefaccionar. Es el contexto que explica por qué las tres ciudades difieren.

Lo que este módulo NO hace, a propósito: tratar CASEN como serie temporal.
La encuesta no es anual y **no es representativa a nivel de comuna** — las
comunas no son dominio de estudio del diseño muestral. Todo lo que salga de aquí
es un descriptor regional y lento, no una covariable semanal.

Subcomandos
-----------
    disponibilidad  qué años responden, con tamaño real (HEAD, no descarga)
    descargar       baja un año a data/raw/ con cadena de validación
    variables       DETECTA las variables por su etiqueta, no por nombre supuesto
    perfil          distribución del combustible de calefacción por región

Uso
---
    python -m src.ingesta.reconocer_casen disponibilidad
    python -m src.ingesta.reconocer_casen descargar 2022
    python -m src.ingesta.reconocer_casen variables data/raw/casen/casen_2022.dta
    python -m src.ingesta.reconocer_casen perfil data/raw/casen/casen_2022.dta
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.rutas import LOGS, RAW, asegurar  # noqa: E402

BASE = "https://observatorio.ministeriodesarrollosocial.gob.cl/storage/docs/casen/"

# Solo rutas COMPROBADAS. Los nombres llevan espacios y van con %20: la variante
# con guiones bajos devuelve 404.
#
# Los demás años existen como encuesta, pero su ruta exacta no está verificada y
# aquí no se adivina. Un 404 de una URL inventada dice que la URL estaba mal, no
# que el año no se publique, y tratar ambas cosas igual es exactamente el error
# que el proyecto se prohíbe. Para añadir un año: sacar el enlace de la página
# del Observatorio, comprobarlo con `disponibilidad` y recién entonces ponerlo.
ARCHIVOS = {
    2022: "2022/Base%20de%20datos%20Casen%202022%20STATA.dta.zip",
}
SIN_RUTA_VERIFICADA = (2015, 2017, 2020, 2024)

COMPLEMENTO_COMUNA = {
    2022: "2022/Base%20de%20datos%20provincia%20y%20comuna%20Casen%202022%20STATA.dta.zip",
}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

# Detección por etiqueta, no por nombre. En 2022 la de calefacción es `v34b`,
# pero el nombre cambia entre años y suponerlo es la forma conocida de leer la
# columna equivocada sin enterarse (regla 6).
PATRON_ENERGIA = re.compile(r"calefac|combustible|le[ñn]a|energ[íi]a|cocinar|agua caliente", re.I)
PATRON_GEO = re.compile(r"\bcomuna\b|\bregi[óo]n\b|provinc|estrato|zona", re.I)

# Categoría que agrupa la combustión de biomasa sólida. El texto exacto varía
# entre años; se detecta por contenido.
PATRON_LENA = re.compile(r"le[ñn]a|carb[óo]n|pellet|astilla", re.I)

# Regiones donde viven las tres ciudades del estudio.
REGIONES_INTERES = {
    "Metropolitana": "Santiago",
    "Biob": "Talcahuano",
    "Ays": "Coyhaique",
}

log = logging.getLogger("casen")


def _head(url: str) -> dict:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    try:
        r = urllib.request.urlopen(req, timeout=30)  # noqa: S310
        return {"http": r.status,
                "bytes": int(r.headers.get("Content-Length", 0)),
                "tipo": r.headers.get("Content-Type")}
    except urllib.error.HTTPError as e:
        # 404 es "no publicado"; 403 detrás de CGNAT suele ser la IP, no el dato.
        clase = "BLOQUEADO (probable IP/CGNAT)" if e.code == 403 else "NO EXISTE"
        return {"http": e.code, "diagnostico": clase}
    except Exception as e:  # noqa: BLE001
        return {"http": None, "diagnostico": f"{type(e).__name__}: {e}"}


# --------------------------------------------------------------------------
def cmd_disponibilidad(args) -> dict:
    out = {"base": BASE, "anios": {}}
    for anio, ruta in ARCHIVOS.items():
        r = _head(BASE + ruta)
        if r.get("bytes"):
            r["megabytes"] = round(r["bytes"] / 1e6, 1)
        out["anios"][anio] = r
        log.info("%s -> HTTP %s (%s MB)", anio, r.get("http"), r.get("megabytes", "?"))
    out["complemento_comuna"] = {a: _head(BASE + u) for a, u in COMPLEMENTO_COMUNA.items()}
    out["anios_sin_ruta_verificada"] = list(SIN_RUTA_VERIFICADA)
    out["notas"] = [
        "Los años de 'anios_sin_ruta_verificada' existen como encuesta; lo que falta "
        "es su URL comprobada. Ausencia aquí NO significa ausencia en la fuente.",
        "2020 es 'Casen en Pandemia', con cuestionario reducido: comprobar que el "
        "módulo de vivienda exista antes de contarlo como año utilizable.",
    ]
    return out


# --------------------------------------------------------------------------
def _validar_dta(ruta: Path) -> dict:
    """Un fallo nunca puede parecer un éxito (regla 5)."""
    import pandas as pd  # noqa: PLC0415

    if ruta.stat().st_size == 0:
        return {"valido": False, "motivo": "archivo de 0 bytes"}
    try:
        lector = pd.io.stata.StataReader(ruta)
        etiquetas = lector.variable_labels()
    except Exception as e:  # noqa: BLE001
        return {"valido": False, "motivo": f"no abre como Stata: {type(e).__name__}: {e}"}
    if not etiquetas:
        return {"valido": False, "motivo": "sin variables"}
    return {"valido": True, "bytes": ruta.stat().st_size, "variables": len(etiquetas)}


def cmd_descargar(args) -> dict:
    if args.anio not in ARCHIVOS:
        raise SystemExit(f"Año {args.anio} no está en el catálogo: {sorted(ARCHIVOS)}")
    url = BASE + ARCHIVOS[args.anio]
    destino = RAW / "casen" / f"casen_{args.anio}.dta"
    asegurar(destino.parent)
    if destino.exists() and not args.forzar:
        return {"url": url, "destino": str(destino), "estado": "ya existe, no se sobrescribe"}

    zip_tmp = destino.with_suffix(".zip.parcial")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as r, zip_tmp.open("wb") as fh:  # noqa: S310
            while chunk := r.read(1 << 20):
                fh.write(chunk)
    except Exception as e:  # noqa: BLE001
        zip_tmp.unlink(missing_ok=True)
        return {"url": url, "estado": "fallo", "diagnostico": f"{type(e).__name__}: {e}"}

    if not zipfile.is_zipfile(zip_tmp):
        zip_tmp.replace(destino.with_suffix(".zip.rechazado"))
        return {"url": url, "estado": "rechazado", "motivo": "la respuesta no es un ZIP"}

    with zipfile.ZipFile(zip_tmp) as z:
        if z.testzip() is not None:
            zip_tmp.replace(destino.with_suffix(".zip.rechazado"))
            return {"url": url, "estado": "rechazado", "motivo": "ZIP corrupto"}
        # El ZIP trae basura AppleDouble de macOS: __MACOSX/._<nombre>.dta, de 0
        # bytes y con extensión .dta. Es la misma trampa que en SatPM2.5.
        miembros = [i for i in z.infolist()
                    if i.filename.lower().endswith(".dta")
                    and not Path(i.filename).name.startswith("._")
                    and not i.filename.startswith("__MACOSX/")]
        if not miembros:
            zip_tmp.replace(destino.with_suffix(".zip.rechazado"))
            return {"url": url, "estado": "rechazado", "motivo": "el ZIP no contiene ningún .dta"}
        miembro = max(miembros, key=lambda i: i.file_size)
        with z.open(miembro) as origen, destino.open("wb") as fh:
            while chunk := origen.read(1 << 20):
                fh.write(chunk)

    veredicto = _validar_dta(destino)
    if not veredicto["valido"]:
        destino.replace(destino.with_suffix(".dta.rechazado"))
        return {"url": url, "estado": "rechazado", "motivo": veredicto["motivo"]}

    bytes_zip = zip_tmp.stat().st_size
    zip_tmp.unlink(missing_ok=True)
    log.info("CASEN %s -> %s (%s variables)", args.anio, destino.name, veredicto["variables"])
    return {"url": url, "destino": str(destino), "estado": "ok",
            "miembro_zip": miembro.filename,
            "megabytes_zip": round(bytes_zip / 1e6, 1),
            "megabytes_dta": round(veredicto["bytes"] / 1e6, 1),
            "ratio_compresion": round(veredicto["bytes"] / bytes_zip, 1),
            **veredicto}


# --------------------------------------------------------------------------
def cmd_variables(args) -> dict:
    """Detecta las variables de energía y geografía por su ETIQUETA.

    No lee ni una fila: `StataReader` expone el diccionario de variables sin
    cargar el archivo, que descomprimido pasa de 1,7 GB.
    """
    import pandas as pd  # noqa: PLC0415

    ruta = Path(args.archivo)
    if not ruta.exists():
        raise SystemExit(f"No existe {ruta}. Bájalo antes con el subcomando 'descargar'.")
    etiquetas = pd.io.stata.StataReader(ruta).variable_labels()

    def coincidencias(patron):
        return {k: v for k, v in etiquetas.items() if patron.search(f"{k} {v}")}

    energia = coincidencias(PATRON_ENERGIA)
    calefaccion = {k: v for k, v in energia.items() if re.search(r"calefacc", str(v), re.I)}
    return {
        "archivo": str(ruta),
        "variables_totales": len(etiquetas),
        "candidatas_calefaccion": calefaccion,
        "otras_de_energia": {k: v for k, v in energia.items() if k not in calefaccion},
        "geograficas": coincidencias(PATRON_GEO),
        "aviso": (
            "si 'candidatas_calefaccion' trae más de una, elegir a mano y dejarlo "
            "escrito en docs/reconocimiento/casen.md antes de usarla"
        ),
    }


# --------------------------------------------------------------------------
def cmd_perfil(args) -> dict:
    """Distribución del combustible de calefacción, por región, ponderada."""
    import pandas as pd  # noqa: PLC0415

    ruta = Path(args.archivo)
    if not ruta.exists():
        raise SystemExit(f"No existe {ruta}. Bájalo antes con el subcomando 'descargar'.")

    etiquetas = pd.io.stata.StataReader(ruta).variable_labels()
    var = args.variable
    if var is None:
        cand = [k for k, v in etiquetas.items() if re.search(r"calefacc", str(v), re.I)]
        if len(cand) != 1:
            raise SystemExit(
                f"No hay una única variable de calefacción ({cand}). Pásala con --variable.")
        var = cand[0]
    if args.peso not in etiquetas:
        raise SystemExit(f"No existe la variable de peso '{args.peso}'.")

    df = pd.read_stata(ruta, columns=["region", var, args.peso], convert_categoricals=True)
    df["_lena"] = df[var].astype(str).apply(lambda s: bool(PATRON_LENA.search(s)))

    por_region = {}
    for reg in df["region"].astype(str).unique():
        ciudad = next((c for k, c in REGIONES_INTERES.items() if k in reg), None)
        if args.solo_interes and ciudad is None:
            continue
        sub = df[df["region"].astype(str) == reg]
        peso_total = float(sub[args.peso].sum())
        peso_lena = float(sub.loc[sub["_lena"], args.peso].sum())
        por_region[reg] = {
            "ciudad_del_estudio": ciudad,
            "n_muestral": int(len(sub)),
            "n_muestral_lena": int(sub["_lena"].sum()),
            "pct_personas_lena_ponderado": (
                round(100 * peso_lena / peso_total, 1) if peso_total else None),
        }

    return {
        "archivo": str(ruta),
        "variable_usada": var,
        "etiqueta": str(etiquetas[var]),
        "peso": args.peso,
        "unidad": "personas (la base es de personas; NO es proporción de hogares)",
        "categorias": {str(k): int(v) for k, v in df[var].value_counts(dropna=False).items()},
        "por_region": dict(sorted(por_region.items())),
        "advertencia": (
            "CASEN no es representativa a nivel de comuna: las comunas no son dominio "
            "de estudio. Estas cifras son regionales y así deben reportarse."
        ),
    }


# --------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--salida-json", type=Path, help="guarda el resultado como JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    def con_salida(s):
        """Acepta --salida-json también DESPUÉS del subcomando.

        Es donde se escribe por instinto, al final de la línea. SUPPRESS impide
        que el valor del parser padre quede pisado con None cuando no se pasa
        aquí. Mismo arreglo que en `src/nube/sincronizar.py`.
        """
        s.add_argument("--salida-json", type=Path, default=argparse.SUPPRESS,
                       help="guarda el resultado como JSON")
        return s

    con_salida(sub.add_parser("disponibilidad")).set_defaults(fn=cmd_disponibilidad)

    d = con_salida(sub.add_parser("descargar"))
    d.add_argument("anio", type=int, choices=sorted(ARCHIVOS))
    d.add_argument("--forzar", action="store_true", help="permite reescribir la zona cruda")
    d.set_defaults(fn=cmd_descargar)

    v = con_salida(sub.add_parser("variables"))
    v.add_argument("archivo")
    v.set_defaults(fn=cmd_variables)

    pf = con_salida(sub.add_parser("perfil"))
    pf.add_argument("archivo")
    pf.add_argument("--variable", help="por omisión se detecta por etiqueta")
    pf.add_argument("--peso", default="expr", help="factor de expansión regional")
    pf.add_argument("--solo-interes", action="store_true",
                    help="solo las regiones de las tres ciudades")
    pf.set_defaults(fn=cmd_perfil)

    args = p.parse_args(argv)

    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")

    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "reconocer_casen.log", encoding="utf-8"),
                  logging.StreamHandler(sys.stderr)],
    )

    res = args.fn(args)
    print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
    if args.salida_json:
        asegurar(args.salida_json.parent)
        args.salida_json.write_text(
            json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
