from datetime import date
from functools import wraps
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.admin import bp
from app.admin.forms import CreateMatchForm, EditMatchForm
from app.models import (Match, MatchPlayer, Transaction, User,
                         ReplacementRequest, MatchResultProposal,
                         SKILL_ORDER, SKILL_LEVELS)


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            flash('Accès réservé aux administrateurs.', 'danger')
            return redirect(url_for('matches.list_matches'))
        return f(*args, **kwargs)
    return decorated


# ── Dashboard ──────────────────────────────────────────────────────────────────

@bp.route('/')
@admin_required
def dashboard():
    status_filter = request.args.get('status', '')
    query = Match.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    matches = query.order_by(Match.date.desc(), Match.start_time.desc()).all()

    stats = {
        'total':     Match.query.count(),
        'open':      Match.query.filter_by(status='open').count(),
        'confirmed': Match.query.filter_by(status='confirmed').count(),
        'completed': Match.query.filter_by(status='completed').count(),
        'players':   User.query.filter_by(role='player').count(),
    }
    return render_template('admin/dashboard.html', matches=matches,
                           stats=stats, current_status=status_filter,
                           title="Panneau d'administration")


# ── Match CRUD ─────────────────────────────────────────────────────────────────

@bp.route('/matches/create', methods=['GET', 'POST'])
@admin_required
def create_match():
    form = CreateMatchForm()
    if form.validate_on_submit():
        match = Match(
            location=form.location.data,
            date=form.date.data,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            required_skill=form.required_skill.data,
            price_per_player=form.price_per_player.data,
            created_by=current_user.id,
        )
        db.session.add(match)
        db.session.commit()
        flash('Match créé avec succès.', 'success')
        return redirect(url_for('admin.manage_match', match_id=match.id))
    return render_template('admin/create_match.html', form=form, title='Créer un match')


@bp.route('/matches/<int:match_id>/manage')
@admin_required
def manage_match(match_id):
    match = Match.query.get_or_404(match_id)
    return render_template('admin/manage_match.html', match=match, title='Gérer le match')


@bp.route('/matches/<int:match_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_match(match_id):
    match = Match.query.get_or_404(match_id)
    form = EditMatchForm(obj=match)
    if form.validate_on_submit():
        match.location = form.location.data
        match.date = form.date.data
        match.start_time = form.start_time.data
        match.end_time = form.end_time.data
        match.required_skill = form.required_skill.data
        match.price_per_player = form.price_per_player.data
        db.session.commit()
        flash('Match mis à jour avec succès.', 'success')
        return redirect(url_for('admin.manage_match', match_id=match_id))
    return render_template('admin/edit_match.html', form=form, match=match, title='Modifier le match')


@bp.route('/matches/<int:match_id>/cancel', methods=['POST'])
@admin_required
def cancel_match(match_id):
    match = Match.query.get_or_404(match_id)
    if match.status in ('cancelled', 'completed'):
        flash('Ce match ne peut pas être annulé.', 'warning')
        return redirect(url_for('admin.dashboard'))

    refunded = 0
    for mp in match.players:
        if mp.payment_status == 'paid':
            mp.player.wallet_balance += match.price_per_player
            mp.payment_status = 'refunded'
            db.session.add(Transaction(
                user_id=mp.player_id,
                amount=match.price_per_player,
                type='refund',
                description=f'Remboursement annulation match #{match.id} — {match.location}',
                match_id=match.id,
            ))
            refunded += 1

    match.status = 'cancelled'
    db.session.commit()
    flash(f'Match annulé. {refunded} remboursement(s) traité(s).', 'success')
    return redirect(url_for('admin.dashboard'))


# ── Payment confirmation ───────────────────────────────────────────────────────

@bp.route('/matches/<int:match_id>/confirm-payment/<int:player_id>', methods=['POST'])
@admin_required
def confirm_payment(match_id, player_id):
    mp = MatchPlayer.query.filter_by(match_id=match_id, player_id=player_id).first_or_404()
    if mp.payment_status != 'pending':
        flash('Le statut du paiement a déjà été traité.', 'warning')
        return redirect(url_for('admin.manage_match', match_id=match_id))

    mp.payment_status = 'paid'
    db.session.add(Transaction(
        user_id=player_id,
        amount=-mp.match.price_per_player,
        type='match_fee',
        description=f'Paiement match #{match_id} — {mp.match.location}',
        match_id=match_id,
    ))
    db.session.commit()
    flash(f'Paiement de {mp.player.username} confirmé.', 'success')
    return redirect(url_for('admin.manage_match', match_id=match_id))


# ── Record result & update skill levels ───────────────────────────────────────

@bp.route('/matches/<int:match_id>/record-result', methods=['POST'])
@admin_required
def record_result(match_id):
    match = Match.query.get_or_404(match_id)
    if match.status != 'confirmed':
        flash('Vous ne pouvez enregistrer des résultats que pour les matchs confirmés.', 'danger')
        return redirect(url_for('admin.manage_match', match_id=match_id))

    if match.date > date.today():
        flash('Impossible de terminer un match dont la date est dans le futur.', 'danger')
        return redirect(url_for('admin.manage_match', match_id=match_id))

    winner_team = request.form.get('winner_team', '')
    if winner_team not in ('1', '2'):
        flash('Sélectionnez une équipe gagnante valide.', 'danger')
        return redirect(url_for('admin.manage_match', match_id=match_id))

    winner_team = int(winner_team)
    for mp in match.players:
        team_val = request.form.get(f'team_{mp.player_id}')
        if team_val in ('1', '2'):
            mp.team = int(team_val)

    match.winner_team = winner_team
    match.status = 'completed'

    for mp in match.players:
        if mp.team is not None:
            mp.player.update_skill(won=(mp.team == winner_team))

    db.session.commit()
    flash('Résultat enregistré. Niveaux mis à jour automatiquement.', 'success')
    return redirect(url_for('admin.manage_match', match_id=match_id))


# ── Player management ─────────────────────────────────────────────────────────

@bp.route('/players')
@admin_required
def list_players():
    skill_filter = request.args.get('skill', '')
    query = User.query.filter_by(role='player')

    if skill_filter in SKILL_LEVELS:
        min_level, max_level, _ = SKILL_LEVELS[skill_filter]
        query = query.filter(User.skill_level >= min_level,
                             User.skill_level <= max_level)

    players = query.order_by(User.username).all()
    return render_template('admin/players.html', players=players,
                           title='Joueurs', current_skill=skill_filter)


@bp.route('/players/<int:player_id>/set-level', methods=['POST'])
@admin_required
def set_level(player_id):
    player = User.query.filter_by(id=player_id, role='player').first_or_404()
    try:
        skill_level = float(request.form.get('skill_level', player.skill_level))
    except (TypeError, ValueError):
        flash('Niveau invalide.', 'danger')
        return redirect(url_for('admin.list_players'))

    if skill_level < 0.0 or skill_level > 7.0:
        flash('Le niveau doit être entre 0.0 et 7.0.', 'danger')
        return redirect(url_for('admin.list_players'))

    player.skill_level = round(skill_level, 2)
    db.session.commit()
    flash(f'Niveau de {player.username} mis à jour à {player.skill_level:.1f}.', 'success')
    return redirect(url_for('admin.list_players'))


@bp.route('/database')
@admin_required
def database():
    users = User.query.order_by(User.id).all()
    matches = Match.query.order_by(Match.id.desc()).all()
    match_players = MatchPlayer.query.order_by(MatchPlayer.id.desc()).all()
    transactions = Transaction.query.order_by(Transaction.id.desc()).all()
    replacements = ReplacementRequest.query.order_by(ReplacementRequest.id.desc()).all()
    proposals = MatchResultProposal.query.order_by(MatchResultProposal.id.desc()).all()
    counts = {
        'users': len(users),
        'matches': len(matches),
        'match_players': len(match_players),
        'transactions': len(transactions),
        'replacements': len(replacements),
        'proposals': len(proposals),
    }
    return render_template('admin/database.html',
                           users=users, matches=matches,
                           match_players=match_players,
                           transactions=transactions,
                           replacements=replacements,
                           proposals=proposals,
                           counts=counts,
                           title='Base de données')


@bp.route('/players/<int:player_id>/add-balance', methods=['POST'])
@admin_required
def add_balance(player_id):
    player = User.query.get_or_404(player_id)
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        flash('Montant invalide.', 'danger')
        return redirect(url_for('admin.list_players'))

    if amount <= 0:
        flash('Le montant doit être supérieur à 0.', 'danger')
        return redirect(url_for('admin.list_players'))

    player.wallet_balance += amount
    db.session.add(Transaction(
        user_id=player.id,
        amount=amount,
        type='top_up',
        description="Rechargement manuel par l'administrateur",
    ))
    db.session.commit()
    flash(f'{amount:.2f} CHF ajoutés au portefeuille de {player.username}.', 'success')
    return redirect(url_for('admin.list_players'))