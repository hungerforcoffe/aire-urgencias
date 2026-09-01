const stack = [
  { icono: "py", nombre: "Python 3.12", desc: "Ingesta, limpieza, consultas a Athena y exportación de JSON.", cat: "procesamiento" },
  { icono: "AWS", nombre: "Amazon Athena + S3", desc: "74 M filas en Parquet. Consultas SQL sobre datos crudos inmutables.", cat: "almacenamiento" },
  { icono: "🗺", nombre: "Leaflet 1.9", desc: "Mapa interactivo de estaciones sobre teselas OSM / CARTO.", cat: "frontend" },
  { icono: "JS", nombre: "JavaScript vanilla", desc: "Sin framework. SVG dinámico para series temporales y rosas de viento.", cat: "frontend" },
  { icono: "🌤", nombre: "Open-Meteo", desc: "Viento actual y reanálisis ERA5. Sin llave, CORS abierto.", cat: "API" },
  { icono: "gh", nombre: "GitHub Pages", desc: "Archivos estáticos. Sin servidor, sin secretos expuestos.", cat: "despliegue" },
];

const catColor: Record<string, string> = {
  procesamiento: "#eff6ff",
  almacenamiento: "#eff6ff",
  frontend: "#f0fdf4",
  API: "#fef9c3",
  despliegue: "#f5f3ff",
};

const reglas = [
  { titulo: "Asociación, nunca causalidad.", texto: "Ningún texto, variable o gráfico afirma que la contaminación causa consultas. Es un estudio ecológico observacional." },
  { titulo: "Acotar al final, no al principio.", texto: "El filtro a tres ciudades ocurre en la última etapa; si se filtrara en la ingesta, el proyecto dejaría de ser Big Data." },
  { titulo: "Nunca sobrescribir la zona cruda.", texto: "Los archivos descargados son inmutables y todo reproceso parte de ahí." },
  { titulo: "Toda decisión de limpieza se documenta", texto: "con su umbral y su justificación." },
  { titulo: "Un fallo nunca puede parecer un éxito.", texto: "El exportador valida cada consulta: si vuelve vacía o con columnas en nulo, aborta y deja intactos los archivos anteriores." },
];

const fuentes = [
  { nombre: "SINCA (MMA)", que: "MP2.5 horario y meteorología, 16 estaciones", como: "descarga por estación y año" },
  { nombre: "DEIS (MINSAL)", que: "urgencias respiratorias por establecimiento, causa y día", como: "descarga de archivos" },
  { nombre: "INE", que: "proyecciones de población comunal, denominador de las tasas", como: "descarga de archivos" },
  { nombre: "CASEN", que: "porcentaje de hogares que calefaccionan con leña", como: "microdatos públicos" },
  { nombre: "Open-Meteo", que: "viento y temperatura actuales; reanálisis ERA5 para rellenar", como: "API, sin llave" },
];

const r2 = [
  { ciudad: "Santiago (mediana 10)", modelo: "0,533", vecinas: "0,750", veredicto: "el modelo pierde en las diez" },
  { ciudad: "Talcahuano", modelo: "0,326", vecinas: "0,403", veredicto: "también pierde" },
  { ciudad: "Las Condes", modelo: "−0,010", vecinas: "−0,091", veredicto: "impredecible por cualquiera" },
];

function Seccion({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: 36 }}>
      <h2 style={{
        fontFamily: "var(--serif)", fontSize: "1.25rem", fontWeight: 600,
        color: "var(--navy)", marginBottom: 14, paddingBottom: 10,
        borderBottom: "1px solid var(--borde)",
      }}>
        {titulo}
      </h2>
      {children}
    </section>
  );
}

function Sub({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <h3 style={{ fontFamily: "var(--serif)", fontSize: "1rem", fontWeight: 600, color: "var(--azul)", marginBottom: 8 }}>
        {titulo}
      </h3>
      {children}
    </div>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return <p style={{ fontSize: ".88rem", color: "var(--texto-2)", lineHeight: 1.72, marginBottom: 12 }}>{children}</p>;
}

export default function PaginaMetodologia() {
  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "calc(100vh - 52px)" }}>

      {/* Hero */}
      <div style={{ background: "var(--navy)", color: "#fff", padding: "28px 24px 24px" }}>
        <div style={{ maxWidth: 800, margin: "0 auto" }}>
          <div style={{ fontFamily: "var(--mono)", fontSize: ".66rem", textTransform: "uppercase", letterSpacing: ".1em", color: "var(--celeste)", marginBottom: 8 }}>
            Reproducibilidad · Transparencia · Trazabilidad
          </div>
          <h1 style={{ fontFamily: "var(--serif)", fontSize: "1.6rem", fontWeight: 700, lineHeight: 1.2, marginBottom: 8 }}>
            Metodología y Stack
          </h1>
          <p style={{ fontSize: ".88rem", color: "rgba(255,255,255,0.6)", maxWidth: 540, lineHeight: 1.6, margin: 0 }}>
            De dónde sale cada número, qué se consulta en vivo, qué reglas se aplican antes
            de mostrar una cifra y qué queda fuera del alcance a propósito.
          </p>
        </div>
      </div>

      <div style={{ flex: 1, background: "var(--fondo)", padding: "0 20px 48px" }}>
        <div style={{ maxWidth: 800, margin: "0 auto", paddingTop: 36 }}>

          {/* Stack */}
          <Seccion titulo="Stack del proyecto">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 12, marginBottom: 8 }}>
              {stack.map((s, i) => (
                <div key={i} style={{
                  background: "var(--panel)", border: "1px solid var(--borde)",
                  borderRadius: 12, padding: "16px 18px", boxShadow: "var(--sombra)",
                  display: "flex", flexDirection: "column", gap: 6,
                  transition: "box-shadow .15s, border-color .15s",
                }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: 8,
                    background: "var(--fondo-alt)", border: "1.5px dashed var(--borde-f)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: ".7rem", fontFamily: "var(--mono)", color: "var(--texto-3)",
                    marginBottom: 2, flexShrink: 0,
                  }}>
                    {s.icono}
                  </div>
                  <div style={{ fontFamily: "var(--mono)", fontSize: ".78rem", fontWeight: 500, color: "var(--azul-medio)" }}>
                    {s.nombre}
                  </div>
                  <div style={{ fontSize: ".78rem", color: "var(--texto-2)", lineHeight: 1.5 }}>
                    {s.desc}
                  </div>
                  <span style={{
                    alignSelf: "flex-start", marginTop: 4,
                    fontFamily: "var(--mono)", fontSize: ".6rem", textTransform: "uppercase",
                    letterSpacing: ".07em", padding: "2px 8px", borderRadius: 99,
                    border: "1px solid var(--celeste-c)", background: "#eff6ff",
                    color: "var(--azul-medio)",
                  }}>
                    {s.cat}
                  </span>
                </div>
              ))}
            </div>
          </Seccion>

          {/* Fuentes */}
          <Seccion titulo="Las fuentes de datos">
            <div style={{ overflowX: "auto", borderRadius: 8, marginBottom: 14 }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: ".85rem" }}>
                <thead>
                  <tr>
                    {["Fuente", "Qué aporta", "Cómo llega"].map((h) => (
                      <th key={h} style={{
                        background: "var(--navy)", color: "rgba(255,255,255,0.8)",
                        fontFamily: "var(--mono)", fontSize: ".64rem", textTransform: "uppercase",
                        letterSpacing: ".06em", padding: "10px 14px", textAlign: "left", whiteSpace: "nowrap",
                      }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {fuentes.map((f, i) => (
                    <tr key={i}>
                      <td style={{ padding: "9px 14px", borderBottom: "1px solid var(--borde)", background: i % 2 ? "var(--fondo-alt)" : "var(--panel)", fontFamily: "var(--mono)", fontSize: ".76rem", color: "var(--azul-medio)", whiteSpace: "nowrap" }}>
                        {f.nombre}
                      </td>
                      <td style={{ padding: "9px 14px", borderBottom: "1px solid var(--borde)", background: i % 2 ? "var(--fondo-alt)" : "var(--panel)", color: "var(--texto-2)", verticalAlign: "top" }}>
                        {f.que}
                      </td>
                      <td style={{ padding: "9px 14px", borderBottom: "1px solid var(--borde)", background: i % 2 ? "var(--fondo-alt)" : "var(--panel)", color: "var(--texto-2)", whiteSpace: "nowrap" }}>
                        {f.como}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <P>
              <strong style={{ color: "var(--texto)" }}>SINCA es la única fuente de aire para Chile en este proyecto.</strong>{" "}
              OpenAQ es un agregador que cosecha los datos chilenos <em>desde</em> SINCA: usarlo
              para MP2.5 chileno sería contar la misma medición dos veces.
            </P>
          </Seccion>

          {/* APIs */}
          <Seccion titulo="Los datos y las APIs">
            <Sub titulo="Lo que viene de la base del proyecto">
              <P>
                La base vive en <strong style={{ color: "var(--texto)" }}>Amazon Athena</strong> sobre
                archivos Parquet en S3: 11 tablas y unos 74 millones de filas. Un script en Python
                corre las consultas y deja los agregados en archivos JSON:
              </P>
              <pre style={{ background: "var(--navy)", borderRadius: 10, padding: "16px 18px", overflowX: "auto", marginBottom: 14, border: "1px solid rgba(255,255,255,0.05)" }}>
                <code style={{ fontFamily: "var(--mono)", fontSize: ".78rem", color: "#93c5fd", lineHeight: 1.6 }}>
                  {"python -m src.sitio.exportar"}
                </code>
              </pre>
              <P>
                GitHub Pages sirve archivos y nada más. Lo que se publica son{" "}
                <strong style={{ color: "var(--texto)" }}>agregados</strong> —medias mensuales por
                estación, medianas por sector de viento—, unos 900 kB en total. Ningún registro
                individual.
              </P>
            </Sub>
            <Sub titulo="Lo que se consulta en vivo">
              <P>
                Desde el navegador solo se puede llamar a una API que no exija llave y que
                permita CORS. <strong style={{ color: "var(--texto)" }}>Open-Meteo</strong> cumple las dos.
              </P>
              <ul style={{ paddingLeft: 20, marginBottom: 12 }}>
                {[
                  "Viento y temperatura actuales en cada estación, para leer la rosa hoy.",
                  "Reanálisis ERA5: la red meteorológica de Santiago se apagó el 8 de mayo de 2025 y la estación de reemplazo empezó el 19 de agosto. 81.216 de las 90.029 horas-estación de MP2.5 de Santiago no tienen viento medido.",
                ].map((li, i) => (
                  <li key={i} style={{ fontSize: ".85rem", color: "var(--texto-2)", lineHeight: 1.7, marginBottom: 6 }}>
                    {li}
                  </li>
                ))}
              </ul>
            </Sub>
          </Seccion>

          {/* Reglas */}
          <Seccion titulo="Las reglas que el sitio aplica">
            <ol style={{ listStyle: "none", paddingLeft: 0, counterReset: "regla" }}>
              {reglas.map((r, i) => (
                <li key={i} style={{
                  display: "flex", gap: 14, padding: "14px 16px",
                  borderRadius: 8, background: "var(--panel)",
                  border: "1px solid var(--borde)", marginBottom: 8,
                  boxShadow: "var(--sombra)",
                }}>
                  <span style={{
                    fontFamily: "var(--mono)", fontSize: ".72rem", color: "#fff",
                    background: "var(--azul-medio)", borderRadius: "50%",
                    width: 22, height: 22, display: "flex", alignItems: "center",
                    justifyContent: "center", flexShrink: 0, fontWeight: 700, marginTop: 1,
                  }}>
                    {i + 1}
                  </span>
                  <p style={{ fontSize: ".85rem", color: "var(--texto-2)", lineHeight: 1.65, margin: 0 }}>
                    <strong style={{ color: "var(--texto)" }}>{r.titulo}</strong>{" "}{r.texto}
                  </p>
                </li>
              ))}
            </ol>
            <Sub titulo="La reja de cobertura">
              <P>
                Un año necesita <strong style={{ color: "var(--texto)" }}>300 días con dato</strong> para
                mostrar su media anual, y un día necesita 18 horas válidas para contar. El caso que
                obligó a escribir la regla: El Bosque midió 59 días en 2025 —enero a marzo— y su
                promedio da 14,6 µg/m³ contra 26,2 el año anterior. Sin la reja, el mapa habría
                anunciado que la comuna se limpió un 44 %.
              </P>
            </Sub>
          </Seccion>

          {/* Puntos no mancha */}
          <Seccion titulo="Por qué el mapa muestra puntos y no una mancha">
            <P>
              Se probó interpolar una superficie continua con{" "}
              <em>leave-one-station-out</em>:
            </P>
            <div style={{ overflowX: "auto", borderRadius: 8, marginBottom: 14 }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: ".85rem" }}>
                <thead>
                  <tr>
                    {["Ciudad", "R² del modelo", "R² promedio vecinas", "Veredicto"].map((h) => (
                      <th key={h} style={{
                        background: "var(--navy)", color: "rgba(255,255,255,0.8)",
                        fontFamily: "var(--mono)", fontSize: ".64rem", textTransform: "uppercase",
                        letterSpacing: ".06em", padding: "10px 14px", textAlign: "left",
                      }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {r2.map((row, i) => (
                    <tr key={i}>
                      <td style={{ padding: "9px 14px", borderBottom: "1px solid var(--borde)", background: i % 2 ? "var(--fondo-alt)" : "var(--panel)", fontFamily: "var(--mono)", fontSize: ".76rem", color: "var(--azul-medio)" }}>{row.ciudad}</td>
                      <td style={{ padding: "9px 14px", borderBottom: "1px solid var(--borde)", background: i % 2 ? "var(--fondo-alt)" : "var(--panel)", color: "var(--texto-2)", textAlign: "center" }}>{row.modelo}</td>
                      <td style={{ padding: "9px 14px", borderBottom: "1px solid var(--borde)", background: i % 2 ? "var(--fondo-alt)" : "var(--panel)", color: "var(--texto-2)", textAlign: "center" }}>{row.vecinas}</td>
                      <td style={{ padding: "9px 14px", borderBottom: "1px solid var(--borde)", background: i % 2 ? "var(--fondo-alt)" : "var(--panel)", color: "var(--texto-2)", fontSize: ".82rem" }}>{row.veredicto}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Seccion>

          {/* Reproducir */}
          <Seccion titulo="Reproducir el sitio">
            <pre style={{ background: "var(--navy)", borderRadius: 10, padding: "18px 20px", overflowX: "auto", marginBottom: 14, border: "1px solid rgba(255,255,255,0.05)" }}>
              <code style={{ fontFamily: "var(--mono)", fontSize: ".78rem", color: "#93c5fd", lineHeight: 1.7 }}>
                {"# 1. datos: consulta Athena y escribe los JSON del sitio\npython -m src.sitio.exportar\n\n# 2. revisar lo escrito sin volver a consultar\npython -m src.sitio.exportar --verificar\n\n# 3. ver el sitio en local\npython -m http.server 8000 --directory sitio"}
              </code>
            </pre>
            <P>
              El paso 1 es el único que necesita credenciales de AWS, leídas del perfil local
              (<code style={{ fontFamily: "var(--mono)", fontSize: ".78rem", background: "var(--fondo-alt)", border: "1px solid var(--borde)", borderRadius: 3, padding: "1px 5px", color: "var(--azul)" }}>~/.aws/credentials</code>).
              No hay ninguna llave en el código ni en el sitio.
            </P>
          </Seccion>

        </div>
      </div>

      <footer style={{
        background: "var(--navy)", color: "rgba(255,255,255,0.4)",
        fontFamily: "var(--mono)", fontSize: ".72rem", lineHeight: 1.7,
        padding: "14px 24px", textAlign: "center",
      }}>
        Estudio ecológico observacional · <b style={{ color: "rgba(255,255,255,0.65)" }}>asociación, no causalidad</b><br />
        Aire SINCA (MMA) · Salud DEIS (MINSAL) · Población INE · Leña CASEN ·
        Meteorología Open-Meteo · Cartografía OSM / CARTO
      </footer>
    </div>
  );
}
