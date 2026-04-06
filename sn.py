import flask
from datetime import datetime
import flask_login
import flask_sqlalchemy
from flask import Flask
from flask import render_template
from flask import redirect
from flask import request
from flask import url_for
from flask import flash
from flask import send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_login import UserMixin
from flask_login import login_user
from flask_login import logout_user
from flask_login import login_required
from flask_login import current_user
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash

app = Flask(__name__, static_folder='style', static_url_path='/style')
app.config['SECRET_KEY'] = 'qwerty123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///social.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@app.route('/image/<path:filename>')
def serve_image(filename):
    return send_from_directory('image', filename)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    author = db.relationship('User', backref=db.backref('posts', lazy=True))
    likes = db.relationship('Like', backref='post', lazy=True, cascade="all, delete-orphan")
    comments = db.relationship('Comment', backref='post', lazy=True, cascade="all, delete-orphan", order_by="Comment.timestamp.asc()")

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    
    author = db.relationship('User')


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.route('/')
@login_required
def index():
    posts = Post.query.order_by(Post.timestamp.desc()).all()
    liked_post_ids = [like.post_id for like in Like.query.filter_by(user_id=current_user.id).all()]
    return render_template('index.html', user=current_user, posts=posts, liked_post_ids=liked_post_ids)

@app.route('/new_post', methods=['POST'])
@login_required
def new_post():
    text = request.form.get('content', '').strip()
    if text:
        post = Post(text=text, user_id=current_user.id)
        db.session.add(post)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/like/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    like = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    if like:
        db.session.delete(like)
    else:
        new_like = Like(user_id=current_user.id, post_id=post_id)
        db.session.add(new_like)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/comment/<int:post_id>', methods=['POST'])
@login_required
def comment_post(post_id):
    text = request.form.get('content', '').strip()
    if text:
        comment = Comment(text=text, user_id=current_user.id, post_id=post_id)
        db.session.add(comment)
        db.session.commit()
    return redirect(url_for('index'))


@app.route('/terms')
def terms():
    from flask import send_from_directory
    return send_from_directory(app.root_path, 'Правила пользования ХАМ.pdf')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm = request.form['confirm']

        if username == '' or email == '' or password == '':
            flash('заполните все поля!!!', 'danger')
            return render_template('reg.html')
            
        agree_terms = request.form.get('agree_terms')
        if not agree_terms:
            flash('Вы должны принять пользовательское соглашение', 'danger')
            return render_template('reg.html')

        if len(password) < 6:
            flash('пароль слишком короткий', 'danger')
            return render_template('reg.html')

        if password != confirm:
            flash('пароли не совпадают', 'danger')
            return render_template('reg.html')

        proverka1 = User.query.filter_by(username=username).first()
        if proverka1:
            flash('такой пользователь уже есть', 'danger')
            return render_template('reg.html')

        proverka2 = User.query.filter_by(email=email).first()
        if proverka2:
            flash('такой email уже есть', 'danger')
            return render_template('reg.html')

        novy_user = User()
        novy_user.username = username
        novy_user.email = email
        novy_user.password = generate_password_hash(password)
        db.session.add(novy_user)
        db.session.commit()

        flash('аккаунт создан! теперь войди', 'success')
        return redirect(url_for('login'))

    return render_template('reg.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        login_id = request.form['login_id']
        password = request.form['password']

        user = User.query.filter_by(username=login_id).first()

        if user == None:
            user = User.query.filter_by(email=login_id).first()

        if user == None:
            flash('неверный логин или пароль', 'danger')
            return render_template('auth.html')

        if check_password_hash(user.password, password) == False:
            flash('неверный логин или пароль', 'danger')
            return render_template('auth.html')

        login_user(user)
        return redirect(url_for('index'))

    return render_template('auth.html')


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0')


