from sn import app, db, User
from werkzeug.security import generate_password_hash

def update_database():
    with app.app_context():
        print("Создание таблиц...")
        db.create_all()
        
        # Проверка и создание системных аккаунтов
        system_users = [
            {
                "username": "admin",
                "email": "admin@xam.ru",
                "password": "123123"
            },
            {
                "username": "XAM_AI",
                "email": "ai@xam.ru",
                "password": "ai_secret_123"
            },
            {
                "username": "Поддержка",
                "email": "support@xam.ru",
                "password": "support_secret_123"
            }
        ]
        
        for user_data in system_users:
            user = User.query.filter_by(username=user_data["username"]).first()
            if not user:
                print(f"--- Создание аккаунта {user_data['username']} ---")
                new_user = User(
                    username=user_data["username"],
                    email=user_data["email"],
                    password=generate_password_hash(user_data["password"])
                )
                db.session.add(new_user)
                db.session.commit()
            else:
                print(f"--- Аккаунт {user_data['username']} уже существует ---")
        
        # Очистка случайных связей с системными аккаунтами
        print("Очистка некорректных связей...")
        system_usernames = ["XAM_AI", "Поддержка"]
        system_ids = [u.id for u in User.query.filter(User.username.in_(system_usernames)).all()]
        
        if system_ids:
            from sn import Friends
            deleted = db.session.query(Friends).filter(
                (Friends.user_id.in_(system_ids)) | (Friends.friend_id.in_(system_ids))
            ).delete(synchronize_session=False)
            db.session.commit()
            if deleted:
                print(f"--- Удалено {deleted} лишних связей с системными аккаунтами ---")

        print("База данных успешно обновлена!")

if __name__ == '__main__':
    update_database()
