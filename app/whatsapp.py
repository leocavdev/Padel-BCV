import requests
from flask import current_app


def notify_new_match(match):
    """Send a WhatsApp group message when a new match is created."""
    instance_id = current_app.config.get('GREENAPI_INSTANCE_ID')
    token       = current_app.config.get('GREENAPI_TOKEN')
    group_id    = current_app.config.get('GREENAPI_GROUP_ID')

    if not all([instance_id, token, group_id]):
        return

    date_str  = match.date.strftime('%d/%m/%Y')
    start_str = match.start_time.strftime('%H:%M')
    end_str   = match.end_time.strftime('%H:%M')
    price     = match.price_per_player

    skill_labels = {
        'beginner':     'Débutant',
        'intermediate': 'Intermédiaire',
        'advanced':     'Avancé',
        'expert':       'Expert',
    }
    skill_label = skill_labels.get(match.required_skill, match.required_skill)

    message = (
        f"🎾 *Nouveau match Padel BCV !*\n\n"
        f"📍 Lieu : {match.location}\n"
        f"📅 Date : {date_str} · {start_str}–{end_str}\n"
        f"💪 Niveau : {skill_label}\n"
        f"💶 Prix : {price:.2f} CHF/joueur\n\n"
        f"Inscris-toi vite 👉 https://padel-bcv.onrender.com"
    )

    url = (
        f"https://api.green-api.com"
        f"/waInstance{instance_id}/sendMessage/{token}"
    )
    try:
        requests.post(url, json={"chatId": group_id, "message": message}, timeout=10)
    except Exception:
        pass  # never block match creation if WhatsApp call fails
