import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'padel-bcv-secret-key-change-in-prod'
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get('DATABASE_URL') or
        'sqlite:///' + os.path.join(basedir, 'padel.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    PLAYERS_PER_MATCH = 4
    PAYMENT_QR_DATA = (
        "Padel BCV | Paiement des matchs | "
        "Virement : IBAN FR76 1234 5678 9012 3456 7890 123 | "
        "Libellé : Votre prénom + date du match"
    )
