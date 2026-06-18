from flask import Flask, render_template, session, redirect, url_for, request
from auth.routes import auth_bp
from admin.routes import admin_bp
import pyodbc
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Регистрируем blueprint'ы
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)

# Настройки для аватарок
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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

def normalize_code(code):
    """Удаляет пробелы, табуляции и переносы строк для сравнения"""
    import re
    return re.sub(r'\s+', '', code.strip())

def check_code(user_code, expected_code):
    """Сравнивает код пользователя с эталоном"""
    return normalize_code(user_code) == normalize_code(expected_code)

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

def save_coding_test_result(test_id, score):
    """Сохраняет результат сложного теста"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT max_score FROM tests WHERE test_id = ?", test_id)
        max_score = cursor.fetchone()[0]

        cursor.execute("""
            INSERT INTO test_results (user_id, test_id, score, max_score, completed_at)
            VALUES (?, ?, ?, ?, GETDATE())
        """, session['user_id'], test_id, score, max_score)

        cursor.execute("""
            INSERT INTO learning_progress (user_id, test_id, progress_type_id, score, completed_at)
            VALUES (?, ?, 2, ?, GETDATE())
        """, session['user_id'], test_id, score)

        conn.commit()
        check_and_award_achievements(session['user_id'])

    except Exception as e:
        print(f"Ошибка при сохранении результата: {e}")
    finally:
        conn.close()

# ========== РОУТЫ ДЛЯ АВАТАРОК ==========
@app.route('/upload_avatar', methods=['POST'])
def upload_avatar():
    if not is_authenticated():
        return {'success': False, 'error': 'Not authenticated'}

    if 'avatar' not in request.files:
        return {'success': False, 'error': 'Нет файла'}

    file = request.files['avatar']

    if file.filename == '':
        return {'success': False, 'error': 'Файл не выбран'}

    if not allowed_file(file.filename):
        return {'success': False, 'error': 'Разрешены только PNG, JPG, JPEG, GIF'}

    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > MAX_FILE_SIZE:
        return {'success': False, 'error': 'Файл слишком большой (макс. 2MB)'}

    try:
        avatar_data = file.read()
        avatar_type = file.content_type

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT avatar_id FROM user_avatars WHERE user_id = ?", session['user_id'])
        existing = cursor.fetchone()

        if existing:
            cursor.execute("""
                UPDATE user_avatars 
                SET avatar_data = ?, avatar_type = ?, updated_at = GETDATE()
                WHERE user_id = ?
            """, avatar_data, avatar_type, session['user_id'])
        else:
            cursor.execute("""
                INSERT INTO user_avatars (user_id, avatar_data, avatar_type)
                VALUES (?, ?, ?)
            """, session['user_id'], avatar_data, avatar_type)

        conn.commit()
        conn.close()

        return {'success': True, 'message': 'Аватар обновлен'}

    except Exception as e:
        return {'success': False, 'error': str(e)}

@app.route('/get_avatar/<int:user_id>')
def get_avatar(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT avatar_data, avatar_type FROM user_avatars WHERE user_id = ?", user_id)
    avatar = cursor.fetchone()
    conn.close()

    if avatar and avatar[0]:
        response = app.response_class(avatar[0], mimetype=avatar[1])
        return response
    else:
        return '', 404

@app.route('/delete_avatar', methods=['POST'])
def delete_avatar():
    if not is_authenticated():
        return {'success': False, 'error': 'Not authenticated'}

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM user_avatars WHERE user_id = ?", session['user_id'])
    conn.commit()
    conn.close()

    return {'success': True, 'message': 'Аватар удален'}

# ========== ОСНОВНЫЕ РОУТЫ ==========
@app.route('/')
def index():
    if not is_authenticated():
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor()

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

    cursor.execute("""
        SELECT TOP 1 1 FROM learning_progress 
        WHERE user_id = ? AND test_id = ? AND progress_type_id = 2
    """, session['user_id'], test_id)

    is_completed = cursor.fetchone() is not None

    cursor.execute("""
        SELECT q.question_id, q.question_text, q.question_type_id, q.points
        FROM test_questions q
        WHERE q.test_id = ?
        ORDER BY q.display_order
    """, test_id)

    questions = cursor.fetchall()

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

        cursor.execute("""
            INSERT INTO test_results (user_id, test_id, score, max_score, time_spent_seconds)
            OUTPUT INSERTED.result_id
            VALUES (?, ?, ?, ?, ?)
        """, session['user_id'], test_id, 0, max_score, 0)

        result_id = cursor.fetchone()[0]

        for question in questions:
            question_id = question[0]
            question_points = question[1]
            user_answer = user_answers.get(str(question_id))

            if user_answer:
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

                    cursor.execute("""
                        INSERT INTO user_answers (result_id, question_id, selected_option_id, is_correct)
                        VALUES (?, ?, ?, ?)
                    """, result_id, question_id, user_answer, is_correct)

                elif isinstance(user_answer, list):
                    pass

        cursor.execute("""
            UPDATE test_results 
            SET score = ? 
            WHERE result_id = ?
        """, total_score, result_id)

        cursor.execute("""
            INSERT INTO learning_progress (user_id, test_id, progress_type_id, score)
            VALUES (?, ?, 2, ?)
        """, session['user_id'], test_id, total_score)

        conn.commit()

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

    check_and_award_achievements(session['user_id'])

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT username, email, created_at 
        FROM users WHERE user_id = ?
    """, session['user_id'])
    user_data = cursor.fetchone()

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

    cursor.execute("SELECT COUNT(*) FROM articles WHERE is_published = 1")
    total_articles = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM tests WHERE is_active = 1")
    total_tests = cursor.fetchone()[0]

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

    cursor.execute("""
        SELECT a.name, a.description, a.icon, ua.earned_at
        FROM user_achievements ua
        JOIN achievements a ON ua.achievement_id = a.achievement_id
        WHERE ua.user_id = ?
        ORDER BY ua.earned_at DESC
    """, session['user_id'])
    recent_achievements = cursor.fetchall()

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

    # Проверяем наличие аватарки (ДО закрытия соединения)
    cursor.execute("SELECT avatar_id FROM user_avatars WHERE user_id = ?", session['user_id'])
    has_avatar = cursor.fetchone() is not None

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
                           test_results=test_results,
                           has_avatar=has_avatar)

@app.route('/mark_article_read/<int:article_id>')
def mark_article_read(article_id):
    if not is_authenticated():
        return {'success': False, 'error': 'Not authenticated'}

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT * FROM learning_progress 
            WHERE user_id = ? AND article_id = ? AND progress_type_id = 1
        """, session['user_id'], article_id)

        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO learning_progress (user_id, article_id, progress_type_id)
                VALUES (?, ?, 1)
            """, session['user_id'], article_id)
            conn.commit()
            check_and_award_achievements(session['user_id'])

        conn.close()
        return {'success': True}

    except Exception as e:
        conn.close()
        return {'success': False, 'error': str(e)}

@app.route('/coding_test/<int:test_id>')
def coding_test(test_id):
    if not is_authenticated():
        return redirect(url_for('auth.login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT test_id, title, description, max_score 
        FROM tests WHERE test_id = ? AND is_active = 1
    """, test_id)
    test = cursor.fetchone()

    if not test:
        return "Тест не найден", 404

    cursor.execute("""
        SELECT challenge_id, step_number, description, points
        FROM coding_challenges 
        WHERE test_id = ?
        ORDER BY step_number
    """, test_id)
    challenges = cursor.fetchall()

    conn.close()

    if 'coding_progress' not in session or session['coding_progress'].get('test_id') != test_id:
        session['coding_progress'] = {
            'test_id': test_id,
            'current_step': 1,
            'completed': [False] * len(challenges),
            'score': 0,
            'answers': {}
        }

    progress = session['coding_progress']
    current_challenge = challenges[progress['current_step'] - 1]

    return render_template('coding_test.html',
                           test=test,
                           challenges=challenges,
                           current_challenge=current_challenge,
                           progress=progress,
                           username=session['username'])

@app.route('/check_code/<int:challenge_id>', methods=['POST'])
def check_code_route(challenge_id):
    if not is_authenticated():
        return {'success': False, 'error': 'Not authenticated'}

    data = request.get_json()
    user_code = data.get('code', '')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT expected_code, points, test_id, step_number
        FROM coding_challenges WHERE challenge_id = ?
    """, challenge_id)
    challenge = cursor.fetchone()
    conn.close()

    if not challenge:
        return {'success': False, 'error': 'Задание не найдено'}

    expected_code, points, test_id, step_number = challenge

    is_correct = check_code(user_code, expected_code)

    if 'coding_progress' in session and session['coding_progress']['test_id'] == test_id:
        progress = session['coding_progress']
        step_index = step_number - 1

        if is_correct and not progress['completed'][step_index]:
            progress['completed'][step_index] = True
            progress['score'] += points
            progress['answers'][str(challenge_id)] = user_code

            if all(progress['completed']):
                save_coding_test_result(test_id, progress['score'])

        session['coding_progress'] = progress

    return {
        'success': True,
        'is_correct': is_correct,
        'expected': expected_code if not is_correct else None,
        'completed': all(progress['completed']) if 'progress' in locals() else False
    }

@app.route('/coding_step/<int:test_id>/<int:step>')
def coding_step(test_id, step):
    if not is_authenticated():
        return redirect(url_for('auth.login'))

    if 'coding_progress' in session and session['coding_progress'].get('test_id') == test_id:
        progress = session['coding_progress']
        if step > 1 and not progress['completed'][step - 2]:
            return redirect(url_for('coding_test', test_id=test_id))

        if 1 <= step <= len(progress['completed']):
            progress['current_step'] = step
            session['coding_progress'] = progress

    return redirect(url_for('coding_test', test_id=test_id))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

if __name__ == '__main__':
    app.run(debug=True)