import ReactMarkdown from "react-markdown"
import CopyButton from "./CopyButton"

export default function Message({ msg }) {
  return (
    <div className={`msg ${msg.role}`}>
      <ReactMarkdown>{msg.content}</ReactMarkdown>

      {msg.role === "assistant" && (
        <>
          {msg.source && (
            <div
              style={{
                marginTop: "10px",
                fontSize: "12px",
                opacity: 0.8,
                borderTop: "1px solid #444",
                paddingTop: "8px"
              }}
            >
              📄 Source: {msg.source}
            </div>
          )}

          <CopyButton text={msg.content} />
        </>
      )}
    </div>
  )
}