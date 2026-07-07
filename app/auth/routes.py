from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func, case
from app import db
from app.auth import bp
from app.auth.forms import LoginForm, RegisterForm
from app.models import User, MatchPlayer, Match, SKILL_LEVELS


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('matches.list_matches'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and user.check_password(form.password.data):
            if not user.is_approved and not user.is_admin:
                flash('Votre compte est en attente de validation par un administrateur.', 'warning')
                return redirect(url_for('auth.login'))
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            flash(f'Bienvenue, {user.username} !', 'success')
            if user.is_admin:
                return redirect(next_page or url_for('admin.dashboard'))
            return redirect(next_page or url_for('matches.list_matches'))
        flash('Email ou mot de passe incorrect.', 'danger')
    return render_template('auth/login.html', form=form, title='Connexion')


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('matches.list_matches'))
    form = RegisterForm()
    if form.validate_on_submit():
        base = f"{form.prenom.data.strip()} {form.nom.data.strip()}"
        username = base
        suffix = 1
        while User.query.filter_by(username=username).first():
            username = f"{base} {suffix}"
            suffix += 1
        user = User(username=username, nom=form.nom.data.strip(),
                    prenom=form.prenom.data.strip(), email=form.email.data.lower())
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Inscription reçue ! Votre compte sera activé après validation par un administrateur.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form, title='Inscription')


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Vous avez été déconnecté.', 'info')
    return redirect(url_for('auth.login'))


@bp.route('/profil')
@login_required
def profile():
    if current_user.is_admin:
        return redirect(url_for('admin.dashboard'))
    match_count = MatchPlayer.query.filter_by(player_id=current_user.id).count()
    return render_template('auth/profile.html',
                           match_count=match_count,
                           title='Mon profil')


@bp.route('/padel-bcv')
@login_required
def padel_bcv():
    return render_template('auth/padel_bcv.html',
                           title='Padel ASBCV')


@bp.route('/joueurs-bcv')
@login_required
def players_bcv():
    players = (User.query
               .filter_by(role='player')
               .order_by(User.skill_level.desc(), User.username)
               .all())
    grouped = {key: [] for key in SKILL_LEVELS}
    for player in players:
        grouped[player.skill_category_key].append(player)

    podium = players[:3]

    active_row = (db.session.query(User, func.count(MatchPlayer.id).label('cnt'))
                  .join(MatchPlayer, MatchPlayer.player_id == User.id)
                  .join(Match, Match.id == MatchPlayer.match_id)
                  .filter(User.role == 'player', Match.status == 'completed')
                  .group_by(User.id)
                  .order_by(func.count(MatchPlayer.id).desc())
                  .first())
    most_active = {'player': active_row[0], 'count': active_row[1]} if active_row else None

    stats = (db.session.query(
                 User,
                 func.count(MatchPlayer.id).label('total'),
                 func.sum(case((Match.winner_team == MatchPlayer.team, 1), else_=0)).label('wins')
             )
             .join(MatchPlayer, MatchPlayer.player_id == User.id)
             .join(Match, Match.id == MatchPlayer.match_id)
             .filter(User.role == 'player', Match.status == 'completed',
                     Match.winner_team.isnot(None))
             .group_by(User.id)
             .having(func.count(MatchPlayer.id) >= 3)
             .all())

    best_ratio = None
    if stats:
        best = max(stats, key=lambda r: (r.wins or 0) / r.total)
        wins_val = int(best.wins) if best.wins else 0
        best_ratio = {
            'player': best[0],
            'wins': wins_val,
            'total': int(best.total),
            'rate': round(wins_val / best.total * 100),
        }

    return render_template('auth/players_bcv.html',
                           groups=grouped,
                           skill_levels=SKILL_LEVELS,
                           podium=podium,
                           most_active=most_active,
                           best_ratio=best_ratio,
                           title='Joueurs ASBCV')


@bp.route('/reglement')
@login_required
def reglement():
    return render_template('auth/reglement.html',
                           title='Règlement')


@bp.route('/regles-padel')
@login_required
def regles_padel():
    return render_template('auth/regles_padel.html',
                           title='Règles de padel')


@bp.route('/niveaux')
@login_required
def skill_levels():
    if current_user.is_admin:
        return redirect(url_for('admin.dashboard'))
    return render_template('auth/skill_levels.html',
                           skill_levels=SKILL_LEVELS,
                           title='Comment progresser')
