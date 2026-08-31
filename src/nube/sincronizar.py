"""Sincroniza data/ con el bucket S3 del proyecto.

Reglas que el script hace cumplir, no que confía en que se recuerden:

  * `interim/` NUNCA se sincroniza. Son intermedios regenerables (2,3 GB de
    .mdb extraídos en este proyecto). Subirlos gastaría la cuota sin aportar.
  * `raw/` se sube pero no se sobrescribe: si el objeto ya existe con el mismo
    tamaño, se omite. La zona cruda es inmutable.
  * Antes de subir se informa cuántos objetos y cuántos bytes se moverán, para
    poder contrastarlos con la cuota gratuita antes de gastarla.

Por defecto SIMULA. Hay que pasar --aplicar para que toque la red.

Uso
---
    python -m src.nube.sincronizar --bucket X subir --zona raw
    python -m src.nube.sincronizar --bucket X subir --zona raw --subcarpeta deis
    python -m src.nube.sincronizar --bucket X subir --zona raw --subcarpeta deis --aplicar
    python -m src.nube.sincronizar --bucket X bajar --zona raw --aplicar
    python -m src.nube.sincronizar --bucket X estado
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.nube import abrir_sesion  # noqa: E402
from src.rutas import DATA, LOGS, asegurar  # noqa: E402

log = logging.getLogger("s3-sync")

# interim NO está aquí a propósito: es regenerable y no viaja.
ZONAS = {"raw": DATA / "raw", "processed": DATA / "processed"}

# Precios de referencia de S3 Standard en us-east-1, para dar una magnitud, no
# una factura. Confírmalos en la consola.
#
# El almacenamiento es barato y no es lo que hay que vigilar: el proyecto entero
# cuesta centavos al mes. Lo que sí escala mal es el NÚMERO de objetos, porque
# cada petición se cobra por unidad y no por byte.
USD_GB_MES = 0.023
USD_POR_1000_PUT = 0.005

# A partir de aquí conviene consolidar antes de subir. Por debajo, el costo en
# peticiones es despreciable (10.000 PUT son 5 centavos).
OBJETOS_DEMASIADOS = 10_000


def humano(n: int) -> str:
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.1f} {u}" if u != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"


def locales(zona: str, subcarpeta: str | None = None) -> list[Path]:
    """Archivos de la zona, opcionalmente acotados a una subcarpeta.

    El filtro existe porque `raw/` mezcla fuentes de tamaños muy distintos: el
    .dta de CASEN pesa 1,7 GB y los NetCDF satelitales otros 99 MB. Subir «la
    zona» cuando lo que se quiere es una fuente mueve gigabytes por error, y en
    `raw/` no hay vuelta atrás: la política del bucket deniega DeleteObject.
    """
    base = ZONAS[zona]
    if subcarpeta:
        base = base / subcarpeta
    if not base.exists():
        return []
    return [p for p in sorted(base.rglob("*"))
            if p.is_file() and p.name not in (".gitkeep", ".mantener")]


def remotos(s3, bucket: str, zona: str) -> dict[str, int]:
    out: dict[str, int] = {}
    pag = s3.get_paginator("list_objects_v2")
    try:
        for page in pag.paginate(Bucket=bucket, Prefix=f"{zona}/"):
            for o in page.get("Contents", []):
                if o["Key"].endswith(".mantener"):
                    continue
                out[o["Key"]] = o["Size"]
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("NoSuchBucket", "404"):
            raise SystemExit(f"El bucket '{bucket}' no existe. ¿Ya corriste configurar_s3?") from e
        if code in ("AccessDenied", "403"):
            raise SystemExit(
                f"Sin permiso sobre '{bucket}'. Revisa que tus credenciales sean las del "
                f"proyecto y no otras. (403 aquí es permiso, no red.)") from e
        raise
    return out


def clave(zona: str, p: Path) -> str:
    return f"{zona}/{p.relative_to(ZONAS[zona]).as_posix()}"


def cmd_estado(s3, args) -> int:
    print(f"  bucket: s3://{args.bucket}\n")
    print(f"  {'zona':<12}{'local':>10}{'':>4}{'remoto':>10}{'':>4}"
          f"{'objetos loc.':>13}{'objetos rem.':>14}")
    for z in ZONAS:
        L = locales(z)
        R = remotos(s3, args.bucket, z)
        print(f"  {z:<12}{humano(sum(p.stat().st_size for p in L)):>10}"
              f"{'':>4}{humano(sum(R.values())):>10}{'':>4}{len(L):>13}{len(R):>14}")
    total_rem = sum(sum(remotos(s3, args.bucket, z).values()) for z in ZONAS)
    costo = total_rem / 1024 ** 3 * USD_GB_MES
    print(f"\n  almacenamiento estimado: {costo:.2f} USD/mes "
          f"({USD_GB_MES} USD por GB, referencia us-east-1)")
    print("  interim/ no se sincroniza: es regenerable.")
    return 0


def cmd_subir(s3, args) -> int:
    zona = args.zona
    sub = getattr(args, "subcarpeta", None)
    L = locales(zona, sub)
    if sub and not L:
        raise SystemExit(f"No hay archivos en {ZONAS[zona] / sub}. "
                         f"¿La subcarpeta existe y tiene ese nombre exacto?")
    R = remotos(s3, args.bucket, zona)

    pendientes = []
    omitidos = 0
    for p in L:
        k = clave(zona, p)
        if k in R and R[k] == p.stat().st_size:
            omitidos += 1          # ya está y pesa igual: la zona cruda no se reescribe
            continue
        pendientes.append((p, k))

    bytes_sub = sum(p.stat().st_size for p, _ in pendientes)
    ambito = f"zona {zona}/{sub}" if sub else f"zona {zona}"
    print(f"  {ambito}: {len(L)} archivos locales, {len(R)} remotos en {zona}/")
    print(f"  ya sincronizados : {omitidos}")
    print(f"  por subir        : {len(pendientes)} archivos, {humano(bytes_sub)}")
    if len(pendientes) > OBJETOS_DEMASIADOS:
        print(f"  AVISO: {len(pendientes)} objetos son ~"
              f"{len(pendientes) / 1000 * USD_POR_1000_PUT:.2f} USD solo en peticiones, "
              f"y bastantes horas de reloj. Con tantos archivos pequeños conviene "
              f"consolidar a Parquet antes de subir.")
    if not pendientes:
        print("  nada que hacer.")
        return 0
    if not args.aplicar:
        for p, k in pendientes[:10]:
            print(f"    [simulación] {p.name} -> s3://{args.bucket}/{k}")
        if len(pendientes) > 10:
            print(f"    … y {len(pendientes) - 10} más")
        print("\n  simulación. Añade --aplicar para subir de verdad.")
        return 0

    for i, (p, k) in enumerate(pendientes, 1):
        s3.upload_file(str(p), args.bucket, k)
        log.info("[%s/%s] %s -> %s (%s)", i, len(pendientes), p.name, k, humano(p.stat().st_size))
    print(f"  subidos {len(pendientes)} archivos.")
    return 0


def cmd_bajar(s3, args) -> int:
    zona = args.zona
    R = remotos(s3, args.bucket, zona)
    base = ZONAS[zona]

    pendientes = []
    for k, tam in sorted(R.items()):
        destino = base / Path(k[len(zona) + 1:])
        if destino.exists() and destino.stat().st_size == tam:
            continue
        pendientes.append((k, destino, tam))

    print(f"  zona {zona}: {len(R)} objetos remotos")
    total = humano(sum(t for _, _, t in pendientes))
    print(f"  por bajar    : {len(pendientes)} archivos, {total}")
    if not pendientes:
        print("  ya está todo al día.")
        return 0
    if not args.aplicar:
        for k, d, _t in pendientes[:10]:
            print(f"    [simulación] s3://{args.bucket}/{k} -> {d.relative_to(DATA.parent)}")
        if len(pendientes) > 10:
            print(f"    … y {len(pendientes) - 10} más")
        print("\n  simulación. Añade --aplicar para bajar de verdad.")
        return 0

    for i, (k, destino, _) in enumerate(pendientes, 1):
        asegurar(destino.parent)
        s3.download_file(args.bucket, k, str(destino))
        log.info("[%s/%s] %s -> %s", i, len(pendientes), k, destino.name)
    print(f"  bajados {len(pendientes)} archivos.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bucket", required=True)
    p.add_argument("--region", default="us-east-1")
    p.add_argument("--perfil", default=None,
                   help="perfil de ~/.aws/credentials; sin esto, el predeterminado")
    sub = p.add_subparsers(dest="cmd", required=True)

    def con_perfil(s):
        """Acepta --perfil también DESPUÉS del subcomando.

        Es donde se escribe por instinto, y de lo contrario argparse responde
        'unrecognized arguments'. SUPPRESS es lo que impide que el valor del
        parser padre quede pisado con None cuando no se pasa aquí.
        """
        s.add_argument("--perfil", default=argparse.SUPPRESS,
                       help="perfil de ~/.aws/credentials")
        return s

    con_perfil(sub.add_parser("estado")).set_defaults(fn=cmd_estado)
    for nombre, fn in (("subir", cmd_subir), ("bajar", cmd_bajar)):
        s = con_perfil(sub.add_parser(nombre))
        s.add_argument("--zona", choices=list(ZONAS), required=True)
        s.add_argument("--aplicar", action="store_true",
                       help="sin esto solo simula")
        if nombre == "subir":
            s.add_argument("--subcarpeta", default=None, metavar="NOMBRE",
                           help="sube solo esa subcarpeta de la zona (p. ej. deis). "
                                "Sin esto sube la zona entera, que en raw/ son varios GB")
        s.set_defaults(fn=fn)

    args = p.parse_args(argv)
    # La consola de Windows viene en cp1252 y rompe los acentos de los mensajes.
    # Se corrige en el flujo, no escribiendo el castellano sin tildes.
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "sincronizar_s3.log", encoding="utf-8"),
                  logging.StreamHandler(sys.stderr)])
    return args.fn(abrir_sesion(args.perfil).client("s3", region_name=args.region), args)


if __name__ == "__main__":
    raise SystemExit(main())
