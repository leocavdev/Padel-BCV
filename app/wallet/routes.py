from flask import render_template, current_app
from flask_login import login_required, current_user
from app.wallet import bp
from app.models import Transaction


@bp.route('/')
@login_required
def dashboard():
    transactions = (Transaction.query
                    .filter_by(user_id=current_user.id)
                    .order_by(Transaction.created_at.desc())
                    .all())
    return render_template('wallet/dashboard.html',
                           transactions=transactions,
                           title='Solde')


@bp.route('/qr')
@login_required
def payment_qr():
    return render_template('wallet/payment_qr.html',
                           twint_token=current_app.config.get('TWINT_QR_TOKEN', ''),
                           title='Paiement TWINT')
