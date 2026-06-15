import { useState } from "react"

export default function Sources({ sources = [] }) {
  const [open, setOpen] = useState(false)

  if (!sources.length) return null

  return (
    <div className="sources">
      <button className="source-toggle" onClick={() => setOpen(!open)}>
        Sources {open ? "▲" : "▼"}
      </button>

      {open && (
        <div className="source-list">
          {sources.map((s, i) => (
            <div key={i} className="source-card">
              <p>{s.document || "Document snippet"}</p>
              <span>Score: {s.score}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}