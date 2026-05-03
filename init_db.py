import os
from app import create_app, db
from app.models import User


def generate_payment_qr(app):
    qr_path = os.path.join(app.root_path, 'static', 'img', 'qr_payment.png')
    os.makedirs(os.path.dirname(qr_path), exist_ok=True)
    if os.path.exists(qr_path):
        return
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(app.config['PAYMENT_QR_DATA'])
        qr.make(fit=True)
        img = qr.make_image(fill_color='#2d6a4f', back_color='white')
        img.save(qr_path)
        print(f'  QR code generated: {qr_path}')
    except ImportError:
        print('  [!] qrcode not installed. Run: pip install qrcode[pil]')


def init():
    app = create_app()
    with app.app_context():
        db.create_all()
        print('Tables created.')

        if not User.query.filter_by(email='admin@padelbcv.com').first():
            admin = User(username='admin', email='admin@padelbcv.com', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('Admin created  →  admin@padelbcv.com  /  admin123')
        else:
            print('Admin already exists.')

        generate_payment_qr(app)
        print('Done — run: python run.py')


if __name__ == '__main__':
    init()
