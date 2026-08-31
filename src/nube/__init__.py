"""Utilidades comunes de los scripts de nube."""

from __future__ import annotations

import boto3
from botocore.exceptions import ProfileNotFound


def abrir_sesion(perfil: str | None) -> boto3.Session:
    """Sesión de boto3, con un error legible si el perfil no existe.

    Sin `perfil` se usa el predeterminado, que en una máquina con varios
    proyectos puede ser el de otro. Por eso conviene nombrarlo siempre.
    """
    if perfil is None:
        return boto3.Session()
    try:
        return boto3.Session(profile_name=perfil)
    except ProfileNotFound as e:
        disponibles = ", ".join(boto3.Session().available_profiles) or "ninguno"
        raise SystemExit(
            f"El perfil '{perfil}' no existe en ~/.aws/credentials.\n"
            f"  Disponibles: {disponibles}"
        ) from e
