import requests
import json
import flask
from flask import Blueprint, request, jsonify
from flask_login import login_required

ai_bp = Blueprint('ai', __name__)

@ai_bp.route('/chat', methods=['POST'])
@login_required
def ai():
    data = request.get_json()
    user_message = data.get('user_message')
    systemprompt = ("Ты — XAM AI Ассистент. Ты можешь помогать пользователю с сайтом. Тебе доступны инструменты: get_friends_list() — возвращает список друзей. create_post(text) — создает новый пост. Если тебе нужно использовать инструмент, ответь СТРОГО в формате: [TOOL_CALL: имя_функции(параметры)]. Если инструмент не нужен — просто отвечай текстом.")
    response = requests.post('http://localhost:11434/api/generate', json={
        'model': 'gemma4:e4b',
        'prompt': user_message,
        'system': systemprompt,
        'stream': False
    })
    return jsonify({'response': response.json()['response']})

def get_bot_response(user_text):
    systemprompt = ("Ты — XAM AI Ассистент. Ты можешь помогать пользователю с сайтом. Тебе доступны инструменты: get_friends_list() — возвращает список друзей. create_post(text) — создает новый пост. Если тебе нужно использовать инструмент, ответь СТРОГО в формате: [TOOL_CALL: имя_функции(параметры)]. Если инструмент не нужен — просто отвечай текстом.")
    response = requests.post('http://localhost:11434/api/generate', json={
        'model': 'gemma4:e4b',
        'prompt': user_text,
        'system': systemprompt,
        'stream': False
    })
    return response.json()['response']

def bot_get_friends_list():
    from sn import db, Friends, User
    friends = Friends.query.filter_by(user_id=current_user.id, status='accepted').all()
    names = [db.session.get(User, f.friend_id).username for f in friends]
    return f"Список друзей: {', '.join(names)}"

def bot_create_post(text):
    from sn import db, Post
    post = Post(text=text, user_id=current_user.id)
    db.session.add(post)
    db.session.commit()
    return 'Пост создан'

def bot_send_comment(post_id, text):
    from sn import db, Comment
    comment = Comment(text=text, user_id=current_user.id, post_id=post_id)
    db.session.add(comment)
    db.session.commit()
    return 'Комментарий создан'

def run_tools(tool_name, tool_args):
    if tool_name == 'get_friends_list': # ИИ проверяет есть ли у пользователя друзья
        return bot_get_friends_list()
    elif tool_name == 'create_post': # ИИ создает пост по запросу пользователя
        return bot_create_post(tool_args['text'])
    elif tool_name == 'send_comment': # ИИ отправляет комментарий по запросу пользователя
        return bot_send_comment(tool_args['post_id'], tool_args['text'])
    else:
        return 'Неизвестный инструмент, переспроси пользователя - что именно ему нужно'