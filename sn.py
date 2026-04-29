import flask
from datetime import datetime
import flask_login
import flask_sqlalchemy
from flask import Flask, render_template, redirect, request, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
import os
import uuid
from aiassis import ai_bp, get_bot_response
from flask_socketio import SocketIO, join_room
import re
from datetime import timedelta

app = Flask(__name__, static_folder='style', static_url_path='/style')
app.register_blueprint(ai_bp)
socketio = SocketIO(app)
app.config['SECRET_KEY'] = 'qwerty123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///social.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['UPLOAD_IMAGE'] = 'C:/Users/redfy/Documents/social-network/instance/images'
app.config['UPLOAD_VIDEO'] = 'C:/Users/redfy/Documents/social-network/instance/videos'

@app.template_filter('localized_time')
def localized_time(dt, user_tz_offset=0):
    if not dt:
        return ""
    # Прибавляем смещение в часах
    local_dt = dt + timedelta(hours=user_tz_offset)
    return local_dt

# база данных sql

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@app.before_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def is_online(self):
        if self.last_seen:
            return (datetime.utcnow() - self.last_seen).total_seconds() < 300 # 5 минут
        return False

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    photo = db.Column(db.String(256), nullable=True)
    video = db.Column(db.String(256), nullable=True)
    is_edited = db.Column(db.Boolean, default=False)
    
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
    likes = db.relationship('CommentLike', backref='comment', lazy=True, cascade="all, delete-orphan")
    
    author = db.relationship('User')

class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(256), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    author = db.relationship('User', backref=db.backref('photos', lazy=True))

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(256), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    author = db.relationship('User', backref=db.backref('videos', lazy=True))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(256), nullable=True)
    isai_image = db.Column(db.Boolean, default=False)
    video = db.Column(db.String(256), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_friend = db.Column(db.Boolean, default=False)
    is_ai = db.Column(db.Boolean, default=False)
    
    sender = db.relationship('User', foreign_keys=[sender_id], backref=db.backref('sent_messages', lazy=True))
    recipient = db.relationship('User', foreign_keys=[receiver_id], backref=db.backref('received_messages', lazy=True))

class Profile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    bio = db.Column(db.Text, nullable=True)
    avatar = db.Column(db.String(256), nullable=True)
    city = db.Column(db.String(128))
    timezone_offset = db.Column(db.Integer, default=0) # Смещение от UTC
    registration_date = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('profile', uselist=False))

class Friends(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    friend_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')

class CommentLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=False)

def proccess_mentions(text):
    mentions = re.findall(r'@(\w+)', text)
    for username in mentions:
        target_user = User.query.filter_by(username=username).first()
        if target_user:
            link = url_for('profile', user_id=target_user.id)
            text = text.replace(f'@{username}', f'<a href="{link}" class="mention">@{username}</a>')
    return text

@socketio.on('connect')
def on_connect():
    user_id = current_user.id
    join_room(user_id)
    print(f"User {user_id} connected and joined room {user_id}")

@socketio.on('typing')
def handle_typing(data):
    socketio.emit('display_typing', {'user_id': current_user.id}, to=data['user_id'])

@socketio.on('stop_typing')
def handle_stop_typing(data):
    socketio.emit('display_stop_typing', {'user_id': current_user.id}, to=data['user_id'])

@socketio.on('message')
def handle_message(data):
    text = data['text']
    user_id = data['user_id']
    if text:
            new_msg = Message()
            new_msg.sender_id = current_user.id
            new_msg.receiver_id = data['user_id']
            new_msg.text = data['text']
            db.session.add(new_msg)
            db.session.commit()
            friend = Friends.query.filter_by(user_id=current_user.id, friend_id=user_id).first()
            bot = User.query.filter_by(username="XAM_AI").first()
            if data['user_id'] == bot.id:
                bot_response = get_bot_response(text)
                new_msg.is_ai = True
                new_msg.sender_id = current_user.id
                bot_msg = Message()
                bot_msg.sender_id = user_id
                bot_msg.receiver_id = current_user.id
                bot_msg.is_ai = True
                if isinstance(bot_response, dict) and 'image_url' in bot_response:
                    bot_msg.text = bot_response.get('text')
                    bot_msg.image = bot_response.get('image_url')
                    bot_msg.is_ai_image = True
                    socketio.emit('display_message', {bot.id: bot_response}, to=current_user.id)
                else:
                    bot_msg.text = bot_response
                    socketio.emit('display_message', {bot.id: bot_response}, to=current_user.id)
                db.session.add(bot_msg)
                db.session.commit()
            else:
                new_msg.is_ai = False
            if friend:
                new_msg.is_friend = True
            else:
                new_msg.is_friend = False
    socketio.emit('display_message', {current_user.id: data['text']}, to=data['user_id'])

@socketio.on('comment')
def handle_comment(data):
    text = data.get('text', '').strip()
    text = proccess_mentions(text)
    post_id = data.get('post_id')
    if text and post_id:
        comment = Comment(text=text, user_id=current_user.id, post_id=post_id)
        db.session.add(comment)
        db.session.commit()
        
        # Отправляем обновленные данные всем в комнате этого поста
        socketio.emit('display_comment', {
            'post_id': post_id,
            'text': text,
            'author': current_user.username,
            'timestamp': datetime.utcnow().strftime('%H:%M')
        }, room=f"post_{post_id}")
    if "@XAM_AI" in text:
        bot = User.query.filter_by(username="XAM_AI").first()
        reply = get_bot_response(text)
        reply = f"@{current_user.username}, {reply}"
        comment_by_bot = Comment(text=reply, user_id=bot.id, post_id=post_id)
        db.session.add(comment_by_bot)
        db.session.commit()
        socketio.emit('display_comment', {
            'post_id': post_id,
            'text': reply,
            'author': bot.username,
            'timestamp': datetime.utcnow().strftime('%H:%M')
        }, room=f"post_{post_id}")

@socketio.on('like_comment')
def handle_like_comment(data):
    comment_id = data.get('comment_id')
    if comment_id:
        comment = Comment.query.get(comment_id)
        if comment:
            like = CommentLike.query.filter_by(user_id=current_user.id, comment_id=comment_id).first()
            if like:
                db.session.delete(like)
                db.session.commit()
                socketio.emit('comment_like_update', {
                    'comment_id': comment_id,
                    'count': len(comment.likes),
                    'user_id': current_user.id,
                    'action': 'unliked'
                }, room=f"post_{comment.post_id}")
            else:
                like = CommentLike(user_id=current_user.id, comment_id=comment_id)
                db.session.add(like)
                db.session.commit()
                socketio.emit('comment_like_update', {
                    'comment_id': comment_id,
                    'count': len(comment.likes),
                    'user_id': current_user.id,
                    'action': 'liked'
                }, room=f"post_{comment.post_id}")

@socketio.on('join_post')
def on_join_post(data):
    post_id = data.get('post_id')
    if post_id:
        join_room(f"post_{post_id}")
        print(f"User joining room for post {post_id}")


@app.before_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@app.route('/') # главная страница
@login_required
def index():
    posts = Post.query.order_by(Post.timestamp.desc()).all()
    liked_post_ids = [like.post_id for like in Like.query.filter_by(user_id=current_user.id).all()]
    return render_template('index.html', user=current_user, posts=posts, liked_post_ids=liked_post_ids)

@app.route('/new_post', methods=['POST']) # посты с видео и изображениями
@login_required
def new_post():
    text = request.form.get('content', '').strip()
    text = text[:250]
    file = request.files.get('image')
    video = request.files.get('video')
    image_filename = None
    video_filename = None
    if file and file.filename != '':
        ext = file.filename.split('.')[-1].lower()
        if ext in ['jpg', 'jpeg', 'png', 'gif']:
            image_filename = str(uuid.uuid4()) + "." + ext
            file.save(os.path.join(app.config['UPLOAD_IMAGE'], image_filename))
    
    if video and video.filename != '':
        ext = video.filename.split('.')[-1].lower()
        if ext in ['mp4', 'avi', 'mov', 'mkv']:
            video_filename = str(uuid.uuid4()) + "." + ext
            video.save(os.path.join(app.config['UPLOAD_VIDEO'], video_filename))

    if text or image_filename or video_filename:
        post = Post(text=text, user_id=current_user.id, photo=image_filename, video=video_filename)
        db.session.add(post)
        db.session.commit()
    return redirect(request.referrer or url_for('index'))

@app.route('/post/edit/<int:post_id>', methods=['POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id:
        flash('Вы не можете редактировать чужой пост!', 'danger')
        return redirect(url_for('index'))
    
    new_text = request.form.get('content', '').strip()
    if new_text and new_text != post.text:
        post.text = new_text[:250]
        post.is_edited = True
        db.session.commit()
        flash('Пост обновлен!', 'success')
    return redirect(request.referrer or url_for('index'))

@app.route('/post/delete/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id and current_user.username != 'admin':
        flash('У вас нет прав для удаления этого поста!', 'danger')
        return redirect(url_for('index'))
    
    # Удаляем связанные файлы (фото/видео), если нужно
    db.session.delete(post)
    db.session.commit()
    flash('Пост удален!', 'success')
    return redirect(request.referrer or url_for('index'))

@app.route('/like/<int:post_id>', methods=['POST']) # лайки под постами
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

@app.route('/comment/<int:post_id>', methods=['POST']) # комментарии под постами
@login_required
def comment_post(post_id):
    text = request.form.get('content', '').strip()
    if text:
        comment = Comment(text=text, user_id=current_user.id, post_id=post_id)
        db.session.add(comment)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/image/<path:filename>') # картинки
def serve_image(filename):
    return send_from_directory(app.config['UPLOAD_IMAGE'], filename)

@app.route('/video/<path:filename>') # видео
def serve_video(filename):
    return send_from_directory(app.config['UPLOAD_VIDEO'], filename)

@app.route('/branding/<path:filename>') # брендинг
def serve_branding(filename):
    return send_from_directory(os.path.join(app.root_path, 'image'), filename)
    


@app.route('/terms') # правила пользования
def terms():
    from flask import send_from_directory
    return send_from_directory(app.root_path, 'Правила пользования ХАМ.pdf')


@app.route('/about') # о нас
def about():
    return render_template('about.html', user=current_user)


@app.route('/register', methods=['GET', 'POST']) # регистрация
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        email_pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
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
        
        if not re.match(email_pattern, email):
            flash('Введите корректный email (например, name@examle.com или .ru)!', 'danger')
            return render_template('reg.html')

        novy_user = User()
        novy_user.username = username
        novy_user.email = email
        novy_user.password = generate_password_hash(password)
        db.session.add(novy_user)
        db.session.commit()
        novyy_profiel = Profile()
        novyy_profiel.user_id = novy_user.id
        db.session.add(novyy_profiel)
        db.session.commit()

        flash('аккаунт создан! теперь войди', 'success')
        return redirect(url_for('login'))

    return render_template('reg.html')


@app.route('/login', methods=['GET', 'POST']) # вход
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

# апроуты ссылок
@app.route('/logout')
def logout():
    if current_user.is_authenticated:
        # Устанавливаем время последнего визита на 10 минут назад, 
        # чтобы статус сразу сменился на "Не в сети"
        from datetime import timedelta
        current_user.last_seen = datetime.now() - timedelta(minutes=10)
        db.session.commit()
    logout_user()
    return redirect(url_for('login'))

@app.route('/friends')
@login_required
def friends():
    friendships = Friends.query.filter(((Friends.user_id == current_user.id) | (Friends.friend_id == current_user.id)) & (Friends.status == 'accepted')).all()
    friends_list = []
    for f in friendships:
        target_id = f.friend_id if f.user_id == current_user.id else f.user_id
        user_obj = db.session.get(User, target_id)
        if user_obj:
            friends_list.append(user_obj)
    pending_requests = Friends.query.filter_by(friend_id=current_user.id, status='pending').all()
    requests_sender = []
    for r in pending_requests:
        sender = db.session.get(User, r.user_id)
        if sender:
            requests_sender.append({'id': r.id, 'user': sender, 'user_id': sender.id})
    return render_template('friends.html', user=current_user, friends=friends_list, requests=requests_sender)

@app.route('/messages')
@login_required
def messages():
    return render_template('messages.html', user=current_user)

@app.route('/messages/<int:user_id>', methods=['GET', 'POST']) # отправление сообщений и отображение переписки
@login_required
def messages_userid(user_id):
    if request.method == 'POST':
        text = request.form.get('message', '').strip()
        if text:
            new_msg = Message()
            new_msg.sender_id = current_user.id
            new_msg.receiver_id = user_id
            new_msg.text = text
            file = request.files.get('image')
            video = request.files.get('video')
            if file:
                new_msg.image = file.filename
                file.save(os.path.join(app.config['UPLOAD_IMAGE'], file.filename))
                if User.query.filter_by(username="XAM_AI").first() == True:
                    new_msg.isai_image = True
            if video:
                new_msg.video = video.filename
                video.save(os.path.join(app.config['UPLOAD_VIDEO'], video.filename))
            friend = Friends.query.filter_by(user_id=current_user.id, friend_id=user_id).first()
            if friend:
                new_msg.friend = True
            else:
                new_msg.friend = False
            db.session.add(new_msg)
            db.session.commit()
    messages = Message.query.filter_by(sender_id=current_user.id, receiver_id=user_id).all()
    messages = messages + Message.query.filter_by(sender_id=user_id, receiver_id=current_user.id).all()
    messages = sorted(messages, key=lambda x: x.timestamp)
    return render_template('messages.html', user=current_user, messages=messages)

@app.route('/profile/<int:user_id>') # профиль
@login_required
def profile(user_id):
    u = User.query.get_or_404(user_id)
    p = Post.query.filter_by(user_id=user_id).order_by(Post.timestamp.desc()).all()
    return render_template('profile.html', user=current_user, other_user=u, posts=p)

@app.route('/profile/<int:user_id>/friends') # отображение друзей в профиле
@login_required
def profile_friends(user_id):
    u = User.query.get_or_404(user_id)
    f = Friends.query.filter_by(user_id=user_id).all()
    return render_template('profile.html', user=current_user, other_user=u, friends=f)

@app.route('/profile/<int:user_id>/edit', methods=['GET', 'POST']) # редактирование профиля
@login_required
def profile_edit(user_id):
    u = User.query.get_or_404(user_id)
    if u.id != current_user.id:
        flash('Вы не можете редактировать профиль другого пользователя!', 'danger')
        return redirect(url_for('profile', user_id=user_id))
    if request.method == 'POST':
        u.name = request.form.get('name')
        u.bio = request.form.get('bio')
        db.session.add(u)
        db.session.commit()
        flash('Профиль успешно обновлен!', 'success')
    return render_template('profile.html', user=current_user, other_user=u)

@app.route('/friends/add/<int:user_id>', methods=['POST']) # система добавления друзей
@login_required
def friend_add(user_id):
    target_user = User.query.get_or_404(user_id)
    
    # Запрет добавления в друзья системных аккаунтов
    if target_user.username in ["XAM_AI", "Поддержка"]:
        flash('Этот аккаунт нельзя добавить в друзья.', 'danger')
        return redirect(request.referrer or url_for('profile', user_id=user_id))

    f = Friends()
    existing = Friends.query.filter_by(user_id=current_user.id, friend_id=user_id).first()
    if existing:
        existing.status = 'pending'
        db.session.add(existing)
    else:
        new_request = Friends()
        new_request.user_id = current_user.id
        new_request.friend_id = user_id
        db.session.add(new_request)
    db.session.commit()
    return redirect(request.referrer or url_for('profile', user_id=user_id))

@app.route('/friends/remove/<int:user_id>', methods=['POST']) # система удаления друзей
@login_required
def friend_remove(user_id):
    f = Friends.query.filter(((Friends.user_id == current_user.id) & (Friends.friend_id == user_id)) | ((Friends.user_id == user_id) & (Friends.friend_id == current_user.id))).first()

    if f:
        db.session.delete(f)
        db.session.commit()
    return redirect(url_for('profile', user_id=user_id))

@app.route('/friends/accept/<int:user_id>', methods=['POST']) # принятие заявки в друзья
@login_required
def friend_accept(user_id):
    f = Friends.query.filter_by(user_id=user_id, friend_id=current_user.id).first()
    f.status = 'accepted'
    db.session.add(f)
    db.session.commit()
    return redirect(request.referrer or url_for('profile', user_id=user_id))

@app.route('/friends/decline/<int:user_id>', methods=['POST']) # отклонение заявки в друзья
@login_required
def friend_decline(user_id):
    f = Friends.query.filter_by(user_id=user_id, friend_id=current_user.id).first()
    db.session.delete(f)
    db.session.commit()
    return redirect(request.referrer or url_for('friends'))

@app.route('/settings/change_password', methods=['POST'])
@login_required
def change_password():
    old_password = request.form.get('old_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if not old_password or not new_password or not confirm_password:
        flash('Заполните все поля!', 'danger')
        return redirect(url_for('settings'))

    if not check_password_hash(current_user.password, old_password):
        flash('Старый пароль введен неверно!', 'danger')
        return redirect(url_for('settings'))

    if new_password != confirm_password:
        flash('Новые пароли не совпадают!', 'danger')
        return redirect(url_for('settings'))

    if len(new_password) < 6:
        flash('Новый пароль слишком короткий (минимум 6 символов)!', 'danger')
        return redirect(url_for('settings'))

    current_user.password = generate_password_hash(new_password)
    db.session.commit()
    flash('Пароль успешно изменен!', 'success')
    return redirect(url_for('settings'))


@app.route('/settings/update_profile', methods=['POST'])
@login_required
def update_profile():
    if not current_user.profile:
        profile = Profile(user_id=current_user.id)
        db.session.add(profile)
    else:
        profile = current_user.profile

    # Обновление текстовых данных
    profile.bio = request.form.get('bio', '')
    profile.city = request.form.get('city', '')
    profile.timezone_offset = int(request.form.get('timezone_offset', 0))

    # Обработка аватара
    file = request.files.get('avatar')
    if file and file.filename != '':
        ext = file.filename.split('.')[-1].lower()
        if ext in ['jpg', 'jpeg', 'png', 'gif']:
            filename = str(uuid.uuid4()) + "." + ext
            file.save(os.path.join(app.config['UPLOAD_IMAGE'], filename))
            profile.avatar = filename

    db.session.commit()
    flash('Профиль успешно обновлен!', 'success')
    return redirect(url_for('settings'))

@app.route('/groups') # группы (в будущем)
@login_required
def groups():
    return render_template('group.html', user=current_user)

@app.route('/settings') # настройки (пока не доделаны)
@login_required
def settings():
    return render_template('settings.html', user=current_user)

@app.route('/search') # поиск людей
@login_required
def search():
    query = request.args.get('q', '').strip()
    result = []
    if query:
        result = User.query.filter(User.username.ilike(f'%{query}%')).all()
    return render_template('search.html', user=current_user, query=query, result=result)

@app.route('/search/user/<int:user_id>')
@login_required
def search_user(user_id):
    u = User.query.get_or_404(user_id)
    return render_template('search.html', user=current_user, other_user=u)

if __name__ == '__main__': # запуск сайта
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            admin_user = User(
                username="admin", 
                email="admin@xam.ru", 
                password=generate_password_hash("123123")
            )
            db.session.add(admin_user)
            db.session.commit()
            print("--- Аккаунт admin создан! ---")
        if not User.query.filter_by(username="XAM_AI").first():
            ai_user = User(
                username="XAM_AI", 
                email="ai@xam.ru", 
                password=generate_password_hash("ai_secret_123")
            )
            db.session.add(ai_user)
            db.session.commit()
            print("--- Аккаунт XAM_AI создан! ---")
        if not User.query.filter_by(username="Поддержка").first():
            support_user = User(
                username="Поддержка", 
                email="support@xam.ru", 
                password=generate_password_hash("support_secret_123")
            )
            db.session.add(support_user)
            db.session.commit()
            print("--- Аккаунт Поддержка создан! ---")
    app.run(debug=True, host='0.0.0.0')