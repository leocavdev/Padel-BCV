import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'padel-bcv-secret-key-change-in-prod'
    _db_url = os.environ.get('DATABASE_URL') or 'sqlite:///' + os.path.join(basedir, 'padel.db')
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    PLAYERS_PER_MATCH = 4
    PAYMENT_QR_DATA = (
        "Padel ASBCV | Paiement des matchs | "
        "Virement : IBAN FR76 1234 5678 9012 3456 7890 123 | "
        "Libellé : Votre prénom + date du match"
    )
    # Token extrait du QR code TWINT ASBCV statique (utilisé pour le deep link Android/iOS)
    TWINT_QR_TOKEN = (
        "02:1732cc684ac546e7b4e463509e548633"
        "#eedc8077fee9e3f280459d636fa00244d6a05843"
        "#a~8cDutzr6Rp2pha6lDzRJvA~s~ADL72ziETNmJAfNGQ4KXPQ"
    )
    # Green API – WhatsApp group notifications
    GREENAPI_INSTANCE_ID = os.environ.get('GREENAPI_INSTANCE_ID', '')
    GREENAPI_TOKEN       = os.environ.get('GREENAPI_TOKEN', '')
    # Group chat ID format: 120363XXXXXXXXXX@g.us  (get it via /getChats)
    GREENAPI_GROUP_ID    = os.environ.get('GREENAPI_GROUP_ID', '')
