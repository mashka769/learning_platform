from flask import Flask, render_template, session, redirect, url_for, request
from auth.routes import auth_bp
from admin.routes import admin_bp
import pyodbc

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Регистрируем blueprint'ы
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)


# Функция подключения к БД
def get_db_connection():
    try:
        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=LAPTOP-J8R45QVQ;'
            'DATABASE=learning_platform_db;'
            'Trusted_Connection=yes;'
        )
        return conn
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return None


# Проверка авторизации
def is_authenticated():
    return 'user_id' in session


def check_and_award_achievements(user_id):

    conn = get_db_connection()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            SELECT COUNT(DISTINCT article_id) FROM learning_progress 
            WHERE user_id = ? AND progress_type_id = 1
        """, user_id)
        articles_read = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(DISTINCT test_id) FROM learning_progress 
            WHERE user_id = ? AND progress_type_id = 2
        """, user_id)
        tests_completed = cursor.fetchone()[0]

        print(f"Отладка достижений для пользователя {user_id}:")
        print(f"Прочитано статей: {articles_read}")
        print(f"Пройдено тестов: {tests_completed}")

        cursor.execute("SELECT * FROM achievements ORDER BY achievement_id")
        all_achievements = cursor.fetchall()

        for achievement in all_achievements:
            achievement_id, name, description, icon, condition_type, condition_value = achievement

            condition_met = False

            if condition_type == 'articles_read':
                condition_met = articles_read >= condition_value
                print(f"Проверка '{name}': {articles_read} >= {condition_value} = {condition_met}")
            elif condition_type == 'tests_passed':
                condition_met = tests_completed >= condition_value
                print(f"Проверка '{name}': {tests_completed} >= {condition_value} = {condition_met}")
            elif condition_type == 'score_threshold':
                condition_met = check_score_threshold(user_id, condition_value)
                print(f"Проверка '{name}': порог {condition_value}% = {condition_met}")

            if condition_met:
                cursor.execute("""
                    SELECT * FROM user_achievements 
                    WHERE user_id = ? AND achievement_id = ?
                """, user_id, achievement_id)

                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO user_achievements (user_id, achievement_id, earned_at)
                        VALUES (?, ?, GETDATE())
                    """, user_id, achievement_id)
                    print(f"Присвоено достижение: {name} (ID: {achievement_id})")
                else:
                    print(f"Достижение '{name}' уже есть у пользователя")
            else:
                print(f"Условие не выполнено для '{name}'")

        conn.commit()

    except Exception as e:
        print(f"Ошибка при проверке достижений: {e}")
    finally:
        conn.close()


def check_score_threshold(user_id, threshold):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT TOP 1 1 FROM test_results 
            WHERE user_id = ? AND (score * 100.0 / max_score) >= ?
        """, user_id, threshold)

        result = cursor.fetchone() is not None
        return result

    except Exception as e:
        print(f"Ошибка при проверке результатов тестов: {e}")
        return False
    finally:
        conn.close()


@app.route('/')
def index():
    if not is_authenticated():
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Считаем УНИКАЛЬНЫЕ пройденные статьи (а не попытки)
    cursor.execute("""
        SELECT COUNT(DISTINCT article_id) FROM learning_progress 
        WHERE user_id = ? AND progress_type_id = 1
    """, session['user_id'])
    articles_read = cursor.fetchone()[0]

    # Считаем УНИКАЛЬНЫЕ пройденные тесты (а не попытки)
    cursor.execute("""
        SELECT COUNT(DISTINCT test_id) FROM learning_progress 
        WHERE user_id = ? AND progress_type_id = 2
    """, session['user_id'])
    tests_completed = cursor.fetchone()[0]

    # Считаем достижения
    cursor.execute("""
        SELECT COUNT(*) FROM user_achievements 
        WHERE user_id = ?
    """, session['user_id'])
    achievements_count = cursor.fetchone()[0]

    conn.close()

    return render_template('index.html',
                           username=session['username'],
                           articles_read=articles_read,
                           tests_completed=tests_completed,
                           achievements_count=achievements_count)


@app.route('/articles')
def articles():
    if not is_authenticated():
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Получаем все опубликованные статьи
    cursor.execute("""
        SELECT a.article_id, a.title, a.content, c.name as category, 
               d.level_name as difficulty, a.reading_time_minutes
        FROM articles a
        JOIN categories c ON a.category_id = c.category_id
        JOIN difficulty_levels d ON a.difficulty_level_id = d.level_id
        WHERE a.is_published = 1
        ORDER BY a.article_id
    """)

    articles_list = cursor.fetchall()

    # Получаем ID прочитанных статей для текущего пользователя
    cursor.execute("""
        SELECT DISTINCT article_id FROM learning_progress 
        WHERE user_id = ? AND progress_type_id = 1
    """, session['user_id'])

    read_articles = [row[0] for row in cursor.fetchall()]

    conn.close()

    return render_template('articles.html',
                           articles=articles_list,
                           read_articles=read_articles,
                           username=session['username'])


@app.route('/article/<int:article_id>')
def article_detail(article_id):
    if not is_authenticated():
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Получаем полную информацию о статье
    cursor.execute("""
        SELECT a.article_id, a.title, a.content, c.name as category, 
               d.level_name as difficulty, a.reading_time_minutes,
               u.username as author
        FROM articles a
        JOIN categories c ON a.category_id = c.category_id
        JOIN difficulty_levels d ON a.difficulty_level_id = d.level_id
        JOIN users u ON a.author_id = u.user_id
        WHERE a.article_id = ? AND a.is_published = 1
    """, article_id)

    article = cursor.fetchone()

    # Проверяем, прочитана ли статья - ИСПРАВЛЕННЫЙ ЗАПРОС
    cursor.execute("""
        SELECT TOP 1 1 FROM learning_progress 
        WHERE user_id = ? AND article_id = ? AND progress_type_id = 1
    """, session['user_id'], article_id)

    is_read = cursor.fetchone() is not None

    conn.close()

    if not article:
        return "Статья не найдена", 404

    return render_template('article_detail.html',
                           article=article,
                           is_read=is_read,
                           username=session['username'])


@app.route('/tests')
def tests():
    if not is_authenticated():
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Получаем все тесты
    cursor.execute("""
        SELECT t.test_id, t.title, t.description, c.name as category, 
               d.level_name as difficulty, t.time_limit_minutes
        FROM tests t
        JOIN categories c ON t.category_id = c.category_id
        JOIN difficulty_levels d ON t.difficulty_level_id = d.level_id
        WHERE t.is_active = 1
        ORDER BY t.test_id
    """)

    tests_list = cursor.fetchall()

    # Получаем ID тестов, которые пользователь проходил хотя бы один раз
    cursor.execute("""
        SELECT DISTINCT test_id FROM learning_progress 
        WHERE user_id = ? AND progress_type_id = 2
    """, session['user_id'])

    completed_tests = [row[0] for row in cursor.fetchall()]

    conn.close()

    return render_template('tests.html',
                           tests=tests_list,
                           completed_tests=completed_tests,
                           username=session['username'])


@app.route('/test/<int:test_id>')
def test_detail(test_id):
    if not is_authenticated():
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Получаем информацию о тесте
    cursor.execute("""
        SELECT t.test_id, t.title, t.description, c.name as category, 
               d.level_name as difficulty, t.time_limit_minutes, t.max_score
        FROM tests t
        JOIN categories c ON t.category_id = c.category_id
        JOIN difficulty_levels d ON t.difficulty_level_id = d.level_id
        WHERE t.test_id = ? AND t.is_active = 1
    """, test_id)

    test = cursor.fetchone()

    if not test:
        return "Тест не найден", 404

    # Проверяем, пройден ли тест (хотя бы один раз) - ИСПРАВЛЕННЫЙ ЗАПРОС
    cursor.execute("""
        SELECT TOP 1 1 FROM learning_progress 
        WHERE user_id = ? AND test_id = ? AND progress_type_id = 2
    """, session['user_id'], test_id)

    is_completed = cursor.fetchone() is not None

    # ВСЕГДА получаем вопросы теста (тест можно проходить неограниченно)
    cursor.execute("""
        SELECT q.question_id, q.question_text, q.question_type_id, q.points
        FROM test_questions q
        WHERE q.test_id = ?
        ORDER BY q.display_order
    """, test_id)

    questions = cursor.fetchall()

    # Для каждого вопроса получаем варианты ответов
    questions_with_options = []
    for question in questions:
        cursor.execute("""
            SELECT o.option_id, o.option_text, o.is_correct
            FROM question_options o
            WHERE o.question_id = ?
            ORDER BY o.display_order
        """, question[0])

        options = cursor.fetchall()
        questions_with_options.append({
            'id': question[0],
            'text': question[1],
            'type': question[2],
            'points': question[3],
            'options': options
        })

    conn.close()

    return render_template('test_detail.html',
                           test=test,
                           questions=questions_with_options,
                           is_completed=is_completed,
                           username=session['username'])


@app.route('/submit_test/<int:test_id>', methods=['POST'])
def submit_test(test_id):
    if not is_authenticated():
        return {'success': False, 'error': 'Not authenticated'}

    user_answers = request.json.get('answers', {})

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Получаем вопросы теста
        cursor.execute("""
            SELECT question_id, points 
            FROM test_questions 
            WHERE test_id = ?
        """, test_id)
        questions = cursor.fetchall()

        total_score = 0
        max_score = sum([q[1] for q in questions])
        correct_answers = 0
        total_questions = len(questions)

        # Создаем запись о результате теста
        cursor.execute("""
            INSERT INTO test_results (user_id, test_id, score, max_score, time_spent_seconds)
            OUTPUT INSERTED.result_id
            VALUES (?, ?, ?, ?, ?)
        """, session['user_id'], test_id, 0, max_score, 0)

        result_id = cursor.fetchone()[0]

        # Проверяем каждый ответ
        for question in questions:
            question_id = question[0]
            question_points = question[1]
            user_answer = user_answers.get(str(question_id))

            if user_answer:
                # Для single choice
                if isinstance(user_answer, int):
                    cursor.execute("""
                        SELECT is_correct FROM question_options 
                        WHERE option_id = ?
                    """, user_answer)
                    option = cursor.fetchone()

                    is_correct = option[0] if option else False

                    if is_correct:
                        total_score += question_points
                        correct_answers += 1

                    # Сохраняем ответ пользователя
                    cursor.execute("""
                        INSERT INTO user_answers (result_id, question_id, selected_option_id, is_correct)
                        VALUES (?, ?, ?, ?)
                    """, result_id, question_id, user_answer, is_correct)

                # Для multiple choice (если нужно в будущем)
                elif isinstance(user_answer, list):
                    # Логика для multiple choice
                    pass

        # Обновляем общий результат
        cursor.execute("""
            UPDATE test_results 
            SET score = ? 
            WHERE result_id = ?
        """, total_score, result_id)

        # Добавляем прогресс обучения
        cursor.execute("""
            INSERT INTO learning_progress (user_id, test_id, progress_type_id, score)
            VALUES (?, ?, 2, ?)
        """, session['user_id'], test_id, total_score)

        conn.commit()

        # Проверяем достижения после прохождения теста
        check_and_award_achievements(session['user_id'])

        conn.close()

        return {
            'success': True,
            'score': total_score,
            'max_score': max_score,
            'correct_answers': correct_answers,
            'total_questions': total_questions,
            'percentage': round((total_score / max_score) * 100) if max_score > 0 else 0
        }

    except Exception as e:
        conn.close()
        return {'success': False, 'error': str(e)}


@app.route('/profile')
def profile():
    if not is_authenticated():
        return redirect(url_for('auth.login'))

    # Сначала проверяем и присваиваем достижения
    check_and_award_achievements(session['user_id'])

    conn = get_db_connection()
    cursor = conn.cursor()

    # Получаем данные пользователя
    cursor.execute("""
        SELECT username, email, created_at 
        FROM users WHERE user_id = ?
    """, session['user_id'])
    user_data = cursor.fetchone()

    # Статистика пользователя
    cursor.execute("""
        SELECT COUNT(DISTINCT article_id) FROM learning_progress 
        WHERE user_id = ? AND progress_type_id = 1
    """, session['user_id'])
    articles_read = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT test_id) FROM learning_progress 
        WHERE user_id = ? AND progress_type_id = 2
    """, session['user_id'])
    tests_completed = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM user_achievements 
        WHERE user_id = ?
    """, session['user_id'])
    achievements_count = cursor.fetchone()[0]

    # Общее количество статей и тестов в системе
    cursor.execute("SELECT COUNT(*) FROM articles WHERE is_published = 1")
    total_articles = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM tests WHERE is_active = 1")
    total_tests = cursor.fetchone()[0]

    # Прогресс по темам
    cursor.execute("""
        SELECT c.name, 
               COUNT(DISTINCT lp.article_id) as completed,
               COUNT(DISTINCT a.article_id) as total
        FROM categories c
        JOIN articles a ON c.category_id = a.category_id AND a.is_published = 1
        LEFT JOIN learning_progress lp ON a.article_id = lp.article_id 
               AND lp.user_id = ? AND lp.progress_type_id = 1
        GROUP BY c.category_id, c.name
        HAVING COUNT(DISTINCT a.article_id) > 0
    """, session['user_id'])
    topic_progress = cursor.fetchall()

    # Последние достижения - ВСЕ достижения для отладки
    cursor.execute("""
        SELECT a.name, a.description, a.icon, ua.earned_at
        FROM user_achievements ua
        JOIN achievements a ON ua.achievement_id = a.achievement_id
        WHERE ua.user_id = ?
        ORDER BY ua.earned_at DESC
    """, session['user_id'])
    recent_achievements = cursor.fetchall()

    # Последние результаты тестов
    cursor.execute("""
        SELECT t.title, tr.score, tr.max_score, tr.completed_at
        FROM test_results tr
        JOIN tests t ON tr.test_id = t.test_id
        WHERE tr.user_id = ? AND tr.completed_at = (
            SELECT MAX(completed_at) 
            FROM test_results 
            WHERE user_id = ? AND test_id = t.test_id
        )
        ORDER BY tr.completed_at DESC
    """, session['user_id'], session['user_id'])
    test_results = cursor.fetchall()

    conn.close()

    return render_template('profile.html',
                           username=user_data[0],
                           email=user_data[1],
                           join_date=user_data[2],
                           articles_read=articles_read,
                           tests_completed=tests_completed,
                           achievements_count=achievements_count,
                           total_articles=total_articles,
                           total_tests=total_tests,
                           topic_progress=topic_progress,
                           recent_achievements=recent_achievements,
                           test_results=test_results)


@app.route('/mark_article_read/<int:article_id>')
def mark_article_read(article_id):
    if not is_authenticated():
        return {'success': False, 'error': 'Not authenticated'}

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Проверяем, не отмечена ли уже статья
        cursor.execute("""
            SELECT * FROM learning_progress 
            WHERE user_id = ? AND article_id = ? AND progress_type_id = 1
        """, session['user_id'], article_id)

        if not cursor.fetchone():
            # Добавляем запись о прочтении
            cursor.execute("""
                INSERT INTO learning_progress (user_id, article_id, progress_type_id)
                VALUES (?, ?, 1)
            """, session['user_id'], article_id)
            conn.commit()

            # Проверяем достижения после прочтения статьи
            check_and_award_achievements(session['user_id'])

        conn.close()
        return {'success': True}

    except Exception as e:
        conn.close()
        return {'success': False, 'error': str(e)}


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


if __name__ == '__main__':
    app.run(debug=True)