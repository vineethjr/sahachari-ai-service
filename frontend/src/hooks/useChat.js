import { useState, useRef } from "react"
import { sendMessage } from "../services/api"

export function useChat() {
  const [chats, setChats] = useState([])
  const [activeChatId, setActiveChatId] = useState(null)
  const [loading, setLoading] = useState(false)

  const bottomRef = useRef(null)

  const activeChat = chats.find(c => c.id === activeChatId)

  const scrollToBottom = () => {
    setTimeout(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }, 100)
  }

  const newChat = () => {
    const id = Date.now()
    const chat = {
      id,
      title: "New Chat",
      messages: []
    }
    setChats(prev => [chat, ...prev])
    setActiveChatId(id)
  }

  const openChat = (id) => {
    setActiveChatId(id)
  }

  const send = async (text) => {
    if (!text.trim()) return

    let chatId = activeChatId

    if (!chatId) {
      const id = Date.now()
      chatId = id

      const newChatObj = {
        id,
        title: text.slice(0, 35),
        messages: []
      }

      setChats(prev => [newChatObj, ...prev])
      setActiveChatId(id)
    }

    const userMsg = { role: "user", content: text }

    setChats(prev =>
      prev.map(c =>
        c.id === chatId
          ? {
              ...c,
              messages: [...c.messages, userMsg],
              title: c.messages.length === 0 ? text.slice(0, 35) : c.title
            }
          : c
      )
    )

    setLoading(true)
    scrollToBottom()

    // build history in the format backend expects
    const currentChat = chats.find(c => c.id === chatId)
    const history = (currentChat?.messages || []).map(m => ({
      role: m.role === "assistant" ? "model" : "user",
      parts: [{ text: m.content }]
    }))

    try {
      const res = await sendMessage(text, history)

      const botMsg = {
        role: "assistant",
        content: res.reply,
        sources: []
      }

      setChats(prev =>
        prev.map(c =>
          c.id === chatId
            ? {
                ...c,
                messages: [...c.messages, botMsg],
                title: c.title === "New Chat" ? text.slice(0, 25) : c.title
              }
            : c
        )
      )

    } catch (e) {
      setChats(prev =>
        prev.map(c =>
          c.id === chatId
            ? {
                ...c,
                messages: [
                  ...c.messages,
                  { role: "assistant", content: "Unable to retrieve response" }
                ]
              }
            : c
        )
      )
    } finally {
      setLoading(false)
      scrollToBottom()
    }
  }

  return {
    chats,
    activeChat,
    activeChatId,
    newChat,
    openChat,
    send,
    loading,
    bottomRef
  }
}
