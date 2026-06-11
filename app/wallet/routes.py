from flask import render_template, current_app, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.wallet import bp
from app import db
from app.models import Transaction, Match, MatchPlayer


@bp.route('/')
@login_required
def dashboard():
    transactions = (Transaction.query
                    .filter_by(user_id=current_user.id)
                    .order_by(Transaction.created_at.desc())
                    .all())
    total_spent = sum(tx.amount for tx in transactions if tx.amount < 0)
    return render_template('wallet/dashboard.html',
                           transactions=transactions,
                           total_spent=total_spent,
                           title='Solde')


@bp.route('/qr')
@login_required
def payment_qr():
    match_id = request.args.get('match_id', type=int)
    pending_mp = None
    match = None
    if match_id:
        match = Match.query.get(match_id)
        if match:
            pending_mp = MatchPlayer.query.filter_by(
                match_id=match_id,
                player_id=current_user.id,
                payment_status='pending',
            ).first()
    return render_template('wallet/payment_qr.html',
                           twint_token=current_app.config.get('TWINT_QR_TOKEN', ''),
                           match=match,
                           pending_mp=pending_mp,
                           title='Paiement TWINT')


@bp.route('/confirm-twint/<int:match_id>', methods=['POST'])
@login_required
def confirm_twint(match_id):
    mp = MatchPlayer.query.filter_by(
        match_id=match_id,
        player_id=current_user.id,
        payment_status='pending',
    ).first_or_404()

    match = Match.query.get_or_404(match_id)

    mp.payment_status = 'paid'
    db.session.add(Transaction(
        user_id=current_user.id,
        amount=-match.price_per_player,
        type='match_fee',
        description=f'Paiement TWINT — match #{match.id} ({match.location})',
        match_id=match.id,
    ))
    db.session.commit()

    flash(f'Paiement confirmé ! Votre inscription au match du {match.date.strftime("%d/%m/%Y")} est validée.', 'success')
    return redirect(url_for('matches.match_detail', match_id=match_id))
