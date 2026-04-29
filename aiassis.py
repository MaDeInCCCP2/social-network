import requests
import json
import flask
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
import google.genai as genai
from google.genai import types
import os
import base64
from dotenv import load_dotenv
from openai import OpenAI

ai_bp = Blueprint('ai', __name__)

load_dotenv()

nvidia_client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.getenv("NVIDIA_API_KEY")
)

# Клиент Google остается в коде, но пока не используется в функциях
try:
    client = genai.Client(
        vertexai=True,
        api_key=os.environ.get("GOOGLE_CLOUD_API_KEY"),
    )
except Exception:
    client = None

API_BASE = "https://api.krea.ai"

def get_bot_response(user_message):
    systemprompt = (
        'Ты — XAM AI Ассистент. '
        'Доступны инструменты: '
        'get_friends_list(), '
        'create_post({"text": "..."}), '
        'send_comment({"post_id": ID, "text": "..."}), '
        'generate_image({"text": "описание для рисования"}). '
        'Если пользователь просит что-то нарисовать или создать картинку, '
        'пиши СТРОГО: [TOOL_CALL: generate_image({"text": "промпт на английском"})]. '
        'Аргументы — только валидный JSON. Иначе — просто текст.'
    )
    try:
        completion = nvidia_client.chat.completions.create(
            model="moonshotai/kimi-k2-instruct-0905",
            messages=[
                {"role": "system", "content": systemprompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.5,
            top_p=1,
            max_tokens=1024,
            timeout=60 
        )
        response_text = completion.choices[0].message.content
    except Exception as e:
        return f"Ошибка LLM (NVIDIA): {e}"

    if "[TOOL_CALL:" in response_text:
        try:
            tool_call = response_text.split("[TOOL_CALL:")[1].split("]")[0]
            tool_name = tool_call.split("(")[0].strip()
            tool_args_str = tool_call.split("(")[1].split(")")[0].strip()
            tool_args = json.loads(tool_args_str) if tool_args_str else {}
            return run_tools(tool_name, tool_args)
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

def generate_image(prompt):
    import time
    api_key = os.getenv('IMAGE_API_KEY') 
    if not api_key:
        return "Ошибка: Не найден IMAGE_API_KEY в .env"
        
    try:
        url = f"{API_BASE}/generate/image/google/nano-banana-pro"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "prompt": prompt,
            "width": 512,
            "height": 512,
            "num_images": 1,
            "aspect_ratio": "1:1"
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code != 200:
            return f"Ошибка Krea (POST {response.status_code}): {response.text}"
            
        job_id = response.json().get("job_id")
        if not job_id:
            return "Ошибка: Сервер не вернул job_id"
            
        for _ in range(30): 
            time.sleep(2) 
            try:
                status_resp = requests.get(
                    f"{API_BASE}/jobs/{job_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=10
                )
                if status_resp.status_code == 200:
                    result_data = status_resp.json()
                    status = result_data.get("status")
                    if status == "completed":
                        urls = result_data.get("result", {}).get("urls", [])
                        return urls[0] if urls else "Ошибка: Список URL пуст"
                    elif status == "failed":
                        return "Ошибка: Генерация на сервере провалена"
            except Exception:
                pass
                    
        return "Ошибка: Превышено время ожидания картинки"
        
    except Exception as e:
        return f"Ошибка генерации (Krea): {e}"

def server_error():
    if genai.errors.server_error == True:
        return 'Сервер временно перегружен, попробуйте позже'
    if genai.errors.rate_limit_error == True:
        return 'Сервер временно перегружен, попробуйте позже'
    if genai.types.GenerateContentResponse.prompt_feedback.block_reason == True:
        return 'Я не могу ответить на этот запрос'

def run_tools(tool_name, tool_args):
    if tool_name == 'get_friends_list':
        return bot_get_friends_list()
    elif tool_name == 'create_post':
        return bot_create_post(tool_args.get('text', ''))
    elif tool_name == 'send_comment':
        return bot_send_comment(tool_args.get('post_id'), tool_args.get('text', ''))
    elif tool_name == 'generate_image':
        img_url = generate_image(tool_args.get('text', ''))
        if img_url:
            return {"image_url": img_url, "text": f"Изображение создано: {tool_args.get('text')}"}
        return "Извините, не удалось сгенерировать изображение."
    else:
        return 'Неизвестный инструмент'