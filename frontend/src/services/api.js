import axios from "axios"

const API = axios.create({
  baseURL: "http://localhost:8000"
})

export const sendMessage = async (message) => {
  const res = await API.post("/chat", {
    message
  })

  return res.data
}