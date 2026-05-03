import json
from datetime import datetime
from zoneinfo import ZoneInfo
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager

_CH = ZoneInfo('Europe/Zurich')


def _now_ch():
    return datetime.now(_CH).replace(tzinfo=None)

SKILL_LEVELS = {
    'beginner':     (0.0, 0.9, 'Débutant'),
    'intermediate': (1.0, 2.4, 'Intermédiaire'),
    'advanced':     (2.5, 4.4, 'Avancé'),
    'expert':       (4.5, 7.0, 'Expert'),
}

SKILL_ORDER = list(SKILL_LEVELS.keys())


def get_skill_category(level: float):
    """Return (key, label) for a numeric skill level."""
    for key, (min_l, max_l, label) in SKILL_LEVELS.items():
        if min_l <= level <= max_l:
            return key, label
    return 'beginner', 'Débutant'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id              = db.Column(db.Integer, primary_key=True)
    username        = db.Column(db.String(64), unique=True, nullable=False)
    email           = db.Column(db.String(120), unique=True, nullable=False)
    password_hash   = db.Column(db.String(256), nullable=False)
    role            = db.Column(db.String(20), nullable=False, default='player')
    is_approved     = db.Column(db.Boolean, nullable=False, default=False)
    skill_level     = db.Column(db.Float, nullable=False, default=0.0)
    wallet_balance  = db.Column(db.Float, nullable=False, default=0.0)
    created_at      = db.Column(db.DateTime, default=_now_ch)

    registrations   = db.relationship('MatchPlayer', back_populates='player',
                                      cascade='all, delete-orphan')
    transactions    = db.relationship('Transaction', back_populates='user',
                                      cascade='all, delete-orphan')
    created_matches = db.relationship('Match', back_populates='creator')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def skill_category_key(self):
        return get_skill_category(self.skill_level)[0]

    @property
    def skill_label(self):
        return get_skill_category(self.skill_level)[1]

    def update_skill(self, won: bool):
        if won:
            self.skill_level = min(7.0, round(self.skill_level + 0.05, 2))
        else:
            self.skill_level = max(0.0, round(self.skill_level - 0.05, 2))

    def __repr__(self):
        return f'<User {self.username}>'


class Match(db.Model):
    __tablename__ = 'matches'

    id               = db.Column(db.Integer, primary_key=True)
    location         = db.Column(db.String(200), nullable=False)
    date             = db.Column(db.Date, nullable=False)
    start_time       = db.Column(db.Time, nullable=False)
    end_time         = db.Column(db.Time, nullable=False)
    required_skill   = db.Column(db.String(20), nullable=False, default='beginner')
    status           = db.Column(db.String(20), nullable=False, default='open')
    price_per_player = db.Column(db.Float, nullable=False, default=10.0)
    winner_team      = db.Column(db.Integer, nullable=True)
    created_by       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at       = db.Column(db.DateTime, default=_now_ch)

    creator      = db.relationship('User', back_populates='created_matches')
    players      = db.relationship('MatchPlayer', back_populates='match',
                                   cascade='all, delete-orphan')
    transactions = db.relationship('Transaction', back_populates='match')

    @property
    def player_count(self):
        return MatchPlayer.query.filter_by(match_id=self.id).count()

    @property
    def is_full(self):
        return self.player_count >= 4

    @property
    def required_skill_label(self):
        return SKILL_LEVELS.get(self.required_skill, (None, None, 'Inconnu'))[2]

    @property
    def status_label(self):
        return {'open': 'Ouvert', 'confirmed': 'Confirmé',
                'completed': 'Terminé', 'cancelled': 'Annulé'}.get(self.status, self.status)

    def get_team(self, number: int):
        return [mp.player for mp in self.players if mp.team == number]

    def __repr__(self):
        return f'<Match {self.id} @ {self.location}>'


class MatchPlayer(db.Model):
    __tablename__ = 'match_players'

    id             = db.Column(db.Integer, primary_key=True)
    match_id       = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False)
    player_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    team           = db.Column(db.Integer, nullable=True)
    payment_status = db.Column(db.String(20), nullable=False, default='pending')
    joined_at      = db.Column(db.DateTime, default=_now_ch)

    match  = db.relationship('Match', back_populates='players')
    player = db.relationship('User', back_populates='registrations')

    __table_args__ = (db.UniqueConstraint('match_id', 'player_id'),)


class ReplacementRequest(db.Model):
    __tablename__ = 'replacement_requests'

    id             = db.Column(db.Integer, primary_key=True)
    match_id       = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False)
    requester_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    replacement_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status         = db.Column(db.String(20), nullable=False, default='pending')
    created_at     = db.Column(db.DateTime, default=_now_ch)

    match       = db.relationship('Match', backref='replacement_requests')
    requester   = db.relationship('User', foreign_keys=[requester_id],
                                  backref='outgoing_replacement_requests')
    replacement = db.relationship('User', foreign_keys=[replacement_id],
                                  backref='incoming_replacement_requests')

    __table_args__ = (db.UniqueConstraint('match_id', 'requester_id'),)


class MatchResultProposal(db.Model):
    __tablename__ = 'match_result_proposals'

    id               = db.Column(db.Integer, primary_key=True)
    match_id         = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False)
    proposed_by_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    winner_team      = db.Column(db.Integer, nullable=False)
    team_assignments = db.Column(db.Text, nullable=False)  # JSON: {player_id: team}
    status           = db.Column(db.String(20), nullable=False, default='pending')
    created_at       = db.Column(db.DateTime, default=_now_ch)

    match       = db.relationship('Match', backref='result_proposals')
    proposed_by = db.relationship('User', foreign_keys=[proposed_by_id],
                                  backref='result_proposals')

    def get_team_assignments(self):
        return {int(k): v for k, v in json.loads(self.team_assignments).items()}


class Transaction(db.Model):
    __tablename__ = 'transactions'

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount      = db.Column(db.Float, nullable=False)
    type        = db.Column(db.String(30), nullable=False)
    description = db.Column(db.String(300), nullable=False)
    match_id    = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=True)
    created_at  = db.Column(db.DateTime, default=_now_ch)

    user  = db.relationship('User', back_populates='transactions')
    match = db.relationship('Match', back_populates='transactions')
