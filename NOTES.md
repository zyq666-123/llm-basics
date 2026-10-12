https://api.deepseek.com/chat/cpmpletions
POST
Authorization:Bear 你的Deepseek API密钥
"message":[
  {"content":"you are a helpful assistant",
   "role":"system"},
  {"content":"Hi",
   "role":"user"}

]
"model":"deepseek-flash"