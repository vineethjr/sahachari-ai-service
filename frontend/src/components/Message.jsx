import ReactMarkdown from "react-markdown"
import CopyButton from "./CopyButton"

export default function Message({ msg }) {
  return (
    <div className={`msg ${msg.role}`}>
      <ReactMarkdown>{msg.content}</ReactMarkdown>

      {msg.role === "assistant" && (
        <CopyButton text={msg.content} />
      )}
    </div>
  )
}