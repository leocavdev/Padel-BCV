from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

login_manager.login_view = 'auth.login'
login_manager.login_message = 'Veuillez vous connecter pour continuer.'
login_manager.login_message_category = 'warning'


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from app.matches import bp as matches_bp
    app.register_blueprint(matches_bp)

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp)

    from app.wallet import bp as wallet_bp
    app.register_blueprint(wallet_bp)

    with app.app_context():
        db.create_all()

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            if current_user.is_admin:
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('matches.list_matches'))
        return redirect(url_for('auth.login'))

    return app
