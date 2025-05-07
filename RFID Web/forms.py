from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired

class TagForm(FlaskForm):
    rfid = StringField('RFID', validators=[DataRequired()])
    label = StringField('Label', validators=[DataRequired()])
    submit = SubmitField('Add RFID')
