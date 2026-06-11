from flask import render_template, current_app, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.wallet import bp
from app import db
from app.models import Transaction, Match, MatchPlayer
from datetime import datetime
import re

_MONTHS_FR = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
              'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']


def _fmt_date_fr(dt):
    return f"{dt.day} {_MONTHS_FR[dt.month - 1]} {dt.year}"


def _fmt_month_fr(dt):
    return f"{_MONTHS_FR[dt.month - 1].capitalize()} {dt.year}"


def _parse_tx(tx):
    if ' — ' in tx.description:
        parts = tx.description.split(' — ', 1)
        title = parts[0]
        sub = parts[1]
        m = re.match(r'match #(\d+) \((.+)\)', sub, re.IGNORECASE)
        if m:
            sub = f"Match #{m.group(1)} · {m.group(2)}"
    else:
        title = tx.description
        sub = None
    return {
        'title': title,
        'sub': sub,
        'date_str': _fmt_date_fr(tx.created_at),
        'time_str': tx.created_at.strftime('%H:%M'),
        'amount': tx.amount,
        'is_credit': tx.amount > 0,
    }


@bp.route('/')
@login_required
def dashboard():
    transactions = (Transaction.query
                    .filter_by(user_id=current_user.id)
                    .order_by(Transaction.created_at.desc())
                    .all())

    now = datetime.utcnow()
    total_spent = sum(tx.amount for tx in transactions if tx.amount < 0)
    current_month_spent = sum(
        tx.amount for tx in transactions
        if tx.amount < 0
        and tx.created_at.month == now.month
        and tx.created_at.year == now.year
    )

    groups = {}
    for tx in transactions:
        key = (tx.created_at.year, tx.created_at.month)
        if key not in groups:
            groups[key] = {'label': _fmt_month_fr(tx.created_at), 'items': []}
        groups[key]['items'].append(_parse_tx(tx))

    return render_template('wallet/dashboard.html',
                           transaction_groups=list(groups.values()),
                           has_transactions=bool(transactions),
                           total_spent=total_spent,
                           current_month_spent=current_month_spent,
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
