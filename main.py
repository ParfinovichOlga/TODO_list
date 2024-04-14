from flask import Flask, render_template, request, url_for, redirect, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
from flask_bootstrap import Bootstrap5
from flask_wtf import FlaskForm
from wtforms import PasswordField, EmailField, SubmitField, StringField, BooleanField, DateField
from wtforms.validators import DataRequired, Email, Length
from sqlalchemy.orm import relationship
from datetime import datetime as dt

app = Flask(__name__)
bootstrap = Bootstrap5(app)
app.config['SECRET_KEY'] = 'secret-key'

# Connect to DB
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy()
db.init_app(app)


# Configure Flask-Login's Login Manager
login_manager = LoginManager()
login_manager.init_app(app)


# WTforms
class RegisterForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired()])
    email = EmailField("Email", validators=[Email(), DataRequired()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    submit = SubmitField(label="Sign me up")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")


# Create a user_loader callback
@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)


# Create tables for adding users, lists and tasks to-do to db
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(100))
    lists = relationship('ListTODO', back_populates='author')


class ListTODO(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    author_id = db.Column(db.Integer, db.ForeignKey(User.id))
    author = relationship('User', back_populates='lists')
    tasks = relationship('Task', back_populates='parent_list')


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    done = db.Column(db.Boolean, nullable=False)
    description = db.Column(db.Text, nullable=False)
    tasks_list = db.Column(db.Integer, db.ForeignKey(ListTODO.id))
    parent_list = relationship('ListTODO', back_populates='tasks')
    deadline = db.Column(db.Date)


with app.app_context():
    db.create_all()


@app.route('/')
def home():
    lists_of_tasks = None
    if not current_user.is_anonymous:
        lists_of_tasks = db.session.execute(db.select(ListTODO).where(ListTODO.author_id == current_user.id)).scalars()
    return render_template('index.html', lists=lists_of_tasks)


@app.route('/register', methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        hash_and_salted_password = generate_password_hash(
            request.form.get('password'),
            method='pbkdf2:sha256',
            salt_length=8
        )
        new_user = User(
            email=request.form.get('email'),
            name=request.form.get('name'),
            password=hash_and_salted_password,
        )
        if db.session.execute(db.select(User).where(User.email == new_user.email)).scalar():
            flash("This email already exists")
        else:
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            return redirect(url_for('home'))
    return render_template('register.html', form=form)


@app.route('/login', methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = request.form.get('email')
        password = request.form.get('password')

        user = db.session.execute(db.select(User).where(User.email == email)).scalar()
        
        if not user:
            flash("That email does not exist, please try again.")
            return redirect(url_for('login'))

        elif not check_password_hash(user.password, password):
            flash("Invalid email or password, please try again.")
            return render_template('login.html', form=form)

        else:
            login_user(user)
            return redirect(url_for('home'))

    return render_template('login.html', form=form)


@app.route('/logout')
def logout():
    logout_user()
    return render_template('index.html')


@app.route('/new-list', methods=['GET', 'POST'])
@login_required
def create_list():
    if request.method == 'POST':
        new_list = ListTODO(

            name=f'My to-do list {dt.today().strftime("%Y/%m/%d")}',
            author=current_user
        )
        db.session.add(new_list)
        db.session.commit()
        new_task = Task(
            done=False,
            deadline=None,
            description=request.form.get('description'),
            parent_list=new_list

        )
        db.session.add(new_task)
        db.session.commit()
        return render_template('create-tasks.html', data=new_list)
    return render_template('make-list.html')


@app.route('/all_task/<int:list_id>', methods=['GET'])
def all_task(list_id):
    required_list = db.session.execute(db.select(ListTODO).where(ListTODO.id == list_id)).scalar()
    return render_template('create-tasks.html', data=required_list)


@app.route('/add_task/<int:list_id>', methods=['POST'])
def add_task(list_id):
    new_task = Task(
        done=False,
        deadline=None,
        description=request.form.get('next_task'),
        parent_list=db.session.execute(db.select(ListTODO).where(ListTODO.id == list_id)).scalar()

    )
    db.session.add(new_task)
    db.session.commit()
    return render_template('create-tasks.html', data=new_task.parent_list)


@app.route('/update_list/<int:list_id>', methods=['GET', 'POST'])
def update_list(list_id):
    list_to_update = db.session.execute(db.select(ListTODO).where(ListTODO.id == list_id)).scalar()
    if request.form.get('name') is not None:
        list_to_update.name = request.form.get('name')
    tasks_done = request.form.getlist('done')
    tasks_to_update = [task.id for task in list_to_update.tasks if task.done == 0]
    if tasks_done:
        for task in tasks_done:
            task_to_complete = db.session.execute(db.select(Task).where(Task.id == task)).scalar()
            task_to_complete.done = True

    due_to_dates = request.form.getlist('deadline')
    descriptions = request.form.getlist('description')

    for date in due_to_dates:
        index = due_to_dates.index(date)
        task_to_update = db.session.execute(db.select(Task).where(Task.id == tasks_to_update[index])).scalar()
        task_to_update.description = descriptions[index]
        if date != "":
            due_to_date = dt.strptime(date, "%Y-%m-%d")
            task_to_update.deadline = due_to_date

    db.session.commit()
    progress = True
    for task in list_to_update.tasks:
        if task.done == 0:
            progress = False
    return render_template('create-tasks.html', data=list_to_update, completed=progress)


@app.route('/all_lists', methods=['GET'])
@login_required
def all_lists():
    lists = db.session.execute(db.select(ListTODO).where(ListTODO.author_id == current_user.id)).scalars()
    return render_template('all-lists.html', lists=lists)


@app.route('/delete_list/<int:list_id>', methods=['GET'])
def delete_list(list_id):
    deleted_list = db.session.execute(db.select(ListTODO).where(ListTODO.id == list_id)).scalar()
    db.session.delete(deleted_list)
    db.session.commit()
    return redirect(url_for('all_lists'))


if __name__ == '__main__':
    app.run(debug=True)