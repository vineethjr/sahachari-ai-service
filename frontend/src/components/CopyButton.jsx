import { useState } from "react"

export default function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)

    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <button
  className={`copy-btn ${copied ? "copied" : ""}`}
  onClick={handleCopy}
>
  {copied ? "Copied" : "Copy"}
</button>
  )
}