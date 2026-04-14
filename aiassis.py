import requests
import json
import flask
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
import google.genai as genai
import os
from dotenv import load_dotenv
ai_bp = Blueprint('ai', __name__)

load_dotenv()

@ai_bp.route('/chat', methods=['POST'])
@login_required
def ai():
    systemprompt = 'Ты — XAM AI Ассистент. Доступны: get_friends_list(), create_post({"text": "..."}), send_comment({"post_id": ID, "text": "..."}). Если нужен инструмент, пиши СТРОГО: [TOOL_CALL: имя_функции(JSON)]. Аргументы — только валидный JSON в двойных кавычках или пусто. Пример: [TOOL_CALL: create_post({"text": "Привет"})]. Иначе — просто текст.'
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    data = request.get_json()
    user_message = data.get('user_message')
    response = client.models.generate_content(
        model='gemini-3-flash-preview',

        contents=user_message,
        config={
            "system_instruction": systemprompt
        }
    )
    return jsonify({'response': response.text})
# def ai():
#    data = request.get_json()
#    user_message = data.get('user_message')
#    systemprompt = ("Ты — XAM AI Ассистент. Ты можешь помогать пользователю с сайтом. Тебе доступны инструменты: get_friends_list() — возвращает список друзей. create_post(text) — создает новый пост. Если тебе нужно использовать инструмент, ответь СТРОГО в формате: [TOOL_CALL: имя_функции(параметры)]. Если инструмент не нужен — просто отвечай текстом.")
#    response = requests.post('http://localhost:11434/api/generate', json={
#        'model': 'gemma4:e4b',
#        'prompt': user_message,
#        'system': systemprompt,
#        'stream': False
#    })
#    return jsonify({'response': response.json()['response']})

def get_bot_response(user_text):
    response = None
    systemprompt = 'Ты — XAM AI Ассистент. Доступны: get_friends_list(), create_post({"text": "..."}), send_comment({"post_id": ID, "text": "..."}). Если нужен инструмент, пиши СТРОГО: [TOOL_CALL: имя_функции(JSON)]. Аргументы — только валидный JSON в двойных кавычках или пусто. Пример: [TOOL_CALL: create_post({"text": "Привет"})]. Иначе — просто текст.'
    models_to_try = ['gemma-4-31b-it', 'gemini-3-flash-preview', 'gemma-4-26b-a4b-it']
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model = model_name,
                contents=user_text,
                config={
                    "system_instruction": systemprompt
                }
            )
            break
        except Exception as e:
            print(f"Модель {model_name} сейчас не отвечает: {e}")
            continue
    if not response:
        return "Просим прощения - сервера временно перегружены, попробуйте позже"
    if "[TOOL_CALL:" in response.text:
        tool_call = response.text.split("[TOOL_CALL:")[1].split("]")[0]
        tool_name = tool_call.split("(")[0].strip()
        tool_args = tool_call.split("(")[1].split(")")[0].strip()
        if tool_args:
            tool_args = json.loads(tool_args)
        else:
            tool_args = {}
        return run_tools(tool_name, tool_args)
    return response.text

# def get_bot_response(user_text):
#    systemprompt = ("Ты — XAM AI Ассистент. Ты можешь помогать пользователю с сайтом. Тебе доступны инструменты: get_friends_list() — возвращает список друзей. create_post(text) — создает новый пост. Если тебе нужно использовать инструмент, ответь СТРОГО в формате: [TOOL_CALL: имя_функции(параметры)]. Если инструмент не нужен — просто отвечай текстом.")
#    response = requests.post('http://localhost:11434/api/generate', json={
#        'model': 'gemma4:e4b',
#        'prompt': user_text,
#        'system': systemprompt,
#        'stream': False
#    })
#    return response.json()['response']

def bot_get_friends_list():
    from sn import app, db, Friends, User
    with app.app_context():
        friends = Friends.query.filter_by(user_id=current_user.id, status='accepted').all()
        names = [db.session.get(User, f.friend_id).username for f in friends]
    return f"Список друзей: {', '.join(names)}"

def bot_create_post(text):
    from sn import app, db, Post
    with app.app_context():
        post = Post(text=text, user_id=current_user.id)
        db.session.add(post)
        db.session.commit()
    return 'Пост создан'

def bot_send_comment(post_id, text):
    from sn import app, db, Comment
    with app.app_context():
        comment = Comment(text=text, user_id=current_user.id, post_id=post_id)
        db.session.add(comment)
        db.session.commit()
    return 'Комментарий создан'

def server_error():
    if genai.errors.server_error == True:
        return 'Сервер временно перегружен, попробуйте позже'
    if genai.errors.rate_limit_error == True:
        return 'Сервер временно перегружен, попробуйте позже'
    if genai.types.GenerateContentResponse.prompt_feedback.block_reason == True:
        return 'Я не могу ответить на этот запрос'

def run_tools(tool_name, tool_args):
    if tool_name == 'get_friends_list': # ИИ проверяет есть ли у пользователя друзья
        return bot_get_friends_list()
    elif tool_name == 'create_post': # ИИ создает пост по запросу пользователя
        return bot_create_post(tool_args['text'])
    elif tool_name == 'send_comment': # ИИ отправляет комментарий по запросу пользователя
        return bot_send_comment(tool_args['post_id'], tool_args['text'])
    else:
        return 'Неизвестный инструмент, переспроси пользователя - что именно ему нужно'