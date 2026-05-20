from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError
from app.models import User


class LoginForm(FlaskForm):
    email       = StringField('Email', validators=[DataRequired(), Email()])
    password    = PasswordField('Mot de passe', validators=[DataRequired()])
    remember_me = BooleanField('Se souvenir de moi')
    submit      = SubmitField('Se connecter')


class RegisterForm(FlaskForm):
    nom              = StringField('Nom', validators=[DataRequired(), Length(1, 64)])
    prenom           = StringField('Prénom', validators=[DataRequired(), Length(1, 64)])
    email            = StringField('Email privé (non ASBCV)', validators=[DataRequired(), Email()])
    password         = PasswordField('Mot de passe', validators=[DataRequired(), Length(6, 128)])
    confirm_password = PasswordField('Confirmer le mot de passe',
                                     validators=[DataRequired(), EqualTo('password',
                                                 message='Les mots de passe ne correspondent pas.')])
    submit = SubmitField("S'inscrire")

    def validate_email(self, field):
        if User.query.filter_by(email=field.data).first():
            raise ValidationError('Cet email est déjà enregistré.')
