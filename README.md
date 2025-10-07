# Auto-Reply Bot (Windows + Ollama + OpenAI SDK)

A local Python email auto-reply bot that reads incoming Gmail messages and responds using Ollama with a personality-driven style. It falls back to a static message if the AI fails, and logs all replies for auditing.

---

## Folder Structure

auto_reply_bot/  
├── .env  
├── main.py  
├── credentials.json  
├── token.json  
├── reply.json  
├── replied_senders.csv   
├── characters/           
│   ├── nijika.json  
│   ├── kita.json  
│   ├── ryo.json  
│   └── seika.json  
└── logs/  
    └── runtime.log  

---

## Requirements

- Python 3.10+
- Windows 10/11
- Ollama installed ([ollama.ai](https://ollama.ai/))
- Gmail API enabled with OAuth credentials ([google cloud console](https://console.cloud.google.com/apis/api/gmail.googleapis.com))

---
### Install dependencies:

```
pip install -r requirements.txt
```

---

## Configuration

### .env
```
OPENAI_API_BASE=http://localhost:11434/v1
OPENAI_API_KEY=ollama
MODEL_NAME=gemma:8b
```


### Gmail Credentials

- Download `credentials.json` from Google Cloud Console
- Place it in the project root

---

## Usage

1. Run the bot once to authenticate Gmail:
```
python main.py
```

2. The script will create `token.json` after login.

3. The bot runs continuously:
   - Checks for new Gmail messages
   - Generates character-based replies with Ollama Gemma:8b
   - Falls back to `reply.json` message if AI fails
   - Logs all replies to `replied_senders.csv` and `logs/runtime.log`

---

## Security Notes

- Do not commit `.env`, `credentials.json`, or `token.json` to public repositories
- Treat `replied_senders.csv` and `logs/runtime.log` as sensitive because they contain sender emails

---

## Character System

- Each character is a JSON file in `/characters/`
- Fields include:
  - name, role, personality, background, style, quirks, randomFacts
- Each email reply is randomly assigned a character

---

## Fallback System

- If Ollama is unavailable or throws an error:
  - Bot automatically uses `reply.json["message"]` as the reply
  - Logs fallback usage in `runtime.log`

---

## Optional Windows Tips

- Run minimized in PowerShell
- Schedule using Task Scheduler: run at startup, "whether user is logged on or not"
- Logs are saved in `/logs/runtime.log`



