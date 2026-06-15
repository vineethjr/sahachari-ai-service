import axios from "axios"

const API = axios.create({
  baseURL: "http://localhost:8000"
})

export const sendMessage = async (question) => {
  const res = await API.post("/chat", {
    question
  })

  return res.data
}