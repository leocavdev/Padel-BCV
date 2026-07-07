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


def _send_group_message(message):
    """Low-level helper: send a message to the WhatsApp group."""
    instance_id = current_app.config.get('GREENAPI_INSTANCE_ID')
    token       = current_app.config.get('GREENAPI_TOKEN')
    group_id    = current_app.config.get('GREENAPI_GROUP_ID')
    if not all([instance_id, token, group_id]):
        return
    url = (
        f"https://api.green-api.com"
        f"/waInstance{instance_id}/sendMessage/{token}"
    )
    try:
        requests.post(url, json={"chatId": group_id, "message": message}, timeout=10)
    except Exception:
        pass


def notify_incomplete_match_warning(match):
    """Send a WhatsApp warning when a match is incomplete 3 days before it starts."""
    date_str  = match.date.strftime('%d/%m/%Y')
    start_str = match.start_time.strftime('%H:%M')
    end_str   = match.end_time.strftime('%H:%M')
    missing   = 4 - match.player_count

    skill_labels = {
        'beginner':     'Débutant',
        'intermediate': 'Intermédiaire',
        'advanced':     'Avancé',
        'expert':       'Expert',
    }
    skill_label = skill_labels.get(match.required_skill, match.required_skill)

    message = (
        f"⚠️ *Match incomplet — J-3*\n\n"
        f"📍 Lieu : {match.location}\n"
        f"📅 Date : {date_str} · {start_str}–{end_str}\n"
        f"💪 Niveau : {skill_label}\n"
        f"👥 Joueurs inscrits : {match.player_count}/4\n\n"
        f"Il manque encore *{missing} joueur(s)* pour confirmer ce match.\n\n"
        f"⏰ Si le match n'est pas complet ce soir, il sera *annulé demain matin* "
        f"et les joueurs déjà inscrits seront remboursés automatiquement.\n\n"
        f"Inscris-toi vite 👉 https://padel-bcv.onrender.com"
    )
    _send_group_message(message)


def notify_match_auto_cancelled(match, refunded_count):
    """Send a WhatsApp notification when a match is automatically cancelled due to insufficient players."""
    date_str  = match.date.strftime('%d/%m/%Y')
    start_str = match.start_time.strftime('%H:%M')
    end_str   = match.end_time.strftime('%H:%M')

    message = (
        f"❌ *Match annulé automatiquement*\n\n"
        f"📍 Lieu : {match.location}\n"
        f"📅 Date : {date_str} · {start_str}–{end_str}\n\n"
        f"Le match n'a pas atteint le nombre de joueurs requis (4) avant la date limite.\n"
        f"Il a été annulé et {refunded_count} joueur(s) inscrit(s) ont été remboursés."
    )
    _send_group_message(message)
