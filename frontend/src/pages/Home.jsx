import { useState } from "react"
import { useChat } from "../hooks/useChat"
import { FiMoon, FiSun } from "react-icons/fi"
import Message from "../components/Message"
import Sources from "../components/Sources"
import Typing from "../components/Typing"

export default function Home() {
  const chat = useChat()
  const [input, setInput] = useState("")
  const [theme, setTheme] = useState("dark")

  const toggleTheme = () => {
    setTheme(prev => (prev === "dark" ? "light" : "dark"))
  }

  const activeMessages = chat.activeChat?.messages || []

  const handleSend = () => {
    chat.send(input)
    setInput("")
  }

  return (
    <div className={`app ${theme}`}>

      {/* SIDEBAR */}
      <div className="sidebar">

        {/* LOGO */}
        <div className="logo">
          <div className="logo-dot"></div>
          <span>Sahachari</span>
        </div>

        {/* THEME TOGGLE */}
        <button className="theme-toggle" onClick={toggleTheme}>
          {theme === "dark" ? <FiMoon /> : <FiSun />}
        </button>

        {/* NEW CHAT */}
        <button className="new-chat" onClick={chat.newChat}>
          + New Chat
        </button>

        {/* RECENT CHATS */}
        <div className="recent">
          <p>Recent Chats</p>

          {chat.chats.length === 0 ? (
            <div className="empty">no chats yet</div>
          ) : (
            chat.chats.map((c) => (
              <div
                key={c.id}
                className="chat-item"
                onClick={() => chat.openChat(c.id)}
                style={{
                  cursor: "pointer",
                  border:
                    chat.activeChatId === c.id
                      ? "1px solid #00d4ff"
                      : "1px solid #1b2a3a"
                }}
              >
                {c.title}
              </div>
            ))
          )}
        </div>
      </div>

      {/* MAIN AREA */}
      <div className="main">

        {/* CHAT BOX */}
        <div className="chat-box">

          {/* WELCOME SCREEN */}
          {activeMessages.length === 0 && (
            <div className="welcome">
              <h2>How can I help you today?</h2>
              <p>Ask a question to search across available documentation.</p>

              <div className="prompt-grid">
                {[
                  "What documents are available?",
                  "Summarize the key topics",
                  "What are the main guidelines?",
                  "How does the process work?"
                ].map((p, i) => (
                  <button key={i} onClick={() => chat.send(p)}>
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* MESSAGES */}
          {activeMessages.map((msg, i) => (
            <div key={i}>
              <Message msg={msg} />

              {msg.role === "assistant" && msg.sources?.length > 0 && (
                <Sources sources={msg.sources} />
              )}
            </div>
          ))}

          {/* LOADING */}
          {chat.loading && <Typing />}

          {/* SCROLL REF */}
          <div ref={chat.bottomRef}></div>
        </div>

        {/* INPUT AREA */}
        <div className="input-box">

          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask Sahachari anything from the documents..."
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
          />

          <button onClick={handleSend}>Send</button>

        </div>

      </div>
    </div>
  )
}