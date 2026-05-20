from datetime import date, datetime
from functools import wraps
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.admin import bp
from app.admin.forms import CreateMatchForm, EditMatchForm
from app.whatsapp import notify_new_match
from app.models import (Match, MatchPlayer, Transaction, User,
                         ReplacementRequest, MatchResultProposal,
                         SKILL_ORDER, SKILL_LEVELS, _now_ch)


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
                           now=_now_ch(),
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
            price_per_player=round(form.price_per_player.data / 8, 2),
            paid_by=form.paid_by.data or None,
            created_by=current_user.id,
        )
        db.session.add(match)
        db.session.commit()
        notify_new_match(match)
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
    if request.method == 'GET':
        form.price_per_player.data = round(match.price_per_player * 8, 2)
        form.paid_by.data = match.paid_by or ''
    if form.validate_on_submit():
        match.location = form.location.data
        match.date = form.date.data
        match.start_time = form.start_time.data
        match.end_time = form.end_time.data
        match.required_skill = form.required_skill.data
        match.price_per_player = round(form.price_per_player.data / 8, 2)
        match.paid_by = form.paid_by.data or None
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


# ── Reimbursements ────────────────────────────────────────────────────────────

@bp.route('/reimbursements')
@admin_required
def reimbursements():
    matches = (Match.query
               .filter(Match.paid_by.isnot(None))
               .order_by(Match.date.desc(), Match.start_time.desc())
               .all())

    owed_to_leo = 0.0
    owed_to_witha = 0.0
    for m in matches:
        total = round(m.price_per_player * 8, 2)
        owed = round(total / 2, 2)
        remaining = max(0.0, round(owed - m.reimbursed_amount, 2))
        if m.paid_by == 'Leonardo':
            owed_to_leo += remaining
        elif m.paid_by == 'Withawat':
            owed_to_witha += remaining

    return render_template('admin/reimbursements.html',
                           matches=matches,
                           owed_to_leo=round(owed_to_leo, 2),
                           owed_to_witha=round(owed_to_witha, 2),
                           title='Remboursements')


@bp.route('/matches/<int:match_id>/toggle-reimbursement', methods=['POST'])
@admin_required
def toggle_reimbursement(match_id):
    match = Match.query.get_or_404(match_id)
    total = round(match.price_per_player * 8, 2)
    owed = round(total / 2, 2)
    if match.reimbursed_amount >= owed:
        match.reimbursed_amount = 0.0
    else:
        match.reimbursed_amount = owed
    db.session.commit()
    return redirect(url_for('admin.reimbursements'))


# ── Player management ─────────────────────────────────────────────────────────

@bp.route('/players')
@admin_required
def list_players():
    skill_filter = request.args.get('skill', '')
    query = User.query.filter_by(role='player', is_approved=True)

    if skill_filter in SKILL_LEVELS:
        min_level, max_level, _ = SKILL_LEVELS[skill_filter]
        query = query.filter(User.skill_level >= min_level,
                             User.skill_level <= max_level)

    players = query.order_by(User.username).all()
    pending = User.query.filter_by(role='player', is_approved=False).order_by(User.created_at).all()
    return render_template('admin/players.html', players=players, pending=pending,
                           title='Joueurs', current_skill=skill_filter)


@bp.route('/players/<int:player_id>/approve', methods=['POST'])
@admin_required
def approve_player(player_id):
    player = User.query.filter_by(id=player_id, role='player').first_or_404()
    player.is_approved = True
    db.session.commit()
    flash(f'Compte de {player.username} validé.', 'success')
    return redirect(url_for('admin.list_players'))


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


# ── DB direct CRUD ─────────────────────────────────────────────────────────────

# --- Users ---

def _build_unique_username(prenom, nom, exclude_id=None):
    base = f"{prenom} {nom}"
    username = base
    suffix = 1
    while True:
        q = User.query.filter_by(username=username)
        if exclude_id:
            q = q.filter(User.id != exclude_id)
        if not q.first():
            break
        username = f"{base} {suffix}"
        suffix += 1
    return username


@bp.route('/db/users/add', methods=['GET', 'POST'])
@admin_required
def db_add_user():
    if request.method == 'POST':
        nom    = request.form.get('nom', '').strip()
        prenom = request.form.get('prenom', '').strip()
        email  = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'player')
        is_approved = request.form.get('is_approved') == '1'
        try:
            skill_level = float(request.form.get('skill_level', 0))
        except ValueError:
            skill_level = 0.0
        try:
            wallet_balance = float(request.form.get('wallet_balance', 0))
        except ValueError:
            wallet_balance = 0.0

        if not nom or not prenom or not email or not password:
            flash("Nom, prénom, email et mot de passe sont requis.", 'danger')
            return redirect(url_for('admin.db_add_user'))
        if User.query.filter_by(email=email).first():
            flash('Cet email existe déjà.', 'danger')
            return redirect(url_for('admin.db_add_user'))

        username = _build_unique_username(prenom, nom)
        user = User(
            username=username, nom=nom, prenom=prenom, email=email, role=role,
            is_approved=is_approved,
            skill_level=round(max(0.0, min(7.0, skill_level)), 2),
            wallet_balance=round(wallet_balance, 2),
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f'Utilisateur {username} créé.', 'success')
        return redirect(url_for('admin.database') + '#users')
    return render_template('admin/db_edit_user.html', user=None, title='Ajouter un utilisateur')


@bp.route('/db/users/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def db_edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        nom    = request.form.get('nom', '').strip()
        prenom = request.form.get('prenom', '').strip()
        email  = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', user.role)
        is_approved = request.form.get('is_approved') == '1'
        try:
            skill_level = float(request.form.get('skill_level', user.skill_level))
        except ValueError:
            skill_level = user.skill_level
        try:
            wallet_balance = float(request.form.get('wallet_balance', user.wallet_balance))
        except ValueError:
            wallet_balance = user.wallet_balance

        if not nom or not prenom or not email:
            flash("Nom, prénom et email sont requis.", 'danger')
            return redirect(url_for('admin.db_edit_user', user_id=user_id))

        existing = User.query.filter_by(email=email).first()
        if existing and existing.id != user_id:
            flash('Cet email existe déjà.', 'danger')
            return redirect(url_for('admin.db_edit_user', user_id=user_id))

        user.nom = nom
        user.prenom = prenom
        user.username = _build_unique_username(prenom, nom, exclude_id=user_id)
        user.email = email
        user.role = role
        user.is_approved = is_approved
        user.skill_level = round(max(0.0, min(7.0, skill_level)), 2)
        user.wallet_balance = round(wallet_balance, 2)
        if password:
            user.set_password(password)
        db.session.commit()
        flash(f'Utilisateur {user.username} mis à jour.', 'success')
        return redirect(url_for('admin.database') + '#users')
    return render_template('admin/db_edit_user.html', user=user, title='Modifier utilisateur')


@bp.route('/db/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def db_delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Impossible de supprimer un administrateur.', 'danger')
        return redirect(url_for('admin.database') + '#users')
    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f'Utilisateur {username} supprimé.', 'success')
    return redirect(url_for('admin.database') + '#users')


# --- Matches ---

@bp.route('/db/matches/<int:match_id>/edit', methods=['GET', 'POST'])
@admin_required
def db_edit_match(match_id):
    match = Match.query.get_or_404(match_id)
    if request.method == 'POST':
        match.location = request.form.get('location', match.location).strip()
        match.status = request.form.get('status', match.status)
        winner_val = request.form.get('winner_team', '')
        match.winner_team = int(winner_val) if winner_val in ('1', '2') else None
        try:
            from datetime import datetime as _dt
            match.date = _dt.strptime(request.form.get('date', ''), '%Y-%m-%d').date()
            match.start_time = _dt.strptime(request.form.get('start_time', ''), '%H:%M').time()
            match.end_time = _dt.strptime(request.form.get('end_time', ''), '%H:%M').time()
        except ValueError:
            flash('Format de date ou heure invalide.', 'danger')
            return redirect(url_for('admin.db_edit_match', match_id=match_id))
        match.required_skill = request.form.get('required_skill', match.required_skill)
        try:
            match.price_per_player = float(request.form.get('price_per_player', match.price_per_player))
        except ValueError:
            pass
        db.session.commit()
        flash(f'Match #{match_id} mis à jour.', 'success')
        return redirect(url_for('admin.database') + '#matches')
    return render_template('admin/db_edit_match.html', match=match, title='Modifier match')


@bp.route('/db/matches/<int:match_id>/delete', methods=['POST'])
@admin_required
def db_delete_match(match_id):
    match = Match.query.get_or_404(match_id)
    db.session.delete(match)
    db.session.commit()
    flash(f'Match #{match_id} supprimé.', 'success')
    return redirect(url_for('admin.database') + '#matches')


# --- MatchPlayers ---

@bp.route('/db/match-players/add', methods=['GET', 'POST'])
@admin_required
def db_add_matchplayer():
    players = User.query.filter_by(role='player', is_approved=True).order_by(User.username).all()
    matches = Match.query.order_by(Match.date.desc()).all()
    if request.method == 'POST':
        try:
            match_id = int(request.form.get('match_id', 0))
            player_id = int(request.form.get('player_id', 0))
        except (TypeError, ValueError):
            flash('Match et joueur sont requis.', 'danger')
            return redirect(url_for('admin.db_add_matchplayer'))

        team_val = request.form.get('team', '')
        team = int(team_val) if team_val in ('1', '2') else None
        payment_status = request.form.get('payment_status', 'pending')

        if MatchPlayer.query.filter_by(match_id=match_id, player_id=player_id).first():
            flash('Ce joueur est déjà inscrit à ce match.', 'danger')
            return redirect(url_for('admin.db_add_matchplayer'))

        mp = MatchPlayer(match_id=match_id, player_id=player_id, team=team, payment_status=payment_status)
        db.session.add(mp)
        db.session.commit()
        flash('Inscription ajoutée.', 'success')
        return redirect(url_for('admin.database') + '#match_players')
    return render_template('admin/db_edit_matchplayer.html', mp=None,
                           players=players, matches=matches, title='Ajouter une inscription')


@bp.route('/db/match-players/<int:mp_id>/edit', methods=['GET', 'POST'])
@admin_required
def db_edit_matchplayer(mp_id):
    mp = MatchPlayer.query.get_or_404(mp_id)
    players = User.query.filter_by(role='player', is_approved=True).order_by(User.username).all()
    matches = Match.query.order_by(Match.date.desc()).all()
    if request.method == 'POST':
        team_val = request.form.get('team', '')
        mp.team = int(team_val) if team_val in ('1', '2') else None
        mp.payment_status = request.form.get('payment_status', mp.payment_status)
        db.session.commit()
        flash('Inscription mise à jour.', 'success')
        return redirect(url_for('admin.database') + '#match_players')
    return render_template('admin/db_edit_matchplayer.html', mp=mp,
                           players=players, matches=matches, title='Modifier inscription')


@bp.route('/db/match-players/<int:mp_id>/delete', methods=['POST'])
@admin_required
def db_delete_matchplayer(mp_id):
    mp = MatchPlayer.query.get_or_404(mp_id)
    db.session.delete(mp)
    db.session.commit()
    flash('Inscription supprimée.', 'success')
    return redirect(url_for('admin.database') + '#match_players')


# --- Transactions ---

@bp.route('/db/transactions/add', methods=['GET', 'POST'])
@admin_required
def db_add_transaction():
    users = User.query.order_by(User.username).all()
    matches = Match.query.order_by(Match.date.desc()).all()
    if request.method == 'POST':
        try:
            user_id = int(request.form.get('user_id', 0))
            amount = float(request.form.get('amount', 0))
        except (TypeError, ValueError):
            flash('Utilisateur et montant sont requis.', 'danger')
            return redirect(url_for('admin.db_add_transaction'))

        tx_type = request.form.get('type', 'manual').strip()
        description = request.form.get('description', '').strip()
        match_id_val = request.form.get('match_id', '')
        match_id = int(match_id_val) if match_id_val else None

        if not description:
            flash('La description est requise.', 'danger')
            return redirect(url_for('admin.db_add_transaction'))

        t = Transaction(user_id=user_id, amount=amount, type=tx_type,
                        description=description, match_id=match_id)
        db.session.add(t)
        db.session.commit()
        flash('Transaction ajoutée.', 'success')
        return redirect(url_for('admin.database') + '#transactions')
    return render_template('admin/db_edit_transaction.html', t=None,
                           users=users, matches=matches, title='Ajouter une transaction')


@bp.route('/db/transactions/<int:t_id>/edit', methods=['GET', 'POST'])
@admin_required
def db_edit_transaction(t_id):
    t = Transaction.query.get_or_404(t_id)
    users = User.query.order_by(User.username).all()
    matches = Match.query.order_by(Match.date.desc()).all()
    if request.method == 'POST':
        try:
            t.amount = float(request.form.get('amount', t.amount))
        except ValueError:
            pass
        t.type = request.form.get('type', t.type).strip()
        t.description = request.form.get('description', t.description).strip()
        match_id_val = request.form.get('match_id', '')
        t.match_id = int(match_id_val) if match_id_val else None
        db.session.commit()
        flash('Transaction mise à jour.', 'success')
        return redirect(url_for('admin.database') + '#transactions')
    return render_template('admin/db_edit_transaction.html', t=t,
                           users=users, matches=matches, title='Modifier transaction')


@bp.route('/db/transactions/<int:t_id>/delete', methods=['POST'])
@admin_required
def db_delete_transaction(t_id):
    t = Transaction.query.get_or_404(t_id)
    db.session.delete(t)
    db.session.commit()
    flash('Transaction supprimée.', 'success')
    return redirect(url_for('admin.database') + '#transactions')


# --- Replacements ---

@bp.route('/db/replacements/<int:r_id>/edit', methods=['GET', 'POST'])
@admin_required
def db_edit_replacement(r_id):
    r = ReplacementRequest.query.get_or_404(r_id)
    if request.method == 'POST':
        r.status = request.form.get('status', r.status)
        db.session.commit()
        flash('Demande de remplacement mise à jour.', 'success')
        return redirect(url_for('admin.database') + '#replacements')
    return render_template('admin/db_edit_replacement.html', r=r, title='Modifier remplacement')


@bp.route('/db/replacements/<int:r_id>/delete', methods=['POST'])
@admin_required
def db_delete_replacement(r_id):
    r = ReplacementRequest.query.get_or_404(r_id)
    db.session.delete(r)
    db.session.commit()
    flash('Demande de remplacement supprimée.', 'success')
    return redirect(url_for('admin.database') + '#replacements')


# --- Proposals ---

@bp.route('/db/proposals/<int:p_id>/edit', methods=['GET', 'POST'])
@admin_required
def db_edit_proposal(p_id):
    p = MatchResultProposal.query.get_or_404(p_id)
    if request.method == 'POST':
        p.status = request.form.get('status', p.status)
        winner_val = request.form.get('winner_team', '')
        if winner_val in ('1', '2'):
            p.winner_team = int(winner_val)
        db.session.commit()
        flash('Proposition mise à jour.', 'success')
        return redirect(url_for('admin.database') + '#proposals')
    return render_template('admin/db_edit_proposal.html', p=p, title='Modifier proposition')


@bp.route('/db/proposals/<int:p_id>/delete', methods=['POST'])
@admin_required
def db_delete_proposal(p_id):
    p = MatchResultProposal.query.get_or_404(p_id)
    db.session.delete(p)
    db.session.commit()
    flash('Proposition supprimée.', 'success')
    return redirect(url_for('admin.database') + '#proposals')