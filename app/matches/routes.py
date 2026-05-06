from datetime import datetime
from zoneinfo import ZoneInfo
from flask import render_template, redirect, url_for, flash, request

_CH = ZoneInfo('Europe/Zurich')
from flask_login import login_required, current_user
from app import db
from app.matches import bp
import json
from app.models import Match, MatchPlayer, Transaction, User, ReplacementRequest, MatchResultProposal, SKILL_LEVELS, SKILL_ORDER

_DAY_NAMES = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
_MONTH_NAMES = ['jan', 'fév', 'mars', 'avr', 'mai', 'juin',
                'juil', 'août', 'sep', 'oct', 'nov', 'déc']


@bp.route('/')
@login_required
def list_matches():
    now_ch = datetime.now(_CH)
    today = now_ch.date()
    now_time = now_ch.time()

    def _is_future():
        return db.or_(Match.date > today, db.and_(Match.date == today, Match.start_time > now_time))

    def _is_past_not_cancelled():
        return db.and_(
            db.or_(Match.date < today, db.and_(Match.date == today, Match.start_time <= now_time)),
            Match.status != 'cancelled'
        )

    registered_matches = []
    registered_ids = []
    incoming_requests = []
    if not current_user.is_admin:
        user_regs = MatchPlayer.query.filter_by(player_id=current_user.id).all()
        registered_ids = [reg.match_id for reg in user_regs]
        if registered_ids:
            registered_matches = (Match.query
                                  .filter(Match.id.in_(registered_ids))
                                  .filter(Match.status.in_(['open', 'confirmed']))
                                  .filter(_is_future())
                                  .order_by(Match.date, Match.start_time)
                                  .all())
        incoming_requests = (ReplacementRequest.query
                             .filter_by(replacement_id=current_user.id, status='pending')
                             .all())
    open_matches = (Match.query
                    .filter_by(status='open')
                    .filter(_is_future())
                    .filter(~Match.id.in_(registered_ids) if registered_ids else True)
                    .order_by(Match.date, Match.start_time)
                    .all())
    confirmed_matches = (Match.query
                         .filter_by(status='confirmed')
                         .filter(_is_future())
                         .filter(~Match.id.in_(registered_ids) if registered_ids else True)
                         .order_by(Match.date, Match.start_time)
                         .all())
    past_matches = (Match.query
                    .filter(db.or_(
                        _is_past_not_cancelled(),
                        Match.status == 'completed'
                    ))
                    .order_by(Match.date.desc(), Match.start_time.desc())
                    .all())
    cancelled_matches = (Match.query
                         .filter_by(status='cancelled')
                         .order_by(Match.date.desc(), Match.start_time.desc())
                         .all())
    now_str = f'{_DAY_NAMES[today.weekday()]} {today.day} {_MONTH_NAMES[today.month - 1]} {today.year}'
    return render_template('matches/list.html',
                           registered_matches=registered_matches,
                           open_matches=open_matches,
                           confirmed_matches=confirmed_matches,
                           past_matches=past_matches,
                           cancelled_matches=cancelled_matches,
                           incoming_requests=incoming_requests,
                           now=now_str,
                           title='Matchs')


@bp.route('/history')
@login_required
def history():
    today = datetime.now(_CH).date()
    all_matches = (Match.query
                   .join(MatchPlayer)
                   .filter(MatchPlayer.player_id == current_user.id)
                   .order_by(Match.date.asc(), Match.start_time.asc())
                   .all())
    upcoming_matches = [m for m in all_matches if m.date >= today]
    past_matches = sorted([m for m in all_matches if m.date < today],
                          key=lambda m: (m.date, m.start_time), reverse=True)
    return render_template('matches/history.html',
                           upcoming_matches=upcoming_matches,
                           past_matches=past_matches,
                           total=len(all_matches),
                           title='Historique des matchs')


@bp.route('/<int:match_id>')
@login_required
def match_detail(match_id):
    match = Match.query.get_or_404(match_id)
    today = datetime.now(_CH).date()
    registration = None
    eligible_replacements = []
    pending_request = None
    incoming_request = None
    pending_proposal = None
    proposal_my_team = None
    proposal_proposer_team = None
    if not current_user.is_admin:
        registration = MatchPlayer.query.filter_by(
            match_id=match_id, player_id=current_user.id
        ).first()
        if registration and match.status in ('open', 'confirmed'):
            pending_request = ReplacementRequest.query.filter_by(
                match_id=match_id, requester_id=current_user.id, status='pending'
            ).first()
            if not pending_request:
                registered_ids = {mp.player_id for mp in match.players}
                required_idx = SKILL_ORDER.index(match.required_skill)
                eligible_replacements = [
                    p for p in User.query.filter_by(role='player').order_by(User.username).all()
                    if p.id not in registered_ids
                    and SKILL_ORDER.index(p.skill_category_key) >= required_idx
                ]
        incoming_request = ReplacementRequest.query.filter_by(
            match_id=match_id, replacement_id=current_user.id, status='pending'
        ).first()
        if registration and match.status == 'confirmed' and match.date <= today:
            pending_proposal = MatchResultProposal.query.filter_by(
                match_id=match_id, status='pending'
            ).first()
            if pending_proposal:
                assignments = pending_proposal.get_team_assignments()
                proposal_my_team = assignments.get(current_user.id)
                proposal_proposer_team = assignments.get(pending_proposal.proposed_by_id)
    return render_template('matches/detail.html', match=match,
                           registration=registration,
                           eligible_replacements=eligible_replacements,
                           pending_request=pending_request,
                           incoming_request=incoming_request,
                           pending_proposal=pending_proposal,
                           proposal_my_team=proposal_my_team,
                           proposal_proposer_team=proposal_proposer_team,
                           today=today,
                           title='Détail du match')


@bp.route('/<int:match_id>/join', methods=['POST'])
@login_required
def join_match(match_id):
    if current_user.is_admin:
        flash("Les administrateurs ne peuvent pas s'inscrire aux matchs.", 'warning')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    match = Match.query.get_or_404(match_id)

    if match.status != 'open':
        flash("Ce match n'est plus disponible.", 'danger')
        return redirect(url_for('matches.list_matches'))

    if match.date < datetime.now(_CH).date():
        flash("Impossible de s'inscrire à un match passé.", 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    current_count = MatchPlayer.query.filter_by(match_id=match_id).count()
    if current_count >= 4:
        flash('Le match est complet.', 'danger')
        return redirect(url_for('matches.list_matches'))

    # Skill level gate
    player_idx   = SKILL_ORDER.index(current_user.skill_category_key)
    required_idx = SKILL_ORDER.index(match.required_skill)
    if player_idx < required_idx:
        flash(
            f"Votre niveau ({current_user.skill_label}) n'atteint pas le niveau requis "
            f'({match.required_skill_label}).',
            'danger',
        )
        return redirect(url_for('matches.match_detail', match_id=match_id))

    if MatchPlayer.query.filter_by(match_id=match_id, player_id=current_user.id).first():
        flash('Vous êtes déjà inscrit à ce match.', 'warning')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    use_wallet = request.form.get('use_wallet') == 'true'

    if use_wallet:
        if current_user.wallet_balance < match.price_per_player:
            flash(
                f'Solde insuffisant. Rechargez votre portefeuille '
                f'({match.price_per_player:.2f} CHF requis, solde actuel : {current_user.wallet_balance:.2f} CHF).',
                'danger',
            )
            return redirect(url_for('matches.match_detail', match_id=match_id))
        current_user.wallet_balance -= match.price_per_player
        db.session.add(Transaction(
            user_id=current_user.id,
            amount=-match.price_per_player,
            type='match_fee',
            description=f'Paiement — match #{match.id} ({match.location})',
            match_id=match.id,
        ))
        payment_status = 'paid'
    else:
        payment_status = 'pending'

    mp = MatchPlayer(match_id=match_id, player_id=current_user.id, payment_status=payment_status)
    db.session.add(mp)

    if current_count + 1 >= 4:
        match.status = 'confirmed'

    db.session.commit()

    if payment_status == 'paid':
        if match.status == 'confirmed':
            flash(
                f'Inscription confirmée ! {match.price_per_player:.2f} CHF déduits. '
                f'Le match est complet (4/4) et confirmé !',
                'success',
            )
        else:
            flash(f'Inscription confirmée ! {match.price_per_player:.2f} CHF déduits de votre portefeuille.', 'success')
        return redirect(url_for('matches.match_detail', match_id=match_id))
    else:
        flash('Inscription enregistrée. Scannez le QR code pour finaliser votre paiement TWINT.', 'info')
        return redirect(url_for('wallet.payment_qr', match_id=match_id))


@bp.route('/<int:match_id>/pay-pending', methods=['POST'])
@login_required
def pay_pending(match_id):
    mp = MatchPlayer.query.filter_by(
        match_id=match_id,
        player_id=current_user.id,
        payment_status='pending',
    ).first_or_404()

    match = Match.query.get_or_404(match_id)

    if match.date < datetime.now(_CH).date():
        flash("Impossible d'effectuer une action sur un match passé.", 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    if current_user.wallet_balance < match.price_per_player:
        flash(
            f'Solde insuffisant ({current_user.wallet_balance:.2f} CHF disponibles, '
            f'{match.price_per_player:.2f} CHF requis).',
            'danger',
        )
        return redirect(url_for('matches.match_detail', match_id=match_id))

    current_user.wallet_balance -= match.price_per_player
    mp.payment_status = 'paid'
    db.session.add(Transaction(
        user_id=current_user.id,
        amount=-match.price_per_player,
        type='match_fee',
        description=f'Paiement — match #{match.id} ({match.location})',
        match_id=match.id,
    ))
    db.session.commit()
    flash(f'Paiement confirmé ! {match.price_per_player:.2f} CHF déduits de votre portefeuille.', 'success')
    return redirect(url_for('matches.match_detail', match_id=match_id))


@bp.route('/<int:match_id>/request-replacement', methods=['POST'])
@login_required
def request_replacement(match_id):
    match = Match.query.get_or_404(match_id)

    if match.date < datetime.now(_CH).date():
        flash("Impossible d'effectuer une action sur un match passé.", 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    if match.status not in ('open', 'confirmed'):
        flash('Vous ne pouvez pas quitter ce match.', 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    mp = MatchPlayer.query.filter_by(match_id=match_id, player_id=current_user.id).first()
    if not mp:
        flash("Vous n'êtes pas inscrit à ce match.", 'warning')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    existing = ReplacementRequest.query.filter_by(
        match_id=match_id, requester_id=current_user.id, status='pending'
    ).first()
    if existing:
        flash('Vous avez déjà une demande de remplacement en attente pour ce match.', 'warning')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    replacement_id = request.form.get('replacement_id', type=int)
    if not replacement_id:
        flash('Vous devez sélectionner un remplaçant.', 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    replacement = User.query.get(replacement_id)
    if not replacement or replacement.is_admin:
        flash('Remplaçant invalide.', 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    if MatchPlayer.query.filter_by(match_id=match_id, player_id=replacement_id).first():
        flash('Ce joueur est déjà inscrit à ce match.', 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    required_idx = SKILL_ORDER.index(match.required_skill)
    if SKILL_ORDER.index(replacement.skill_category_key) < required_idx:
        flash(
            f"Le niveau de {replacement.username} ({replacement.skill_label}) est insuffisant "
            f"pour ce match ({match.required_skill_label}).",
            'danger',
        )
        return redirect(url_for('matches.match_detail', match_id=match_id))

    rr = ReplacementRequest(
        match_id=match_id,
        requester_id=current_user.id,
        replacement_id=replacement_id,
        status='pending',
    )
    db.session.add(rr)
    db.session.commit()
    flash(
        f'Demande envoyée à {replacement.username}. '
        f'Vous resterez inscrit jusqu\'à son acceptation.',
        'info',
    )
    return redirect(url_for('matches.match_detail', match_id=match_id))


@bp.route('/<int:match_id>/cancel-replacement', methods=['POST'])
@login_required
def cancel_replacement(match_id):
    rr = ReplacementRequest.query.filter_by(
        match_id=match_id, requester_id=current_user.id, status='pending'
    ).first_or_404()
    db.session.delete(rr)
    db.session.commit()
    flash('Demande de remplacement annulée.', 'info')
    return redirect(url_for('matches.match_detail', match_id=match_id))


@bp.route('/<int:match_id>/respond-replacement/<int:request_id>', methods=['POST'])
@login_required
def respond_replacement(match_id, request_id):
    rr = ReplacementRequest.query.get_or_404(request_id)

    if rr.match_id != match_id or rr.replacement_id != current_user.id or rr.status != 'pending':
        flash('Demande invalide.', 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    action = request.form.get('action')
    match = Match.query.get_or_404(match_id)

    if match.date < datetime.now(_CH).date():
        flash("Impossible d'effectuer une action sur un match passé.", 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    if action == 'decline':
        db.session.delete(rr)
        db.session.commit()
        flash('Vous avez refusé la demande de remplacement.', 'info')
        return redirect(url_for('matches.list_matches'))

    if action == 'accept':
        if match.status not in ('open', 'confirmed'):
            db.session.delete(rr)
            db.session.commit()
            flash("Ce match n'est plus disponible.", 'danger')
            return redirect(url_for('matches.list_matches'))

        mp = MatchPlayer.query.filter_by(match_id=match_id, player_id=rr.requester_id).first()
        if not mp:
            db.session.delete(rr)
            db.session.commit()
            flash("Le joueur n'est plus inscrit à ce match.", 'warning')
            return redirect(url_for('matches.list_matches'))

        if MatchPlayer.query.filter_by(match_id=match_id, player_id=current_user.id).first():
            db.session.delete(rr)
            db.session.commit()
            flash('Vous êtes déjà inscrit à ce match.', 'warning')
            return redirect(url_for('matches.match_detail', match_id=match_id))

        payment_method = request.form.get('payment_method', 'wallet')
        requester = rr.requester

        if payment_method == 'twint':
            if mp.payment_status == 'paid':
                requester.wallet_balance += match.price_per_player
                db.session.add(Transaction(
                    user_id=requester.id,
                    amount=match.price_per_player,
                    type='refund',
                    description=f'Remboursement pour remplacement — match #{match.id} ({match.location})',
                    match_id=match.id,
                ))
            db.session.add(MatchPlayer(match_id=match_id, player_id=current_user.id, payment_status='pending'))
            db.session.delete(mp)
            db.session.delete(rr)
            db.session.commit()
            flash(
                f'Vous remplacez {requester.username} dans le match du '
                f'{match.date.strftime("%d/%m/%Y")} à {match.location}. '
                f'Procédez au paiement TWINT pour confirmer votre place.',
                'info',
            )
            return redirect(url_for('wallet.payment_qr', match_id=match_id))

        if current_user.wallet_balance < match.price_per_player:
            flash(
                f'Solde insuffisant pour accepter ce remplacement. '
                f'Rechargez votre portefeuille ({match.price_per_player:.2f} CHF requis, '
                f'solde actuel : {current_user.wallet_balance:.2f} CHF).',
                'danger',
            )
            return redirect(url_for('matches.match_detail', match_id=match_id))

        if mp.payment_status == 'paid':
            requester.wallet_balance += match.price_per_player
            db.session.add(Transaction(
                user_id=requester.id,
                amount=match.price_per_player,
                type='refund',
                description=f'Remboursement pour remplacement — match #{match.id} ({match.location})',
                match_id=match.id,
            ))

        current_user.wallet_balance -= match.price_per_player
        db.session.add(Transaction(
            user_id=current_user.id,
            amount=-match.price_per_player,
            type='match_fee',
            description=f'Paiement remplacement — match #{match.id} ({match.location})',
            match_id=match.id,
        ))

        db.session.add(MatchPlayer(match_id=match_id, player_id=current_user.id, payment_status='paid'))
        db.session.delete(mp)
        db.session.delete(rr)
        db.session.commit()
        flash(
            f'Vous remplacez {requester.username} dans le match du '
            f'{match.date.strftime("%d/%m/%Y")} à {match.location}. '
            f'{match.price_per_player:.2f} CHF déduits de votre portefeuille.',
            'success',
        )
        return redirect(url_for('matches.match_detail', match_id=match_id))

    flash('Action invalide.', 'danger')
    return redirect(url_for('matches.match_detail', match_id=match_id))


@bp.route('/<int:match_id>/propose-result', methods=['POST'])
@login_required
def propose_result(match_id):
    if current_user.is_admin:
        return redirect(url_for('admin.manage_match', match_id=match_id))

    match = Match.query.get_or_404(match_id)
    today = datetime.now(_CH).date()

    if match.status != 'confirmed' or match.date > today:
        flash("Impossible de proposer un résultat pour ce match.", 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    mp = MatchPlayer.query.filter_by(match_id=match_id, player_id=current_user.id).first()
    if not mp:
        flash("Vous n'êtes pas inscrit à ce match.", 'warning')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    existing = MatchResultProposal.query.filter_by(match_id=match_id, status='pending').first()
    if existing:
        flash('Une proposition de résultat est déjà en attente.', 'warning')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    winner_team = request.form.get('winner_team', '')
    if winner_team not in ('1', '2'):
        flash('Sélectionnez une équipe gagnante valide.', 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    team_assignments = {}
    for player_mp in match.players:
        team_val = request.form.get(f'team_{player_mp.player_id}')
        if team_val in ('1', '2'):
            team_assignments[player_mp.player_id] = int(team_val)

    if len(team_assignments) != len(match.players):
        flash('Assignez tous les joueurs à une équipe.', 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    proposal = MatchResultProposal(
        match_id=match_id,
        proposed_by_id=current_user.id,
        winner_team=int(winner_team),
        team_assignments=json.dumps(team_assignments),
        status='pending',
    )
    db.session.add(proposal)
    db.session.commit()
    flash('Résultat proposé. En attente de confirmation par un adversaire.', 'info')
    return redirect(url_for('matches.match_detail', match_id=match_id))


@bp.route('/<int:match_id>/cancel-result-proposal/<int:proposal_id>', methods=['POST'])
@login_required
def cancel_result_proposal(match_id, proposal_id):
    proposal = MatchResultProposal.query.get_or_404(proposal_id)
    if proposal.match_id != match_id or proposal.proposed_by_id != current_user.id or proposal.status != 'pending':
        flash('Proposition invalide.', 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))
    proposal.status = 'rejected'
    db.session.commit()
    flash('Proposition annulée.', 'info')
    return redirect(url_for('matches.match_detail', match_id=match_id))


@bp.route('/<int:match_id>/confirm-result/<int:proposal_id>', methods=['POST'])
@login_required
def confirm_result(match_id, proposal_id):
    if current_user.is_admin:
        return redirect(url_for('admin.manage_match', match_id=match_id))

    proposal = MatchResultProposal.query.get_or_404(proposal_id)
    if proposal.match_id != match_id or proposal.status != 'pending':
        flash('Proposition invalide.', 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    mp = MatchPlayer.query.filter_by(match_id=match_id, player_id=current_user.id).first()
    if not mp:
        flash("Vous n'êtes pas inscrit à ce match.", 'warning')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    assignments = proposal.get_team_assignments()
    proposer_team = assignments.get(proposal.proposed_by_id)
    my_team = assignments.get(current_user.id)

    if proposer_team is None or my_team is None or my_team == proposer_team:
        flash("Seul un joueur de l'équipe adverse peut confirmer le résultat.", 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    match = Match.query.get_or_404(match_id)
    if match.status != 'confirmed':
        flash('Ce match ne peut plus être modifié.', 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    for player_mp in match.players:
        team_val = assignments.get(player_mp.player_id)
        if team_val:
            player_mp.team = team_val

    match.winner_team = proposal.winner_team
    match.status = 'completed'

    for player_mp in match.players:
        if player_mp.team is not None:
            player_mp.player.update_skill(won=(player_mp.team == proposal.winner_team))

    proposal.status = 'confirmed'
    db.session.commit()
    flash('Résultat confirmé ! Les niveaux ont été mis à jour.', 'success')
    return redirect(url_for('matches.match_detail', match_id=match_id))


@bp.route('/<int:match_id>/reject-result/<int:proposal_id>', methods=['POST'])
@login_required
def reject_result(match_id, proposal_id):
    if current_user.is_admin:
        return redirect(url_for('admin.manage_match', match_id=match_id))

    proposal = MatchResultProposal.query.get_or_404(proposal_id)
    if proposal.match_id != match_id or proposal.status != 'pending':
        flash('Proposition invalide.', 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    mp = MatchPlayer.query.filter_by(match_id=match_id, player_id=current_user.id).first()
    if not mp:
        flash("Vous n'êtes pas inscrit à ce match.", 'warning')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    assignments = proposal.get_team_assignments()
    proposer_team = assignments.get(proposal.proposed_by_id)
    my_team = assignments.get(current_user.id)

    if current_user.id != proposal.proposed_by_id and my_team == proposer_team:
        flash("Seul un joueur de l'équipe adverse peut contester le résultat.", 'danger')
        return redirect(url_for('matches.match_detail', match_id=match_id))

    proposal.status = 'rejected'
    db.session.commit()
    flash('Résultat contesté. Un nouveau résultat peut être proposé.', 'info')
    return redirect(url_for('matches.match_detail', match_id=match_id))
