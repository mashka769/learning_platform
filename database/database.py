import pyodbc


def get_db_connection():
    try:
        # Для Windows Authentication
        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=LAPTOP-J8R45QVQ;'
            'DATABASE=learning_platform_db;'
            'Trusted_Connection=yes;'  # Это для Windows Auth
        )
        print("✅ Успешное подключение через pyodbc!")
        return conn
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None


def test_connection():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()

        # Проверяем пользователей
        cursor.execute("SELECT user_id, username FROM users")
        users = cursor.fetchall()
        print(f"👥 Найдено пользователей: {len(users)}")
        for user in users:
            print(f" - ID: {user[0]}, Имя: {user[1]}")

        # Проверяем статьи
        cursor.execute("SELECT article_id, title FROM articles")
        articles = cursor.fetchall()
        print(f"📚 Найдено статей: {len(articles)}")
        for article in articles:
            print(f" - ID: {article[0]}, Заголовок: {article[1]}")

        conn.close()
    else:
        print("Не удалось подключиться к БД")


if __name__ == "__main__":
    test_connection()