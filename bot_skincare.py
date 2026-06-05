"""
Bot Telegram Skincare — Sequenza personalizzata per ogni iscritto
- /start → salva l'utente nel Google Sheet
- GitHub Actions ogni mattina invia il messaggio del giorno giusto
"""

import os
import re
import requests
import json
from datetime import date, datetime

TELEGRAM_BOT_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
GOOGLE_SHEET_ID      = os.environ["GOOGLE_SHEET_ID"]
GOOGLE_DOC_FILE_ID   = os.environ["GOOGLE_DOC_FILE_ID"]
# URL del Google Apps Script Web App (per leggere/scrivere il Sheet)
APPS_SCRIPT_URL      = os.environ["APPS_SCRIPT_URL"]


def scarica_messaggi() -> dict:
    """Scarica i messaggi dal Google Doc."""
    url = f"https://docs.google.com/document/d/{GOOGLE_DOC_FILE_ID}/export?format=txt"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    testo = r.text

    messaggi = {}
    pattern = re.compile(r'[Gg]iorno\s+(\d+)\s*[:.\-]\s*(.+?)(?=\n[Gg]iorno\s+\d+|\Z)', re.DOTALL)
    for match in pattern.finditer(testo):
        numero   = int(match.group(1))
        contenuto = match.group(2).strip()
        if contenuto:
            messaggi[numero] = contenuto
    return messaggi


def leggi_iscritti() -> list:
    """Legge gli iscritti dal Google Sheet tramite Apps Script."""
    r = requests.get(APPS_SCRIPT_URL, params={"action": "leggi"}, timeout=15)
    r.raise_for_status()
    return r.json()


def salva_iscritto(chat_id: str, nome: str) -> None:
    """Salva un nuovo iscritto nel Google Sheet."""
    payload = {
        "action": "scrivi",
        "chat_id": chat_id,
        "nome": nome,
        "data_iscrizione": date.today().isoformat()
    }
    r = requests.post(APPS_SCRIPT_URL, json=payload, timeout=15)
    r.raise_for_status()


def invia_messaggio(chat_id: str, testo: str) -> bool:
    """Invia un messaggio Telegram a un utente."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": testo,
    }
    r = requests.post(url, json=payload, timeout=15)
    return r.ok


def calcola_giorno(data_iscrizione_str: str, totale: int) -> int:
    """Calcola a che giorno della sequenza è arrivato l'utente."""
    data_iscrizione = datetime.fromisoformat(data_iscrizione_str).date()
    delta = (date.today() - data_iscrizione).days + 1  # Giorno 1 = giorno iscrizione
    if delta < 1:
        return None
    if delta > totale:
        return None  # Sequenza finita
    return delta


def processa_aggiornamenti() -> None:
    """Controlla i nuovi messaggi /start e registra gli iscritti."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    
    # Leggi offset salvato
    offset_file = "/tmp/telegram_offset.txt"
    offset = 0
    try:
        with open(offset_file) as f:
            offset = int(f.read().strip())
    except:
        pass

    r = requests.get(url, params={"offset": offset, "timeout": 5}, timeout=10)
    if not r.ok:
        return
    
    updates = r.json().get("result", [])
    
    for update in updates:
        offset = update["update_id"] + 1
        msg = update.get("message", {})
        text = msg.get("text", "")
        
        if text.startswith("/start"):
            chat_id = str(msg["chat"]["id"])
            nome = msg["from"].get("first_name", "Amico")
            
            # Controlla se già iscritto
            iscritti = leggi_iscritti()
            ids_esistenti = [str(i.get("chat_id", "")) for i in iscritti]
            
            if chat_id not in ids_esistenti:
                salva_iscritto(chat_id, nome)
                invia_messaggio(chat_id, 
                    f"Ciao {nome}! 🌿 Benvenuta nel programma skincare.\n"
                    f"Da domani riceverai ogni giorno un consiglio per prenderti cura della tua pelle. ✨"
                )
                print(f"Nuovo iscritto: {nome} ({chat_id})")
            else:
                invia_messaggio(chat_id, f"Ciao {nome}! Sei già iscritta. 😊")

    # Salva nuovo offset
    with open(offset_file, "w") as f:
        f.write(str(offset))


def invia_messaggi_giornalieri() -> None:
    """Invia il messaggio del giorno a ogni iscritto."""
    messaggi = scarica_messaggi()
    if not messaggi:
        print("Nessun messaggio trovato nel Doc.")
        return
    
    totale = len(messaggi)
    chiavi = sorted(messaggi.keys())
    iscritti = leggi_iscritti()
    
    print(f"Messaggi disponibili: {totale} | Iscritti: {len(iscritti)}")
    
    for iscritto in iscritti:
        chat_id = str(iscritto.get("chat_id", ""))
        nome    = iscritto.get("nome", "")
        data_is = iscritto.get("data_iscrizione", "")
        
        if not chat_id or not data_is:
            continue
        
        giorno = calcola_giorno(data_is, totale)
        
        if giorno is None:
            print(f"{nome}: sequenza completata o non ancora iniziata.")
            continue
        
        numero_msg = chiavi[giorno - 1]
        testo = messaggi[numero_msg]
        
        ok = invia_messaggio(chat_id, testo)
        stato = "✅" if ok else "❌"
        print(f"{stato} {nome} → Giorno {giorno}: {testo[:50]}...")


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "invia"
    
    if mode == "start":
        # Modalità: registra nuovi iscritti (esegui ogni minuto o on-demand)
        print("Controllo nuovi iscritti...")
        processa_aggiornamenti()
    else:
        # Modalità: invia messaggio giornaliero (esegui ogni mattina)
        print("Invio messaggi giornalieri...")
        invia_messaggi_giornalieri()
