import requests
import json
import flask
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
import google.genai as genai
import os
import base64
import uuid
import re
import traceback
from dotenv import load_dotenv
from openai import OpenAI

ai_bp = Blueprint('ai', __name__)
load_dotenv()

nvidia_client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.getenv("NVIDIA_API_KEY")
)



try:
    client = genai.Client(
        vertexai=True,
        api_key=os.environ.get("GOOGLE_CLOUD_API_KEY"),
    )
except Exception:
    client = None

def get_bot_response(user_message):
    systemprompt = (
        "Ты — XAM AI, вежливый и полезный ИИ-ассистент.\n"
        "У тебя есть доступ к внутренним инструментам:\n"
        "- create_post({\"text\": \"текст\"})\n"
        "- get_friends_list()\n"
        "Чтобы вызвать инструмент, верни ответ ТОЛЬКО в формате: [TOOL_CALL: tool_name(args)]\n"
    )
    
    try:
        completion = nvidia_client.chat.completions.create(
            model="moonshotai/kimi-k2.6", # Возвращаем вашу модель!
            messages=[
                {"role": "system", "content": systemprompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.3, # Снижаем фантазию, чтобы она точно выдала скобки
            top_p=1,
            max_tokens=1024,
            timeout=60 
        )
        response_text = completion.choices[0].message.content
    except Exception as e:
        print(f"❌ Ошибка LLM: {e}", flush=True)
        return f"Ошибка LLM: {e}"

    if "[TOOL_CALL:" in response_text:
        print(f"🤖 Kimi вызывает инструмент: {response_text.strip()}", flush=True)
        try:
            match = re.search(r'\[TOOL_CALL:\s*([a-zA-Z0-9_]+)\((.*?)\)\]', response_text)
            if match:
                tool_name = match.group(1).strip()
                tool_args_str = match.group(2).strip()
                
                tool_args = json.loads(tool_args_str) if tool_args_str else {}
                return run_tools(tool_name, tool_args)
            else:
                return "Ошибка: неверный формат вызова инструмента."
        except json.JSONDecodeError:
            return "Ошибка: Kimi сгенерировала невалидный JSON."
        except Exception as e:
            return f"Ошибка инструментов: {e}"
            
    return response_text

@ai_bp.route('/chat', methods=['POST'])
@login_required
def ai_chat_api():
    data = request.get_json()
    user_message = data.get('user_message')
    bot_text = get_bot_response(user_message)
    return jsonify({'response': bot_text})

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

def run_tools(tool_name, tool_args):
    print(f"🛠 Запуск инструмента: {tool_name} с аргументами {tool_args}", flush=True)
    
    if tool_name == 'get_friends_list':
        return bot_get_friends_list()
    elif tool_name == 'create_post':
        return bot_create_post(tool_args.get('text', ''))
    elif tool_name == 'send_comment':
        return bot_send_comment(tool_args.get('post_id'), tool_args.get('text', ''))

    else:
        return 'Неизвестный инструмент'