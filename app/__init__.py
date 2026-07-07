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
        _migrate()
        _seed_admin()

    @app.context_processor
    def inject_pending_players_count():
        if current_user.is_authenticated and current_user.is_admin:
            from app.models import User
            count = User.query.filter_by(is_approved=False, role='player').count()
            return {'pending_players_count': count}
        return {'pending_players_count': 0}

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            if current_user.is_admin:
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('matches.list_matches'))
        return redirect(url_for('auth.login'))

    return app


def _migrate():
    from sqlalchemy import text, inspect
    inspector = inspect(db.engine)
    existing_users = [col['name'] for col in inspector.get_columns('users')]
    existing_matches = [col['name'] for col in inspector.get_columns('matches')]
    with db.engine.connect() as conn:
        if 'is_approved' not in existing_users:
            conn.execute(text(
                'ALTER TABLE users ADD COLUMN is_approved BOOLEAN NOT NULL DEFAULT TRUE'
            ))
        if 'nom' not in existing_users:
            conn.execute(text('ALTER TABLE users ADD COLUMN nom VARCHAR(64)'))
        if 'prenom' not in existing_users:
            conn.execute(text('ALTER TABLE users ADD COLUMN prenom VARCHAR(64)'))
        if 'paid_by' not in existing_matches:
            conn.execute(text('ALTER TABLE matches ADD COLUMN paid_by VARCHAR(20)'))
        if 'reimbursed_amount' not in existing_matches:
            conn.execute(text(
                'ALTER TABLE matches ADD COLUMN reimbursed_amount FLOAT NOT NULL DEFAULT 0.0'
            ))
        if 'warning_sent_at' not in existing_matches:
            conn.execute(text('ALTER TABLE matches ADD COLUMN warning_sent_at TIMESTAMP'))
        conn.commit()


def _seed_admin():
    import os
    from app.models import User
    email    = os.environ.get('ADMIN_EMAIL')
    password = os.environ.get('ADMIN_PASSWORD')
    if not email or not password:
        return
    admin = User.query.filter_by(email=email).first()
    if admin:
        admin.set_password(password)
        admin.role = 'admin'
        admin.is_approved = True
    else:
        admin = User(username='admin', email=email, role='admin', is_approved=True)
        admin.set_password(password)
        db.session.add(admin)
    db.session.commit()
