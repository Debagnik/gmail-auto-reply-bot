import os
import time
import json
import csv
import logging
import signal
from datetime import datetime, timezone
from random import choice
from dotenv import load_dotenv
from openai import OpenAI
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from email.utils import parseaddr
from email.mime.text import MIMEText
import base64

# ======================================================
# CONFIGURATION
# ======================================================
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(BASE_DIR, 'credentials.json')
TOKEN_PATH = os.path.join(BASE_DIR, 'token.json')
REPLY_JSON_PATH = os.path.join(BASE_DIR, 'reply.json')
REPLIED_SENDERS_PATH = os.path.join(BASE_DIR, 'replied_senders.csv')
CHARACTERS_DIR = os.path.join(BASE_DIR, 'characters')
LOG_DIR = os.path.join(BASE_DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'runtime.log')

# Check interval in seconds
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "30"))

os.makedirs(LOG_DIR, exist_ok=True)
load_dotenv()
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s [%(levelname)s]: %(message)s')

OLLAMA_API_BASE = os.getenv("OPENAI_API_BASE", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("MODEL_NAME", "gemma3:4b")
OLLAMA_KEY = os.getenv("OPENAI_API_KEY", "ollama")
REPLY_ONCE = os.getenv("REPLY_ONCE", "True").lower() == "true"

client = OpenAI(base_url=OLLAMA_API_BASE, api_key=OLLAMA_KEY)

shutdown_requested = False
script_start_time = int(datetime.now(timezone.utc).timestamp())

# ======================================================
# GRACEFUL SHUTDOWN HANDLING
# ======================================================
def graceful_shutdown(signum=None, frame=None):
    global shutdown_requested
    if not shutdown_requested:
        print("\nStopping bot gracefully... please wait up to 30s for cleanup.")
        logging.info("Graceful shutdown requested.")
        shutdown_requested = True

signal.signal(signal.SIGINT, graceful_shutdown)
signal.signal(signal.SIGTERM, graceful_shutdown)

# ======================================================
# GMAIL AUTH
# ======================================================
def gmail_authenticate():
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, 'w') as token_file:
            token_file.write(creds.to_json())
    service = build('gmail', 'v1', credentials=creds)
    profile = service.users().getProfile(userId='me').execute()
    return service, profile['emailAddress']

# ======================================================
# EMAIL UTILITIES
# ======================================================
def get_unread_messages(service):
    query = f"is:unread after:{script_start_time}"
    results = service.users().messages().list(userId='me', labelIds=['INBOX'], q=query).execute()
    logging.info(f"Checked for unread emails, found: {results}")
    return results.get('messages', [])

def get_sender(msg):
    headers = msg['payload']['headers']
    for header in headers:
        if header['name'].lower() == 'from':
            return parseaddr(header['value'])[1]  # Extract only email
    return None

def load_replied_senders():
    if not os.path.exists(REPLIED_SENDERS_PATH):
        return set()
    with open(REPLIED_SENDERS_PATH, newline='', encoding='utf-8') as f:
        next(csv.reader(f), None)  # Skip header
        return set(row[0] for row in csv.reader(f) if row)

def save_replied_sender(sender, character_name, used_fallback):
    is_new_file = not os.path.exists(REPLIED_SENDERS_PATH)
    with open(REPLIED_SENDERS_PATH, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if is_new_file:
            writer.writerow(["sender_email", "timestamp", "character_used", "fallback_used"])
        writer.writerow([
            sender,
            datetime.now(timezone.utc).isoformat(),
            character_name,
            "Yes" if used_fallback else "No"
        ])

def load_characters():
    characters = []
    if os.path.exists(CHARACTERS_DIR):
        for file in os.listdir(CHARACTERS_DIR):
            if file.endswith('.json'):
                with open(os.path.join(CHARACTERS_DIR, file), encoding='utf-8') as f:
                    characters.append(json.load(f))
    return characters

def load_fallback_message():
    if not os.path.exists(REPLY_JSON_PATH):
        return "Thank you for reaching out! I'll get back to you soon."
    with open(REPLY_JSON_PATH, encoding='utf-8') as f:
        data = json.load(f)
        return data.get('message', "Thank you for your email!")

def generate_ai_reply(prompt):
    try:
        completion = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Ollama API error: {e}")
        return None

def send_reply(service, to_email, subject, message_body, character):
    message_body = f"{message_body}\n\n-{character.get('name', 'Automated System')}."
    reply = MIMEText(message_body)
    reply['to'] = to_email
    reply['subject'] = f"Re: {subject} - OOO Automated Reply"
    reply['From'] = f"secure.test@debagnik.in"
    raw = base64.urlsafe_b64encode(reply.as_bytes()).decode()
    service.users().messages().send(userId='me', body={'raw': raw}).execute()

# ======================================================
# MAIN LOOP
# ======================================================
def main():
    logging.info("Starting Gmail Auto Reply Bot (Windows)")
    print(f"Gmail Auto Reply Bot started. Press Ctrl+C to stop. (Reply once per sender: {REPLY_ONCE})")
    service, my_email = gmail_authenticate()

    replied_senders = load_replied_senders()
    characters = load_characters()
    fallback_message = load_fallback_message()

    if not characters:
        logging.warning("No character profiles found. Using default reply personality.")
        characters = [{"name": "Default", "style": "friendly"}]

    while not shutdown_requested:
        try:
            messages = get_unread_messages(service)
            for msg_meta in messages:
                msg = service.users().messages().get(userId='me', id=msg_meta['id']).execute()
                sender = get_sender(msg)
                if not sender or (REPLY_ONCE and sender in replied_senders) or sender == my_email:
                    continue  # Skip if already replied (when toggle on) or self

                character = choice(characters)

                # Use reply.json content as prompt only
                prompt = (
                            f"You are {character.get('name')}, a {character.get('style')} persona. "
                            f"Facts about you: {character.get('randomFacts', [])}. "
                            f"Personality quirks: {character.get('quirks', [])}. "
                            f"Your task: rewrite and deliver the following message so that it keeps ALL its information, facts, and meaning intact, "
                            f"but sounds exactly like something {character.get('name')} would say — their tone, habits, mannerisms, and emotional nuance. "
                            f"Do not shorten or omit any factual part of the message. "
                            f"Keep it readable as an in-character email reply, not a script or stage direction. "
                            f"Here is the message you must fully express in character:\n\"{fallback_message}\""
                )
                ai_reply = generate_ai_reply(prompt)
                used_fallback = False
                if not ai_reply:
                    ai_reply = fallback_message
                    used_fallback = True

                send_reply(service, sender, "Automated Reply", ai_reply, character)

                
                replied_senders.add(sender)
                save_replied_sender(sender, character.get('name'), used_fallback)

                logging.info(f"Replied to {sender} with persona {character.get('name')}, fallback: {used_fallback}")
                print(f"✔ Replied to {sender} ({character.get('name')}){' [fallback]' if used_fallback else ''}")

            # Responsive sleep using CHECK_INTERVAL
            for _ in range(CHECK_INTERVAL):
                if shutdown_requested:
                    break
                time.sleep(1)

        except KeyboardInterrupt:
            graceful_shutdown()
        except Exception as e:
            logging.error(f"Runtime error: {e}")
            time.sleep(5)

    logging.info("Bot stopped gracefully.")
    print("Bot stopped gracefully.")

if __name__ == "__main__":
    main()
