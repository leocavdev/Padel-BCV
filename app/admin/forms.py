from flask_wtf import FlaskForm
from wtforms import StringField, DateField, TimeField, SelectField, FloatField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Optional

SKILL_CHOICES = [
    ('beginner',     'Débutant'),
    ('intermediate', 'Intermédiaire'),
    ('advanced',     'Avancé'),
    ('expert',       'Expert'),
]

PAYER_CHOICES = [
    ('',          '— Non renseigné —'),
    ('Leonardo',  'Leonardo'),
    ('Withawat',  'Withawat'),
]


class CreateMatchForm(FlaskForm):
    location         = StringField('Lieu / Court', validators=[DataRequired()])
    date             = DateField('Date', validators=[DataRequired()])
    start_time       = TimeField('Heure de début', validators=[DataRequired()])
    end_time         = TimeField('Heure de fin', validators=[DataRequired()])
    required_skill   = SelectField('Niveau minimum requis', choices=SKILL_CHOICES,
                                   validators=[DataRequired()])
    price_per_player = FloatField('Montant de la réservation (CHF)',
                                  validators=[DataRequired(), NumberRange(min=0, max=5000)],
                                  default=78.0)
    paid_by          = SelectField('Payé par', choices=PAYER_CHOICES,
                                   validators=[Optional()], default='')
    submit = SubmitField('Créer le match')


class EditMatchForm(FlaskForm):
    location         = StringField('Lieu / Court', validators=[DataRequired()])
    date             = DateField('Date', validators=[DataRequired()])
    start_time       = TimeField('Heure de début', validators=[DataRequired()])
    end_time         = TimeField('Heure de fin', validators=[DataRequired()])
    required_skill   = SelectField('Niveau minimum requis', choices=SKILL_CHOICES,
                                   validators=[DataRequired()])
    price_per_player = FloatField('Montant de la réservation (CHF)',
                                  validators=[DataRequired(), NumberRange(min=0, max=5000)])
    paid_by          = SelectField('Payé par', choices=PAYER_CHOICES,
                                   validators=[Optional()], default='')
    submit = SubmitField('Enregistrer les modifications')
