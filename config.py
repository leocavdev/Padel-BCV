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
        "Padel BCV | Paiement des matchs | "
        "Virement : IBAN FR76 1234 5678 9012 3456 7890 123 | "
        "Libellé : Votre prénom + date du match"
    )
