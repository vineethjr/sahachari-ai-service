import axios from "axios"

const TEST_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2YTExOTMyMzdjYjA2MDljZTE4ZDZmZmUiLCJlbWFpbCI6ImFhZGl0aEBnbWFpbC5jb20iLCJyb2xlIjoiVVNFUiIsInN0YXR1cyI6IkFDVElWRSIsImlhdCI6MTc4MTY5ODM0NiwiZXhwIjoxNzg0MjkwMzQ2fQ.-nWJA_QbuPZzbryL4aMM5e5CSSIRvXNMoXSHyB9x1KM"

const API = axios.create({
  baseURL: "http://localhost:3000"
})

API.interceptors.request.use((config) => {
  config.headers.Authorization = `Bearer ${TEST_TOKEN}`
  return config
})

export const sendMessage = async (message) => {
  const sessionId = localStorage.getItem("session_id") || crypto.randomUUID()
  localStorage.setItem("session_id", sessionId)

  const res = await API.post("/chat", {
    query: message,       // ✅ Python expects "query"
    session_id: sessionId // ✅ Python expects "session_id"
  })

  return res.data
}
