import os
import requests

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

def send_discord_alert(title, description, fields=None):
    if not DISCORD_WEBHOOK_URL:
        print(f"[Notifier] No Discord Webhook URL provided. Alert: {title}")
        return False
    
    embed = {
        "title": f"🎲 VEGAS QUANT ALERT: {title}",
        "description": description,
        "color": 15844367, # Vegas Gold
        "fields": fields or [],
        "footer": {"text": "Autonomous NFL Betting Machine"}
    }
    payload = {"embeds": [embed]}
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        return response.status_code in [200, 204]
    except Exception as e:
        print(f"[Notifier Error]: {e}")
        return False