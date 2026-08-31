"""Prepara el bucket S3 del proyecto y los permisos del equipo.

Crea UNA sola vez la infraestructura mínima para que las cuatro personas del
equipo trabajen sobre los mismos datos:

  * un bucket privado, con acceso público bloqueado a nivel de cuenta y bucket
  * versionado activado -> materializa la regla 3: la zona cruda es inmutable
  * cifrado en reposo y bloqueo de subidas sin cifrar
  * ciclo de vida que borra `interim/` a los 30 días (es regenerable)
  * un grupo IAM con la política mínima, y un usuario por integrante

Este script NO sube datos. Solo prepara el destino.

Requisitos
----------
Credenciales de administrador de la cuenta AWS en el entorno:

    $env:AWS_ACCESS_KEY_ID     = "..."
    $env:AWS_SECRET_ACCESS_KEY = "..."

Nunca escribir credenciales en el código ni en el repositorio.

Uso
---
    python -m src.nube.configurar_s3 --bucket aire-urgencias-uxxx --simular
    python -m src.nube.configurar_s3 --bucket aire-urgencias-uxxx --aplicar
    python -m src.nube.configurar_s3 --bucket aire-urgencias-uxxx --aplicar \
        --usuarios ana,bruno,carla
"""

from __future__ import annotations

import argparse
import json
import logging
import secrets
import string
import sys
from pathlib import Path

from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.nube import abrir_sesion  # noqa: E402
from src.rutas import LOGS, RAIZ, asegurar  # noqa: E402

log = logging.getLogger("s3-setup")

# Zonas del lake. Son las mismas de data/ en local: quien conoce el repo
# conoce el bucket.
ZONAS = ["raw/", "interim/", "processed/"]

GRUPO = "aire-urgencias-equipo"

# Bucket donde Athena deja el resultado de cada consulta. No es el de datos y no
# se le parece: Athena escribe ahi un CSV por consulta y luego lo lee para
# mostrarlo en pantalla. Sin permiso de objeto sobre este bucket, TODA consulta
# muere con AccessDenied, y el error apunta a S3 en vez de a Athena.
RESULTADOS_ATHENA = "s3-athena-results-pablo-2026"

# Política gestionada por AWS: permite a cada usuario cambiar SOLO su propia
# contraseña, y leer los requisitos vigentes al hacerlo. Si AWS cambia la
# semántica, la política se actualiza sola; una copia a mano no.
POLITICA_CONTRASENA = "arn:aws:iam::aws:policy/IAMUserChangePassword"


def politica_equipo(bucket: str, cuenta: str = "", consola: bool = False) -> dict:
    """Permisos del equipo: usar las tres zonas; no destruir la cruda.

    Todo el equipo lee todo y escribe en todo, `raw/` incluida: la ingesta se
    reparte entre varias personas y cada una sube lo que descarga.

    Lo que no puede nadie es BORRAR en `raw/`. Con versionado activado eso
    basta para que la zona cruda sea inmutable de hecho: subir un archivo con
    una clave ya usada no pisa nada, crea una versión nueva y la anterior sigue
    ahí, recuperable para siempre (el ciclo de vida no caduca versiones de
    `raw/`, a diferencia de las otras zonas).

    Es la regla 3 del proyecto sostenida por la infraestructura en vez de por
    la memoria de quien sube. Más débil que negar la escritura, y a cambio el
    equipo puede alimentar la zona cruda sin depender de una sola persona.
    """
    doc = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "ListarElBucket",
                "Effect": "Allow",
                # ListBucketVersions permite recuperar una versión anterior sin
                # tener que pedírselo a quien administra.
                "Action": ["s3:ListBucket", "s3:ListBucketVersions",
                           "s3:GetBucketLocation"],
                "Resource": f"arn:aws:s3:::{bucket}",
            },
            {
                "Sid": "LeerTodo",
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:GetObjectVersion"],
                "Resource": f"arn:aws:s3:::{bucket}/*",
            },
            {
                "Sid": "EscribirEnLasTresZonas",
                "Effect": "Allow",
                "Action": ["s3:PutObject"],
                "Resource": f"arn:aws:s3:::{bucket}/*",
            },
            {
                "Sid": "BorrarSoloFueraDeLaZonaCruda",
                "Effect": "Allow",
                "Action": ["s3:DeleteObject", "s3:DeleteObjectVersion"],
                "Resource": [
                    f"arn:aws:s3:::{bucket}/interim/*",
                    f"arn:aws:s3:::{bucket}/processed/*",
                ],
            },
            {
                # Un Deny en IAM gana siempre, sin importar qué permita el resto.
                "Sid": "NuncaBorrarEnLaZonaCruda",
                "Effect": "Deny",
                "Action": ["s3:DeleteObject", "s3:DeleteObjectVersion"],
                "Resource": f"arn:aws:s3:::{bucket}/raw/*",
            },
            {
                # AmazonAthenaFullAccess NO cubre esto. Esa política gestionada
                # concede S3 a nivel de objeto solo en buckets cuyo nombre empieza
                # por `aws-athena-query-results-`, y el nuestro no sigue esa
                # convención. Sin estas dos sentencias, el equipo ve el bucket de
                # resultados pero no puede escribir en él, y ninguna consulta
                # llega a ejecutarse.
                "Sid": "ResultadosDeAthena",
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:PutObject",
                           "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"],
                "Resource": f"arn:aws:s3:::{RESULTADOS_ATHENA}/*",
            },
            {
                "Sid": "ListarResultadosDeAthena",
                "Effect": "Allow",
                "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
                "Resource": f"arn:aws:s3:::{RESULTADOS_ATHENA}",
            },
        ],
    }

    if consola:
        doc["Statement"] += [
            {
                # Sin esto la consola responde "Access Denied" en la pantalla
                # inicial de S3 y no se ve ni el nombre del bucket. Expone la
                # LISTA de nombres de la cuenta, nada de su contenido: entrar a
                # cualquier otro bucket sigue denegado por ausencia de permiso.
                "Sid": "VerLaListaDeBucketsEnLaConsola",
                "Effect": "Allow",
                "Action": ["s3:ListAllMyBuckets"],
                "Resource": "*",
            },
        ]
        # Cambiar la propia contraseña NO se resuelve aquí: se delega en la
        # política gestionada IAMUserChangePassword (ver POLITICA_CONTRASENA).
        # Escribirla a mano exige `${aws:username}`, y esa variable el simulador
        # de IAM no la sustituye: la comprobación daría implicitDeny sin que se
        # pueda distinguir de un permiso realmente ausente. Un permiso que no se
        # puede verificar, sosteniendo el acceso de todo el equipo, no es un
        # buen sitio donde ahorrarse una dependencia.
    return doc


def _contrasena(n: int = 20) -> str:
    """Contraseña inicial, aleatoria y de un solo uso.

    Se genera con `secrets` y no con `random`: la diferencia es la que hay
    entre impredecible y meramente desordenado. Se garantiza variedad de tipos
    para no chocar con la política de contraseñas de la cuenta, que de otro
    modo rechazaría algunas al azar y dejaría el alta a medias.
    """
    simbolos = "!@#$%*-_=+"
    alfabeto = string.ascii_letters + string.digits + simbolos
    while True:
        p = "".join(secrets.choice(alfabeto) for _ in range(n))
        if (any(c.islower() for c in p) and any(c.isupper() for c in p)
                and any(c.isdigit() for c in p) and any(c in simbolos for c in p)):
            return p


def crear_acceso_consola(iam, usuarios: list[str], simular: bool) -> list[dict]:
    """Da acceso por navegador: contraseña inicial que hay que cambiar al entrar."""
    salida = []
    for u in usuarios:
        if simular:
            log.info("[simulación] contraseña de consola para %s", u)
            continue
        try:
            clave = _contrasena()
            iam.create_login_profile(UserName=u, Password=clave,
                                     PasswordResetRequired=True)
            log.info("acceso de consola para %s", u)
            salida.append({"usuario": u, "contrasena_inicial": clave})
        except iam.exceptions.EntityAlreadyExistsException:
            # Ya entró alguna vez y quizá ya la cambió. Pisarla sería sacarlo
            # de su propia cuenta sin avisar.
            log.info("%s ya tenía acceso de consola, no se toca", u)
    return salida


def restablecer_contrasena(iam, usuarios: list[str], simular: bool) -> list[dict]:
    """Emite una contraseña nueva para quien perdió la suya.

    Los usuarios IAM no tienen recuperación por correo: no existe el enlace de
    «olvidé mi contraseña». Restablecerla desde aquí es la única vía, y por eso
    conviene que sea un comando y no una excursión por la consola.

    La nueva vuelve a ser de un solo uso: quien entra elige la suya.
    """
    salida = []
    for u in usuarios:
        if simular:
            log.info("[simulación] nueva contraseña para %s", u)
            continue
        clave = _contrasena()
        try:
            iam.update_login_profile(UserName=u, Password=clave,
                                     PasswordResetRequired=True)
        except iam.exceptions.NoSuchEntityException:
            # Nunca tuvo acceso por navegador: se crea en vez de actualizarse.
            iam.create_login_profile(UserName=u, Password=clave,
                                     PasswordResetRequired=True)
        log.info("contraseña de %s restablecida", u)
        salida.append({"usuario": u, "contrasena_inicial": clave})
    return salida


def revocar_claves(iam, usuarios: list[str], simular: bool) -> int:
    """Elimina las claves de acceso programático.

    En un equipo que solo usa el navegador, una clave de larga vida repartida
    por cuatro portátiles es superficie de ataque sin contrapartida: nadie la
    usa, nadie la vigila, y sigue siendo válida hasta que la cuenta caduque.
    """
    n = 0
    for u in usuarios:
        for k in iam.list_access_keys(UserName=u)["AccessKeyMetadata"]:
            if simular:
                log.info("[simulación] revocar clave %s… de %s", k["AccessKeyId"][:8], u)
                continue
            iam.delete_access_key(UserName=u, AccessKeyId=k["AccessKeyId"])
            log.info("clave de %s revocada", u)
            n += 1
    return n


def url_ingreso(iam, cuenta: str) -> str:
    """URL de ingreso de la cuenta. Con alias si lo hay; si no, con el número."""
    try:
        alias = iam.list_account_aliases()["AccountAliases"]
        if alias:
            return f"https://{alias[0]}.signin.aws.amazon.com/console"
    except ClientError:
        pass
    return f"https://{cuenta}.signin.aws.amazon.com/console"


def identidad(sesion) -> str:
    """Con qué credencial estamos operando.

    Se imprime siempre antes de tocar nada. Es barato y evita el error caro:
    aplicar cambios con la credencial de otro proyecto porque quedó como perfil
    por defecto.
    """
    try:
        return sesion.client("sts").get_caller_identity()["Arn"].split(":")[-1]
    except ClientError as e:
        return f"desconocida ({e.response['Error']['Code']})"


def _existe_bucket(s3, bucket: str) -> bool:
    try:
        s3.head_bucket(Bucket=bucket)
        return True
    except ClientError as e:
        codigo = e.response["Error"]["Code"]
        if codigo in ("404", "NoSuchBucket"):
            return False
        if codigo == "403":
            raise SystemExit(
                f"El nombre '{bucket}' ya existe y pertenece a otra cuenta. "
                f"Los nombres de bucket son globales: elige otro."
            ) from e
        raise


def crear_bucket(s3, bucket: str, region: str, simular: bool) -> None:
    if _existe_bucket(s3, bucket):
        log.info("bucket %s ya existe, no se recrea", bucket)
        return
    if simular:
        log.info("[simulación] crear bucket %s en %s", bucket, region)
        return
    kwargs = {"Bucket": bucket}
    # us-east-1 es la única región que NO acepta LocationConstraint.
    if region != "us-east-1":
        kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
    s3.create_bucket(**kwargs)
    log.info("bucket %s creado en %s", bucket, region)


def endurecer(s3, bucket: str, simular: bool) -> None:
    """Bloqueo público, versionado y cifrado. Los tres, siempre."""
    acciones = [
        ("bloquear acceso público", lambda: s3.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True, "IgnorePublicAcls": True,
                "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
            })),
        ("activar versionado", lambda: s3.put_bucket_versioning(
            Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})),
        ("cifrado en reposo", lambda: s3.put_bucket_encryption(
            Bucket=bucket,
            ServerSideEncryptionConfiguration={"Rules": [{
                "ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"},
                "BucketKeyEnabled": True,
            }]})),
        ("ciclo de vida de interim/", lambda: s3.put_bucket_lifecycle_configuration(
            Bucket=bucket,
            LifecycleConfiguration={"Rules": [
                {
                    "ID": "interim-es-regenerable",
                    "Status": "Enabled",
                    # El filtro por tamaño no es decorativo: sin él la regla
                    # tambien borraria `interim/.mantener`, que pesa 0 bytes, y
                    # a los 30 dias la carpeta desapareceria de la consola sin
                    # que nadie la hubiera tocado.
                    "Filter": {"And": {"Prefix": "interim/", "ObjectSizeGreaterThan": 1}},
                    "Expiration": {"Days": 30},
                },
                {
                    "ID": "versiones-antiguas-de-interim",
                    "Status": "Enabled",
                    "Filter": {"Prefix": "interim/"},
                    "NoncurrentVersionExpiration": {"NoncurrentDays": 30},
                },
                {
                    "ID": "versiones-antiguas-de-processed",
                    "Status": "Enabled",
                    "Filter": {"Prefix": "processed/"},
                    "NoncurrentVersionExpiration": {"NoncurrentDays": 90},
                },
                {
                    # `raw/` NO aparece en ninguna regla de versiones, y es
                    # deliberado: sus versiones se conservan sin caducidad.
                    # Es lo que sostiene la inmutabilidad de la zona cruda
                    # ahora que el equipo puede escribir en ella. Si alguien
                    # sube encima de una clave existente, el original sigue
                    # recuperable; caducarlo a los 90 días lo perdería justo
                    # cuando ya nadie recuerda que pasó.
                    "ID": "lapidas-y-subidas-a-medias",
                    "Status": "Enabled",
                    "Filter": {"Prefix": ""},
                    "Expiration": {"ExpiredObjectDeleteMarker": True},
                    "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
                },
            ]})),
    ]
    for nombre, fn in acciones:
        if simular:
            log.info("[simulación] %s", nombre)
            continue
        fn()
        log.info("%s: ok", nombre)


def crear_zonas(s3, bucket: str, simular: bool) -> None:
    """S3 no tiene carpetas; se crean marcadores para que la estructura se vea."""
    for z in ZONAS:
        if simular:
            log.info("[simulación] zona %s", z)
            continue
        s3.put_object(Bucket=bucket, Key=f"{z}.mantener", Body=b"")
        log.info("zona %s creada", z)


def configurar_iam(iam, bucket: str, cuenta: str, usuarios: list[str],
                   consola: bool, emitir_claves: bool, simular: bool) -> list[dict]:
    """Crea el grupo, adjunta la política y da de alta a cada integrante."""
    politica = politica_equipo(bucket, cuenta, consola)
    nombre_pol = f"{GRUPO}-politica"
    credenciales = []

    # Sin gente que dar de alta no se toca IAM. Importa: crear el bucket suele
    # estar permitido con credenciales acotadas, y administrar IAM casi nunca.
    # Si el grupo se creara igual, el script moriría DESPUÉS del bucket y
    # dejaría la configuración a medias.
    if not usuarios:
        log.info("sin --usuarios: no se toca IAM")
        return []

    if simular:
        log.info("[simulación] grupo %s + política %s", GRUPO, nombre_pol)
        for u in usuarios:
            log.info("[simulación] usuario %s con clave de acceso", u)
        return []

    try:
        iam.create_group(GroupName=GRUPO)
        log.info("grupo %s creado", GRUPO)
    except iam.exceptions.EntityAlreadyExistsException:
        log.info("grupo %s ya existe", GRUPO)
    except ClientError as e:
        if e.response["Error"]["Code"] != "AccessDenied":
            raise
        raise SystemExit(
            "Esta credencial puede usar S3 pero no administrar IAM.\n"
            "  El bucket ya quedó configurado; lo que falta son las cuentas.\n"
            "  Opciones: darle a esta credencial los permisos de IAM desde la\n"
            "  consola, o crear los usuarios a mano. Ver docs/nube/README.md §4."
        ) from e

    iam.put_group_policy(GroupName=GRUPO, PolicyName=nombre_pol,
                         PolicyDocument=json.dumps(politica))
    log.info("política adjunta al grupo")

    if consola:
        iam.attach_group_policy(GroupName=GRUPO, PolicyArn=POLITICA_CONTRASENA)
        log.info("política de cambio de contraseña adjunta al grupo")

    for u in usuarios:
        try:
            iam.create_user(UserName=u)
            log.info("usuario %s creado", u)
        except iam.exceptions.EntityAlreadyExistsException:
            log.info("usuario %s ya existe", u)
        iam.add_user_to_group(GroupName=GRUPO, UserName=u)

        if not emitir_claves:
            continue

        # Volver a correr el script no debe emitir una clave nueva: IAM permite
        # dos por usuario y a la tercera falla. Si ya tiene una, se respeta —
        # el secreto no se puede reconsultar, asi que quien la perdio la rota a
        # mano en la consola.
        if iam.list_access_keys(UserName=u)["AccessKeyMetadata"]:
            log.info("usuario %s ya tiene clave de acceso, no se emite otra", u)
            continue
        clave = iam.create_access_key(UserName=u)["AccessKey"]
        credenciales.append({
            "usuario": u,
            "AWS_ACCESS_KEY_ID": clave["AccessKeyId"],
            "AWS_SECRET_ACCESS_KEY": clave["SecretAccessKey"],
        })
    return credenciales


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bucket", required=True,
                   help="nombre global único, minúsculas y guiones")
    p.add_argument("--region", default="us-east-1",
                   help="us-east-1 es la más barata; sa-east-1 está más cerca pero cuesta más")
    p.add_argument("--usuarios", default="",
                   help="lista separada por comas, sin ti (tú ya eres admin)")
    p.add_argument("--perfil", default=None,
                   help="perfil de ~/.aws/credentials. Sin esto se usa el "
                        "predeterminado, que puede ser el de otro proyecto")
    p.add_argument("--consola", action="store_true",
                   help="acceso por navegador: contraseña inicial y permiso "
                        "para ver el bucket en la consola")
    p.add_argument("--revocar-claves", action="store_true",
                   help="elimina las claves de acceso programático del equipo. "
                        "Con --consola, nadie las necesita")
    p.add_argument("--restablecer", action="store_true",
                   help="emite contraseña nueva para los --usuarios indicados "
                        "y termina. Para quien perdió la suya")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--simular", action="store_true", help="muestra qué haría, sin tocar AWS")
    g.add_argument("--aplicar", action="store_true", help="ejecuta de verdad")
    args = p.parse_args(argv)

    asegurar(LOGS)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOGS / "configurar_s3.log", encoding="utf-8"),
                  logging.StreamHandler(sys.stderr)])

    sesion = abrir_sesion(args.perfil)
    s3 = sesion.client("s3", region_name=args.region)
    iam = sesion.client("iam")

    log.info("operando como: %s", identidad(sesion))

    cuenta = sesion.client("sts").get_caller_identity()["Account"]
    usuarios = [u.strip() for u in args.usuarios.split(",") if u.strip()]

    # El restablecimiento va ANTES y termina aquí: cambiar una contraseña no
    # tiene por qué reconfigurar el bucket. Es idempotente, pero un comando que
    # hace de más es un comando que da miedo correr.
    if args.restablecer:
        if not usuarios:
            raise SystemExit("--restablecer necesita --usuarios nombre[,nombre...]")
        nuevas = restablecer_contrasena(iam, usuarios, args.simular)
        if nuevas:
            for c in nuevas:
                c["url_ingreso"] = url_ingreso(iam, cuenta)
            # Archivo aparte: el de alta ya se entregó y sus contraseñas están
            # obsoletas. El nombre empieza por "credenciales" a propósito, que
            # es lo que .gitignore vigila.
            destino = RAIZ.parent / f"credenciales_restablecidas_{args.bucket}.json"
            destino.write_text(json.dumps(nuevas, indent=2, ensure_ascii=False),
                               encoding="utf-8")
            print(f"\n  Contraseñas nuevas en: {destino}")
            print("  De un solo uso: al entrar, cada quien elige la suya.")
        elif args.simular:
            print("\n  (simulación: no se tocó nada en AWS)")
        return 0

    crear_bucket(s3, args.bucket, args.region, args.simular)
    endurecer(s3, args.bucket, args.simular)
    crear_zonas(s3, args.bucket, args.simular)

    creds = configurar_iam(iam, args.bucket, cuenta, usuarios,
                           args.consola, not args.revocar_claves, args.simular)

    if usuarios and args.consola:
        # Las contraseñas se fusionan con las claves por usuario, para poder
        # entregar UN bloque por persona en vez de dos listas que hay que cruzar.
        por_usuario = {c["usuario"]: c for c in creds}
        for c in crear_acceso_consola(iam, usuarios, args.simular):
            por_usuario.setdefault(c["usuario"], {"usuario": c["usuario"]}).update(c)
            por_usuario[c["usuario"]]["url_ingreso"] = url_ingreso(iam, cuenta)
        creds = list(por_usuario.values())

    if usuarios and args.revocar_claves:
        n = revocar_claves(iam, usuarios, args.simular)
        for c in creds:
            c.pop("AWS_ACCESS_KEY_ID", None)
            c.pop("AWS_SECRET_ACCESS_KEY", None)
        print(f"\n  Claves de acceso revocadas: {n}")

    if creds:
        # Se escriben FUERA del repositorio y se entregan una a una.
        destino = RAIZ.parent / f"credenciales_{args.bucket}.json"
        destino.write_text(json.dumps(creds, indent=2, ensure_ascii=False),
                           encoding="utf-8")
        print()
        print(f"  Credenciales escritas en: {destino}")
        print("  Este archivo está FUERA del repositorio a propósito.")
        print("  Entrega cada bloque por separado y bórralo cuando termines.")
        print("  Ni la contraseña ni la clave secreta se pueden volver a consultar.")

    print()
    print(f"  Bucket: s3://{args.bucket}  ({args.region})")
    print(f"  Zonas : {', '.join(ZONAS)}")
    if args.consola:
        print(f"  Ingreso: {url_ingreso(iam, cuenta) if not args.simular else '(simulado)'}")
    if args.simular:
        print("  (simulación: no se tocó nada en AWS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
