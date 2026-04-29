import sqlite3
import os

db_path = 'instance/social.db'
if not os.path.exists(db_path):
    db_path = 'social.db'

if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("ALTER TABLE profile ADD COLUMN timezone_offset INTEGER DEFAULT 0")
        conn.commit()
        conn.close()
        print(f"--- Колонка timezone_offset успешно добавлена в {db_path} ---")
    except Exception as e:
        print(f"Ошибка при обновлении БД: {e}")
