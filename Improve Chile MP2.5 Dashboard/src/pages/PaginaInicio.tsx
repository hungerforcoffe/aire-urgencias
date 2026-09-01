const S = {
  consola: {
    display: "grid",
    gridTemplateColumns: "240px 1fr",
    gridTemplateRows: "1fr 76px",
    gridTemplateAreas: '"riel mapa" "riel tira"',
    height: "calc(100vh - 52px - 44px)",
    minHeight: 400,
    borderBottom: "1px solid var(--borde)",
  } as React.CSSProperties,

  riel: {
    gridArea: "riel",
    background: "var(--panel)",
    borderRight: "1px solid var(--borde)",
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
  } as React.CSSProperties,

  rielTit: {
    padding: "13px 16px 10px",
    borderBottom: "1px solid var(--borde)",
    background: "var(--panel-alt)",
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    position: "sticky",
    top: 0,
    zIndex: 10,
  } as React.CSSProperties,

  mapa: {
    gridArea: "mapa",
    background: "linear-gradient(155deg,#c4d9f5 0%,#d5e8f8 55%,#b6cfe8 100%)",
    position: "relative",
    overflow: "hidden",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "column",
    gap: 12,
  } as React.CSSProperties,

  tira: {
    gridArea: "tira",
    background: "var(--panel)",
    borderTop: "1px solid var(--borde)",
    display: "flex",
    alignItems: "stretch",
  } as React.CSSProperties,
};

const estaciones = [
  { id: "LC", nombre: "Las Condes", ciudad: "Santiago", val: 11.2 },
  { id: "PM", nombre: "Pudahuel", ciudad: "Santiago", val: 28.4 },
  { id: "CE", nombre: "Cerrillos", ciudad: "Santiago", val: 24.1 },
  { id: "IN", nombre: "Independencia", ciudad: "Santiago", val: 22.7 },
  { id: "EB", nombre: "El Bosque", ciudad: "Santiago", val: null },
  { id: "QN", nombre: "Quilicura", ciudad: "Santiago", val: 19.8 },
  { id: "PA", nombre: "Parque O'Higgins", ciudad: "Santiago", val: 21.3 },
  { id: "TA", nombre: "Talcahuano", ciudad: "Talcahuano", val: 17.6 },
  { id: "HU", nombre: "Hualpén", ciudad: "Talcahuano", val: 20.2 },
  { id: "CO", nombre: "Coyhaique", ciudad: "Coyhaique", val: 38.9 },
];

function colorVal(v: number | null) {
  if (v === null) return "var(--texto-3)";
  if (v < 15) return "#16a34a";
  if (v < 25) return "#d97706";
  return "#dc2626";
}

export default function PaginaInicio() {
  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "calc(100vh - 52px)" }}>

      {/* Consola principal */}
      <div style={S.consola}>

        {/* Sidebar estaciones */}
        <div style={S.riel}>
          <div style={S.rielTit}>
            <h2 style={{ fontFamily: "var(--serif)", fontSize: ".9rem", fontWeight: 600, color: "var(--navy)" }}>
              Estaciones
            </h2>
            <span style={{ fontFamily: "var(--mono)", fontSize: ".66rem", color: "var(--texto-3)" }}>
              ago 2026
            </span>
          </div>
          <div style={{ padding: "6px 0", flex: 1 }}>
            {estaciones.map((e) => (
              <div
                key={e.id}
                style={{
                  padding: "9px 16px",
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  borderBottom: "1px solid var(--borde)",
                  cursor: "pointer",
                  transition: "background .12s",
                }}
                onMouseEnter={(el) => (el.currentTarget.style.background = "var(--fondo-alt)")}
                onMouseLeave={(el) => (el.currentTarget.style.background = "transparent")}
              >
                <div
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: "50%",
                    background: colorVal(e.val),
                    border: e.val === null ? "1.5px dashed var(--texto-3)" : "none",
                    flexShrink: 0,
                  }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: ".82rem", fontWeight: 500, color: "var(--texto)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {e.nombre}
                  </div>
                  <div style={{ fontSize: ".66rem", fontFamily: "var(--mono)", color: "var(--texto-3)" }}>
                    {e.ciudad}
                  </div>
                </div>
                <div style={{ fontFamily: "var(--mono)", fontSize: ".78rem", fontWeight: 500, color: colorVal(e.val), flexShrink: 0 }}>
                  {e.val !== null ? `${e.val}` : "—"}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Mapa */}
        <div style={S.mapa}>
          {/* Decoración de fondo */}
          <div style={{
            position: "absolute", inset: 0,
            backgroundImage: "radial-gradient(circle at 35% 45%, rgba(37,99,235,0.1) 0%, transparent 55%), radial-gradient(circle at 72% 62%, rgba(13,34,64,0.07) 0%, transparent 50%)",
          }} />
          {/* Marcadores simulados */}
          {[
            { x: "42%", y: "38%", label: "Santiago", r: 18 },
            { x: "55%", y: "68%", label: "Talcahuano", r: 12 },
            { x: "62%", y: "82%", label: "Coyhaique", r: 14 },
          ].map((m) => (
            <div key={m.label} style={{ position: "absolute", left: m.x, top: m.y, transform: "translate(-50%,-50%)" }}>
              <div style={{
                width: m.r * 2, height: m.r * 2,
                borderRadius: "50%",
                background: "rgba(37,99,235,0.25)",
                border: "2px solid rgba(37,99,235,0.6)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#2563eb" }} />
              </div>
              <div style={{
                position: "absolute", top: "100%", left: "50%", transform: "translateX(-50%)",
                marginTop: 4,
                fontFamily: "var(--mono)", fontSize: ".6rem",
                color: "rgba(13,34,64,0.7)", whiteSpace: "nowrap",
                background: "rgba(255,255,255,0.7)", padding: "1px 6px", borderRadius: 3,
              }}>
                {m.label}
              </div>
            </div>
          ))}
          {/* Leyenda de placeholder */}
          <div style={{
            position: "absolute", bottom: 12, right: 14,
            fontFamily: "var(--mono)", fontSize: ".62rem",
            color: "rgba(13,34,64,0.40)",
            background: "rgba(255,255,255,0.6)",
            padding: "4px 10px", borderRadius: 4,
            backdropFilter: "blur(4px)",
          }}>
            Mapa interactivo · Leaflet / OSM
          </div>
        </div>

        {/* Línea de tiempo */}
        <div style={S.tira}>
          <div style={{
            display: "flex", flexDirection: "column", justifyContent: "center",
            padding: "0 16px", borderRight: "1px solid var(--borde)", minWidth: 130,
          }}>
            <div style={{ fontFamily: "var(--serif)", fontSize: ".95rem", fontWeight: 600, color: "var(--navy)" }}>
              ago 2026
            </div>
            <div style={{ fontFamily: "var(--mono)", fontSize: ".62rem", color: "var(--texto-3)", marginBottom: 6 }}>
              media mensual
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              {["◀", "⏸", "▶"].map((ic, i) => (
                <button key={i} style={{
                  background: "var(--fondo-alt)", border: "1px solid var(--borde)",
                  borderRadius: 6, width: 26, height: 26,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  cursor: "pointer", fontSize: ".7rem", color: "var(--azul)",
                }}>
                  {ic}
                </button>
              ))}
            </div>
          </div>
          {/* Tira de meses */}
          <div style={{ flex: 1, display: "flex", alignItems: "center", padding: "0 12px", gap: 3, overflowX: "auto" }}>
            {Array.from({ length: 24 }, (_, i) => {
              const active = i === 23;
              return (
                <div key={i} style={{
                  height: 36, width: 20, flexShrink: 0,
                  background: active ? "var(--azul-medio)" : "var(--fondo-alt)",
                  borderRadius: 3,
                  border: active ? "none" : "1px solid var(--borde)",
                  opacity: active ? 1 : 0.6 + i * 0.018,
                }} />
              );
            })}
          </div>
        </div>

      </div>

      {/* Escala */}
      <div style={{
        background: "var(--panel)", borderBottom: "1px solid var(--borde)",
        padding: "10px 20px", display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
      }}>
        <span style={{ fontFamily: "var(--mono)", fontSize: ".66rem", color: "var(--texto-2)", whiteSpace: "nowrap" }}>
          Media mensual · µg/m³
        </span>
        <div style={{
          height: 10, flex: 1, minWidth: 80, maxWidth: 260,
          borderRadius: 5,
          background: "linear-gradient(to right,#86efac,#fde68a,#fca5a5,#dc2626)",
          border: "1px solid var(--borde)",
        }} />
        <span style={{ fontFamily: "var(--mono)", fontSize: ".66rem", color: "var(--texto-2)", whiteSpace: "nowrap" }}>
          guías anuales OMS 2021 · 5 µg/m³
        </span>
        <p style={{ fontSize: ".72rem", color: "var(--texto-3)", margin: 0, width: "100%", lineHeight: 1.5 }}>
          Radio del círculo proporcional a la media del mes. Punteado = estación sin datos ese mes.
          A escala de Chile, las diez estaciones de Santiago caen en el mismo píxel.
        </p>
      </div>

      {/* Notas */}
      <div style={{ background: "var(--fondo-alt)", borderBottom: "1px solid var(--borde)", padding: "28px 20px" }}>
        <div style={{ maxWidth: 960, margin: "0 auto", display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", gap: 16 }}>
          {[
            {
              alerta: true,
              titulo: "Cobertura antes que cifra",
              texto: "El Bosque midió 59 días en 2025 —enero a marzo, puro verano— y su promedio da 14,6 µg/m³ contra 26,2 el año anterior. Un año necesita 300 días para mostrar promedio.",
            },
            {
              titulo: "Qué dice la rosa",
              texto: "Cada pétalo es la mediana horaria de MP2.5 en invierno de las horas en que el viento venía de ese sector. Un pétalo largo al este dice «cuando sopló del este, el sensor midió más».",
            },
            {
              titulo: "Puntos, no una mancha",
              texto: "Prediciendo cada estación desde las demás, el modelo dio R² 0,533 contra 0,750 del simple promedio de vecinas. Las Condes queda en −0,01: impredecible desde el resto de la ciudad.",
            },
          ].map((n, i) => (
            <div key={i} style={{
              background: "var(--panel)", borderRadius: 12,
              border: "1px solid var(--borde)", padding: "18px 20px",
              boxShadow: "var(--sombra)",
            }}>
              <h3 style={{
                fontFamily: "var(--serif)", fontSize: ".95rem", fontWeight: 600,
                color: n.alerta ? "var(--alerta)" : "var(--navy)",
                marginBottom: 10, display: "flex", alignItems: "flex-start", gap: 8,
              }}>
                {n.alerta && (
                  <span style={{
                    display: "inline-flex", alignItems: "center", justifyContent: "center",
                    width: 18, height: 18, borderRadius: "50%",
                    background: "var(--alerta)", color: "#fff",
                    fontSize: ".65rem", fontFamily: "var(--mono)", fontWeight: 700, flexShrink: 0, marginTop: 1,
                  }}>!</span>
                )}
                {n.titulo}
              </h3>
              <p style={{ fontSize: ".83rem", color: "var(--texto-2)", lineHeight: 1.65 }}>
                {n.texto}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <footer style={{
        background: "var(--navy)", color: "rgba(255,255,255,0.4)",
        fontFamily: "var(--mono)", fontSize: ".72rem", lineHeight: 1.7,
        padding: "14px 24px", textAlign: "center",
      }}>
        Estudio ecológico observacional · <b style={{ color: "rgba(255,255,255,0.65)" }}>asociación, no causalidad</b><br />
        Aire SINCA (MMA) · Salud DEIS (MINSAL) · Población INE · viento{" "}
        <a href="https://open-meteo.com/" style={{ color: "var(--celeste)" }}>Open-Meteo</a> · cartografía OSM / CARTO
      </footer>
    </div>
  );
}
