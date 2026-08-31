"""Generación del sitio estático que se publica en GitHub Pages.

El sitio vive en `sitio/` y no consulta Athena: lee archivos JSON que este
paquete escribe. La razón es que GitHub Pages sirve archivos y nada más — no
ejecuta Python, no abre conexiones a AWS y no puede guardar un secreto.
Cualquier credencial que llegara al sitio quedaría publicada.
"""
