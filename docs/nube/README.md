# Trabajo en equipo sobre AWS S3

Cómo compartir los datos del proyecto entre las cuatro personas del equipo sin
que cada una tenga que volver a descargar 573 MB del DEIS, y sin salirse de la
cuota gratuita.

## 1. Qué se sube y qué no

Esta es la decisión más importante y está tomada con los tamaños reales medidos:

| Zona | Contenido | Tamaño | ¿Va al bucket? |
|---|---|---|---|
| `raw/` | ZIP del DEIS, XLSX de establecimientos, muestras SINCA y OpenAQ | **553 MB** | **Sí** |
| `interim/` | `.mdb` extraídos de 2018-2019 | 2,3 GB | **No** — regenerable |
| `processed/` | Parquet de trabajo | ~380 MB estimados | **Sí** |

**Total previsto: menos de 1 GB**, pero el tamaño no es la restricción: en S3 un
GB cuesta unos 0,02 USD al mes. Los números están aquí para dimensionar el
trabajo, no para racionar espacio.

`interim/` queda fuera por una razón que no es el costo: son los Access
descomprimidos, derivados del ZIP y regenerables en un minuto. Compartir datos
derivados invita a tratarlos como fuente, y entonces nadie sabe de qué ZIP
salieron. Que cada quien los reconstruya en local es lo que mantiene al ZIP como
único origen. El script de sincronización directamente no ofrece esa zona.

### Por qué Parquet y no CSV

Medido sobre el año 2023 del DEIS (8,9 millones de filas):

| Formato | Tamaño |
|---|---|
| CSV descomprimido | 1.526 MB |
| ZIP original | 132,5 MB |
| **Parquet + zstd** | **66 MB** |

Parquet pesa **23 veces menos** que el CSV y además se lee por columnas, así que
quien solo necesite `fecha`, `IdCausa` y `Total` no descarga las 21 columnas.
Para un análisis por columnas esto no es un detalle: es la diferencia entre
trabajar cómodo y pelear con la RAM.

## 2. Estructura del bucket

Las mismas zonas que en local. Quien conoce el repositorio conoce el bucket:

```
s3://<tu-bucket>/
  raw/          # todos leen y suben; NADIE borra. Versiones sin caducidad
    Santiago/
    Talcahuano/
    Coyhaique/
  interim/      # se borra solo a los 30 días
  processed/    # tablas de trabajo, lectura y escritura para todos
```

Las tres ciudades están dentro de `raw/` por decisión del equipo: el análisis
trabaja sobre esas tres y no sobre el país. Queda anotado que esto se aparta de
la regla 2 de `CLAUDE.md` —que pide ingesta a escala nacional y filtro al final—
y que hay material que no cae en ninguna ciudad, como el archivo del DEIS por
servicio de salud, que va directamente en `raw/`.

Las cinco personas pueden **usar y alimentar las tres zonas**. La ingesta se
reparte —cada quien descarga unos años del DEIS y los sube—, así que negar la
escritura en `raw/` obligaría a que todo pasara por una sola persona.

Lo que nadie puede es **borrar en `raw/`**: la política IAM lo deniega
explícitamente, y un `Deny` gana sobre cualquier permiso. Con versionado
activado eso alcanza para que la zona cruda sea inmutable de hecho:

- Subir sobre una clave existente no pisa nada. Crea una versión nueva y la
  anterior sigue accesible.
- Las versiones de `raw/` **no caducan**. Las de `interim/` y `processed/` sí
  (30 y 90 días), pero `raw/` no aparece en ninguna regla de ciclo de vida, a
  propósito.
- Nadie puede borrar ni el objeto ni sus versiones.

Es la regla 3 del proyecto sostenida por la infraestructura y no por la memoria
de quien sube. Más débil que prohibir la escritura, y a cambio el equipo trabaja
sin cuello de botella. El precio: que dos personas suban el mismo archivo con
distinto contenido es posible, y solo se nota mirando las versiones.
`sincronizar` reduce el riesgo omitiendo lo que ya existe con el mismo tamaño.

### Este párrafo fue falso hasta el 26 de agosto de 2026

Lo de arriba describe lo que `configurar_s3.py` **declara**. Durante una
auditoría del bucket se descubrió que **no era lo que había desplegado**. La
política que el grupo tenía realmente era una versión anterior:

```
Allow  s3:DeleteObject         -> aire-urgencias-2026-pr/*
Deny   s3:DeleteObjectVersion  -> aire-urgencias-2026-pr/*
```

Es decir, cualquiera del equipo podía borrar en `raw/`. El versionado dejaba la
versión recuperable —el `Deny` sobre `DeleteObjectVersion` impedía destruirla—
pero el objeto **desaparecía de los listados**, y con él lo veían desaparecer el
ETL, Glue y Athena. Un dato borrado era indistinguible de un dato que nunca se
descargó, que es justo lo que la regla 5 prohíbe.

La causa: el script solo toca IAM cuando se le pasa `--usuarios`. Sin ese
argumento imprime `sin --usuarios: no se toca IAM` y sale, así que las
ejecuciones posteriores para reconfigurar el bucket nunca reaplicaron la
política.

Ya está corregido y **comprobado con el simulador de IAM sobre un usuario real
del grupo**, simulando claves de objeto y no de carpeta:

| Acción | Sobre | Resultado |
|---|---|---|
| `DeleteObject` | `raw/deis/algo.zip` | `explicitDeny` |
| `DeleteObjectVersion` | `raw/Santiago/algo.csv` | `explicitDeny` |
| `PutObject` | `raw/nuevo.csv` | `allowed` |
| `GetObject` | `raw/deis/algo.zip` | `allowed` |
| `DeleteObject` | `processed/…`, `interim/…` | `allowed` |

**Lección operativa:** una política declarada en el repositorio no es una
política vigente. Conviene volver a correr esa comprobación cada vez que alguien
toque `configurar_s3.py`, y no dar por hecho que el código y la cuenta dicen lo
mismo.

Efecto lateral de la reaplicación: la política vieja concedía
`s3:GetObjectTagging` y `s3:PutObjectTagging`, que la declarada no incluye. El
proyecto no usa etiquetas de objeto en ninguna parte, así que no se echa en
falta; queda anotado por si alguien las necesitara.

S3 no tiene carpetas de verdad — solo claves con `/`. Para que las tres zonas se
vean aunque estén vacías, el script escribe un marcador `.mantener` de cero
bytes en cada una. El ciclo de vida de `interim/` los excluye por tamaño; sin
esa exclusión la propia regla de limpieza haría desaparecer la carpeta a los 30
días.

De ahí se sigue algo práctico: **crear subcarpetas no requiere tocar la
política**. Los permisos se dan sobre patrones de clave (`<bucket>/*`,
`<bucket>/raw/*`), así que cualquier profundidad nueva queda cubierta al
nacer. Nadie tiene que conceder nada al añadir una ciudad, y tampoco se puede
restringir por ciudad sin reescribir la política: quien entra ve las tres.

Un aviso para quien verifique esto con el simulador de IAM: **no sabe evaluar
ARN terminados en `/`**. Devuelve `implicitDeny` para toda clave con barra
final, incluso cuando existe un `Deny` explícito que debería dispararse — se
comprueba pidiendo `DeleteObject` sobre `raw/loquesea/`, que `raw/*` cubre por
definición y aun así reporta que ninguna regla coincidió. Las mismas claves sin
la barra resuelven bien. Simular la clave del objeto, no la de la carpeta.

## 3. Puesta en marcha — lo hace una sola persona

Quien administre la cuenta AWS ejecuta esto una vez.

### 3.1 Una credencial de administración aparte

Crear el bucket y crear cuentas son cosas distintas y piden permisos distintos.
Una credencial acotada a S3 —lo normal para una aplicación— **no** puede
administrar IAM, y está bien que así sea: no hay que ampliarla para salir del
paso. Se crea una identidad de administración separada, y se borra al terminar
el proyecto.

No hacen falta claves de root en ningún momento. Root entra a la consola con
correo y contraseña; desde ahí:

1. *IAM → Usuarios → Crear usuario*, por ejemplo `aire-admin`.
2. Adjuntar `AdministratorAccess`.
3. *Credenciales de seguridad → Crear clave de acceso*, tipo «CLI».

Las claves de root son la única credencial de AWS que no se puede acotar ni
revocar sin comprometer la cuenta entera. Es la razón por la que este rodeo vale
la pena aunque parezca un paso de más.

### 3.2 Guardarla como perfil, sin pisar otras

Si la máquina ya tiene credenciales de otro proyecto, pegar las nuevas encima
rompe ese proyecto en silencio. Van con nombre propio, en
`~/.aws/credentials`:

```ini
[aire-admin]
aws_access_key_id = AKIA...
aws_secret_access_key = ...
```

Y todos los scripts aceptan `--perfil`:

```powershell
python -m src.nube.configurar_s3 --bucket <tu-bucket> --perfil aire-admin --simular
```

Sin `--perfil` se usa el predeterminado, que puede no ser el que crees. Por eso
el script **imprime siempre con qué identidad opera** antes de tocar nada:

```
INFO operando como: user/aire-admin
```

Míralo. Es la diferencia entre configurar tu bucket y configurar el de otro.

### 3.3 Simular primero

El nombre del bucket es **global en todo AWS**: si alguien ya lo usó, hay que
elegir otro. Conviene añadir algo propio al final.

```powershell
python -m src.nube.configurar_s3 --bucket aire-urgencias-2026-pr --simular
```

Esto no toca nada. Muestra qué haría.

### 3.4 Aplicar

Sin `--usuarios` deja el bucket listo y nada más. Es el arranque razonable si el
equipo todavía está decidiendo qué subir:

```powershell
python -m src.nube.configurar_s3 --bucket aire-urgencias-2026-pr --aplicar
```

Crea el bucket, lo cierra al público, activa versionado y cifrado, y crea las
tres zonas. Añadir a las personas después es volver a correr el mismo comando
con `--usuarios`: las operaciones son idempotentes, lo que ya existe no se
recrea.

```powershell
python -m src.nube.configurar_s3 --bucket aire-urgencias-2026-pr --aplicar `
    --usuarios nombre1,nombre2,nombre3
```

Esto da de alta a las tres personas restantes en un grupo con la política
mínima.

Las credenciales de cada integrante quedan en un JSON **fuera del repositorio**,
en la carpeta superior. Entrega cada bloque por separado y borra el archivo
cuando termines: **la clave secreta no se puede volver a consultar**. Si se
pierde, se rota y punto.

### 3.5 Subir los datos

```powershell
python -m src.nube.sincronizar --bucket aire-urgencias-2026-pr subir --zona raw
```

Sin `--aplicar` solo simula y te dice cuántos archivos y cuántos bytes moverá.
Míralo antes de gastar cuota. Cuando estés conforme:

```powershell
python -m src.nube.sincronizar --bucket aire-urgencias-2026-pr subir --zona raw --aplicar
```

## 4. Puesta en marcha — cada integrante

El equipo entra **por navegador**, como a una carpeta compartida. Sin repositorio,
sin Python y sin claves de acceso: los integrantes no tienen ninguna, y es
deliberado — una clave que se filtra funciona desde cualquier parte del mundo,
una contraseña de consola no basta por sí sola para lo mismo.

1. Abrir `https://<id-de-cuenta>.signin.aws.amazon.com/console`. Es la puerta de
   IAM; la pantalla normal de AWS pide correo, y ahí no funciona.
2. Nombre de usuario (`Noemi`, `Nicolas`, `Mika`, `Dante`) y la contraseña
   inicial que se entregó por privado.
3. AWS obliga a cambiarla en el primer ingreso. La nueva la elige cada quien y
   **nadie más la conoce**, tampoco quien administra.
4. Buscar «S3» arriba → el bucket del proyecto → `raw/` → la ciudad → *Cargar*.

Sobre las contraseñas: **un usuario IAM no tiene «olvidé mi contraseña»**. No hay
correo de recuperación. Si alguien la pierde, quien administra le genera otra
inicial con `--restablecer`, y el ciclo vuelve a empezar.

Quien además quiera trabajar con los scripts en local necesita el repositorio y
una clave de acceso propia, que se emite aparte. No es el camino previsto para el
equipo.

Para regenerar los Access de 2018-2019 en local, sin descargarlos de nadie:

```powershell
python -m src.ingesta.reconocer_deis perfil --desde 2018 --hasta 2019
```

## 5. Costos: qué vigilar de verdad

**El almacenamiento no es el problema.** En us-east-1, S3 Standard cuesta del
orden de 0,023 USD por GB al mes: el proyecto entero, aun subiendo los 8,3 GB
descomprimidos, ronda los 0,20 USD mensuales. Si la cuenta tiene créditos,
pasarse de los 5 GB del nivel gratuito no cambia nada. Trata las cifras como
orden de magnitud y confírmalas en la consola.

Lo que sí puede sorprender es otra cosa:

1. **Las peticiones se cobran por unidad, no por byte.** Del orden de 0,005 USD
   por cada 1.000 PUT y 0,0004 por cada 1.000 GET. Da igual con archivos
   grandes; importa muchísimo con archivos diminutos. Aquí es concreto: el
   archivo de OpenAQ tiene **16 millones de objetos**. Copiarlo tal cual son 16
   millones de GET más otros tantos PUT — decenas de dólares y muchas horas de
   reloj, para acabar con lo mismo que un Parquet consolidado ocupando una
   fracción. Se consolida primero, siempre.
2. **La transferencia de salida.** Los primeros 100 GB al mes son gratis; más
   allá se cobra por GB. Cuatro personas bajando un GB no se acercan ni de
   lejos. Un bucket público indexado por terceros, sí — por eso el script lo
   cierra, y no por pudor.
3. **Los créditos tienen su propia fecha de caducidad**, distinta de los 12
   meses del nivel gratuito. Está en *Facturación → Créditos*. Si el semestre se
   apoya en esta cuenta, conviene saber cuándo se acaba antes y no después.
4. **Activa igual la alerta de facturación**, en *Facturación → Preferencias*.
   No por miedo al gasto, sino porque es el único aviso de que algo quedó
   corriendo en bucle. Un script que reintenta sin límite no se nota en la
   factura; se nota en la alerta.

## 6. Una alternativa honesta

Para 553 MB y cuatro personas, S3 es cómodo pero **no es imprescindible**. Los
datos del DEIS y de SINCA son públicos y los scripts del repositorio los
descargan solos:

```powershell
python -m src.ingesta.reconocer_deis descargar --desde 2018 --hasta 2024
python -m src.ingesta.reconocer_deis establecimientos --desde 2018 --hasta 2024
```

Cada integrante puede reconstruir su propia zona cruda en unos minutos sin tocar
AWS. Lo que S3 sí aporta de verdad es:

- **Una sola versión de la zona procesada.** Que las cuatro personas trabajen
  sobre el mismo Parquet, no sobre cuatro copias que divergen.
- **Aprender la herramienta**, que para un capstone de Big Data cuenta como
  parte del trabajo.
- **Un respaldo** de lo descargado, por si una fuente cambia o desaparece — algo
  ya visto en este proyecto: el registro de datos.gob.cl apunta a un dominio que
  ya no resuelve.

Si el objetivo es sobre todo el segundo punto, adelante. Si fuera solo compartir
archivos, el propio repositorio y los scripts bastarían.

## 7. Reparto de trabajo sugerido

El reconocimiento dejó cuatro frentes bastante separables:

| Frente | Qué implica | Depende de |
|---|---|---|
| **Ingesta SINCA** | Completar el reconocimiento (meteorología, unidades, volumen) y bajar las 19 estaciones de MP2.5 de las tres ciudades | nada — se puede empezar ya |
| **Procesamiento DEIS** | Convertir los 7 años a Parquet tratando cada año como caso distinto (Access, sin cabecera, fechas Java, códigos migrados) | decisión diario/semanal |
| **Dimensiones y calidad** | Establecimientos por año, normalizar códigos antiguo↔vigente, empalme SAPU/SAR, reglas en `docs/calidad/` | ingesta DEIS |
| **Contexto internacional** | Percentil mundial con OpenAQ, insertando el dato de SINCA | nada — se puede empezar ya |

Dos de los cuatro frentes no dependen de nada y pueden arrancar de inmediato.

**Antes de repartir hay que cerrar una decisión: ¿resolución diaria o semanal?**
Condiciona el formato de todas las tablas intermedias, y por tanto el trabajo de
dos de los cuatro frentes. Está planteada en el informe de la etapa 1, §9.1.

## 8. La cuenta tiene fecha de término: 28 de diciembre de 2026

La consola lo dice así: el acceso gratuito termina en esa fecha **o** cuando se
agoten los créditos. El segundo caso no va a ocurrir — con ~0,02 USD al mes, los
100 USD no se gastan ni acercándose. Lo que llega es la fecha, con el crédito
casi intacto.

De ahí se sigue lo único importante de esta sección:

**El bucket no es un respaldo. Es un espacio de trabajo que caduca.** Un
respaldo que expira antes que el proyecto no respalda nada. Nada puede existir
únicamente en S3.

En este proyecto eso ya se cumple casi solo, y conviene mantenerlo así:

- `raw/` se regenera con los scripts del repositorio, desde las fuentes
  originales. Si el bucket desaparece, se vuelve a bajar.
- `interim/` es regenerable por definición, y ni siquiera se sincroniza.
- `processed/` es lo único que costaría rehacer. Debe reproducirse ejecutando el
  código del repositorio — si un Parquet no se puede regenerar desde `raw/` más
  el código versionado, ese Parquet es un problema con o sin fecha de caducidad.

**Antes del 28 de diciembre**, un solo comando deja todo en local:

```powershell
python -m src.nube.sincronizar --bucket <tu-bucket> bajar --zona processed --aplicar
python -m src.nube.sincronizar --bucket <tu-bucket> bajar --zona raw --aplicar
```

Conviene ponerlo en el calendario con dos semanas de margen, no para el día 27.

Si el trabajo tuviera que seguir más allá de esa fecha, pasar al plan de pago
cuesta centavos con este volumen — pero exige medio de pago y deja de haber red
de protección. Mientras el capstone termine antes de diciembre, no hace falta.
