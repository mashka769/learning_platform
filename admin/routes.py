from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
import pyodbc
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

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

def is_admin():
    """Проверка является ли пользователь админом"""
    if 'user_id' not in session:
        return False

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM admins 
        WHERE user_id = ? AND is_active = 1
    """, session['user_id'])
    is_admin = cursor.fetchone() is not None
    conn.close()
    return is_admin

def admin_required(f):
    """Декоратор для проверки прав админа"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin():
            flash('Доступ запрещен. Требуются права администратора.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/')
@admin_required
def dashboard():
    """Главная панель админа"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Статистика платформы
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM articles WHERE is_published = 1")
    total_articles = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM tests WHERE is_active = 1")
    total_tests = cursor.fetchone()[0]

    # Последние зарегистрированные пользователи
    cursor.execute("""
        SELECT TOP 5 username, email, created_at 
        FROM users 
        ORDER BY created_at DESC
    """)
    recent_users = cursor.fetchall()

    conn.close()

    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         total_articles=total_articles,
                         total_tests=total_tests,
                         recent_users=recent_users)

@admin_bp.route('/articles')
@admin_required
def admin_articles():
    """Управление статьями"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT a.article_id, a.title, c.name as category, 
               d.level_name as difficulty, a.is_published, a.created_at
        FROM articles a
        JOIN categories c ON a.category_id = c.category_id
        JOIN difficulty_levels d ON a.difficulty_level_id = d.level_id
        ORDER BY a.created_at DESC
    """)
    articles = cursor.fetchall()

    cursor.execute("SELECT category_id, name FROM categories")
    categories = cursor.fetchall()

    cursor.execute("SELECT level_id, level_name FROM difficulty_levels")
    difficulties = cursor.fetchall()

    conn.close()

    return render_template('admin/articles.html',
                         articles=articles,
                         categories=categories,
                         difficulties=difficulties)

@admin_bp.route('/article/edit/<int:article_id>')
@admin_required
def edit_article(article_id):
    """Редактирование статьи"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT article_id, title, content, category_id, 
               difficulty_level_id, reading_time_minutes, is_published
        FROM articles 
        WHERE article_id = ?
    """, article_id)
    article = cursor.fetchone()

    if not article:
        flash('Статья не найдена', 'error')
        return redirect(url_for('admin.admin_articles'))

    cursor.execute("SELECT category_id, name FROM categories")
    categories = cursor.fetchall()

    cursor.execute("SELECT level_id, level_name FROM difficulty_levels")
    difficulties = cursor.fetchall()

    conn.close()

    return render_template('admin/edit_article.html',
                         article=article,
                         categories=categories,
                         difficulties=difficulties)

@admin_bp.route('/article/update/<int:article_id>', methods=['POST'])
@admin_required
def update_article(article_id):
    """Обновление статьи"""
    title = request.form['title']
    content = request.form['content']
    category_id = request.form['category_id']
    difficulty_id = request.form['difficulty_id']
    reading_time = request.form['reading_time']
    is_published = 1 if request.form.get('is_published') else 0

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE articles 
            SET title = ?, content = ?, category_id = ?, 
                difficulty_level_id = ?, reading_time_minutes = ?, 
                is_published = ?, updated_at = GETDATE()
            WHERE article_id = ?
        """, title, content, category_id, difficulty_id, reading_time, is_published, article_id)

        conn.commit()
        flash('Статья успешно обновлена', 'success')
    except Exception as e:
        flash(f'Ошибка при обновлении статьи: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('admin.admin_articles'))

@admin_bp.route('/article/delete/<int:article_id>')
@admin_required
def delete_article(article_id):
    """Удаление статьи"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Сначала удаляем связанные записи в learning_progress
        cursor.execute("DELETE FROM learning_progress WHERE article_id = ?", article_id)
        # Затем удаляем саму статью
        cursor.execute("DELETE FROM articles WHERE article_id = ?", article_id)
        conn.commit()
        flash('Статья успешно удалена', 'success')
    except Exception as e:
        flash(f'Ошибка при удалении статьи: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('admin.admin_articles'))

@admin_bp.route('/article/new')
@admin_required
def new_article():
    """Создание новой статьи"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT category_id, name FROM categories")
    categories = cursor.fetchall()

    cursor.execute("SELECT level_id, level_name FROM difficulty_levels")
    difficulties = cursor.fetchall()

    conn.close()

    return render_template('admin/edit_article.html',
                         article=None,
                         categories=categories,
                         difficulties=difficulties)

@admin_bp.route('/article/create', methods=['POST'])
@admin_required
def create_article():
    """Создание новой статьи"""
    title = request.form['title']
    content = request.form['content']
    category_id = request.form['category_id']
    difficulty_id = request.form['difficulty_id']
    reading_time = request.form['reading_time']
    is_published = 1 if request.form.get('is_published') else 0

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO articles (title, content, category_id, difficulty_level_id, 
                                reading_time_minutes, is_published, author_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())
        """, title, content, category_id, difficulty_id, reading_time, is_published, session['user_id'])

        conn.commit()
        flash('Статья успешно создана', 'success')
    except Exception as e:
        flash(f'Ошибка при создании статьи: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('admin.admin_articles'))

@admin_bp.route('/tests')
@admin_required
def admin_tests():
    """Управление тестами"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT t.test_id, t.title, t.description, c.name as category, 
               d.level_name as difficulty, t.max_score, t.is_active, t.created_at
        FROM tests t
        JOIN categories c ON t.category_id = c.category_id
        JOIN difficulty_levels d ON t.difficulty_level_id = d.level_id
        ORDER BY t.created_at DESC
    """)
    tests = cursor.fetchall()

    cursor.execute("SELECT category_id, name FROM categories")
    categories = cursor.fetchall()

    cursor.execute("SELECT level_id, level_name FROM difficulty_levels")
    difficulties = cursor.fetchall()

    conn.close()

    return render_template('admin/tests.html',
                           tests=tests,
                           categories=categories,
                           difficulties=difficulties)

@admin_bp.route('/test/edit/<int:test_id>')
@admin_required
def edit_test(test_id):
    """Редактирование теста с вопросами и ответами"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Получаем основную информацию о тесте
    cursor.execute("""
        SELECT test_id, title, description, category_id, difficulty_level_id, 
               max_score, is_active
        FROM tests 
        WHERE test_id = ?
    """, test_id)
    test = cursor.fetchone()

    if not test:
        flash('Тест не найден', 'error')
        return redirect(url_for('admin.admin_tests'))

    # Получаем вопросы теста
    cursor.execute("""
        SELECT question_id, question_text, question_type_id, points, display_order
        FROM test_questions 
        WHERE test_id = ?
        ORDER BY display_order
    """, test_id)
    questions = cursor.fetchall()

    # Получаем варианты ответов для каждого вопроса
    question_options = {}
    for question in questions:
        cursor.execute("""
            SELECT option_id, option_text, is_correct, display_order
            FROM question_options 
            WHERE question_id = ?
            ORDER BY display_order
        """, question[0])
        question_options[question[0]] = cursor.fetchall()

    cursor.execute("SELECT category_id, name FROM categories")
    categories = cursor.fetchall()

    cursor.execute("SELECT level_id, level_name FROM difficulty_levels")
    difficulties = cursor.fetchall()

    conn.close()

    return render_template('admin/edit_test.html',
                           test=test,
                           questions=questions,
                           question_options=question_options,
                           categories=categories,
                           difficulties=difficulties)

@admin_bp.route('/test/update/<int:test_id>', methods=['POST'])
@admin_required
def update_test(test_id):
    """Обновление теста с вопросами и ответами"""
    # Основная информация о тесте
    title = request.form['title']
    description = request.form['description']
    category_id = request.form['category_id']
    difficulty_id = request.form['difficulty_id']
    max_score = request.form['max_score']
    is_active = 1 if request.form.get('is_active') else 0

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Обновляем основную информацию о тесте
        cursor.execute("""
            UPDATE tests 
            SET title = ?, description = ?, category_id = ?, 
                difficulty_level_id = ?, max_score = ?, is_active = ?
            WHERE test_id = ?
        """, title, description, category_id, difficulty_id, max_score, is_active, test_id)

        # Обрабатываем вопросы и ответы
        process_test_questions(cursor, test_id, request.form)

        conn.commit()
        flash('Тест успешно обновлен', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Ошибка при обновлении теста: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('admin.admin_tests'))

@admin_bp.route('/test/delete/<int:test_id>')
@admin_required
def delete_test(test_id):
    """Удаление теста"""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Сначала удаляем связанные записи
        cursor.execute(
            "DELETE FROM user_answers WHERE result_id IN (SELECT result_id FROM test_results WHERE test_id = ?)",
            test_id)
        cursor.execute("DELETE FROM test_results WHERE test_id = ?", test_id)
        cursor.execute("DELETE FROM learning_progress WHERE test_id = ?", test_id)

        # Удаляем вопросы и варианты ответов
        cursor.execute(
            "DELETE FROM question_options WHERE question_id IN (SELECT question_id FROM test_questions WHERE test_id = ?)",
            test_id)
        cursor.execute("DELETE FROM test_questions WHERE test_id = ?", test_id)

        # Удаляем сам тест
        cursor.execute("DELETE FROM tests WHERE test_id = ?", test_id)

        conn.commit()
        flash('Тест успешно удален', 'success')
    except Exception as e:
        flash(f'Ошибка при удалении теста: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('admin.admin_tests'))

@admin_bp.route('/test/new')
@admin_required
def new_test():
    """Создание нового теста"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT category_id, name FROM categories")
    categories = cursor.fetchall()

    cursor.execute("SELECT level_id, level_name FROM difficulty_levels")
    difficulties = cursor.fetchall()

    conn.close()

    return render_template('admin/edit_test.html',
                           test=None,
                           questions=None,
                           question_options=None,
                           categories=categories,
                           difficulties=difficulties)

@admin_bp.route('/test/create', methods=['POST'])
@admin_required
def create_test():
    """Создание нового теста с вопросами и ответами"""
    # Основная информация о тесте
    title = request.form['title']
    description = request.form['description']
    category_id = request.form['category_id']
    difficulty_id = request.form['difficulty_id']
    max_score = request.form['max_score']
    is_active = 1 if request.form.get('is_active') else 0

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Создаем тест
        cursor.execute("""
            INSERT INTO tests (title, description, category_id, difficulty_level_id, 
                             max_score, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, GETDATE())
        """, title, description, category_id, difficulty_id, max_score, is_active)

        # Получаем ID созданного теста
        test_id = cursor.execute("SELECT @@IDENTITY").fetchone()[0]

        # Обрабатываем вопросы и ответы
        process_test_questions(cursor, test_id, request.form)

        conn.commit()
        flash('Тест успешно создан', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Ошибка при создании теста: {str(e)}', 'error')
    finally:
        conn.close()

    return redirect(url_for('admin.admin_tests'))

def process_test_questions(cursor, test_id, form_data):
    """Обработка вопросов и вариантов ответов"""
    # Получаем существующие вопросы для этого теста
    cursor.execute("SELECT question_id FROM test_questions WHERE test_id = ?", test_id)
    existing_questions = [row[0] for row in cursor.fetchall()]

    # Обрабатываем вопросы из формы
    question_texts = form_data.getlist('question_text[]')
    question_types = form_data.getlist('question_type[]')
    question_points = form_data.getlist('question_points[]')

    used_question_ids = []

    for i, (q_text, q_type, q_points) in enumerate(zip(question_texts, question_types, question_points)):
        if not q_text.strip():
            continue

        # Проверяем, существует ли уже такой вопрос
        question_id = None
        if i < len(existing_questions):
            question_id = existing_questions[i]
            # Обновляем существующий вопрос
            cursor.execute("""
                UPDATE test_questions 
                SET question_text = ?, question_type_id = ?, points = ?, display_order = ?
                WHERE question_id = ?
            """, q_text, int(q_type), int(q_points), i + 1, question_id)
        else:
            # Создаем новый вопрос
            cursor.execute("""
                INSERT INTO test_questions (test_id, question_text, question_type_id, points, display_order)
                VALUES (?, ?, ?, ?, ?)
            """, test_id, q_text, int(q_type), int(q_points), i + 1)
            question_id = cursor.execute("SELECT @@IDENTITY").fetchone()[0]

        used_question_ids.append(question_id)

        # Обрабатываем варианты ответов для этого вопроса
        process_question_options(cursor, question_id, form_data, i)

    # Удаляем вопросы, которые больше не используются
    for existing_id in existing_questions:
        if existing_id not in used_question_ids:
            cursor.execute("DELETE FROM question_options WHERE question_id = ?", existing_id)
            cursor.execute("DELETE FROM test_questions WHERE question_id = ?", existing_id)

def process_question_options(cursor, question_id, form_data, question_index):
    """Безопасная обработка вариантов ответов для вопроса"""
    # Получаем существующие варианты для этого вопроса
    cursor.execute(
        "SELECT option_id, option_text, is_correct FROM question_options WHERE question_id = ? ORDER BY display_order",
        question_id)
    existing_options = cursor.fetchall()

    # Получаем варианты ответов из формы
    option_texts = form_data.getlist('option_text_new[]')
    option_corrects = form_data.getlist('option_correct_new[]')

    # Определяем правильные ответы
    correct_indices = [int(idx) for idx in option_corrects]

    # ВАЖНО: Не удаляем старые варианты, а только обновляем/добавляем новые
    # Это предотвращает конфликты с foreign keys

    # Обновляем существующие варианты
    for i, existing_option in enumerate(existing_options):
        if i < len(option_texts) and option_texts[i].strip():
            # Обновляем существующий вариант
            is_correct = 1 if i in correct_indices else 0
            cursor.execute("""
                UPDATE question_options 
                SET option_text = ?, is_correct = ?, display_order = ?
                WHERE option_id = ?
            """, option_texts[i], is_correct, i + 1, existing_option[0])

    # Добавляем новые варианты, если их больше чем существующих
    for i in range(len(existing_options), len(option_texts)):
        if option_texts[i].strip():
            is_correct = 1 if i in correct_indices else 0
            cursor.execute("""
                INSERT INTO question_options (question_id, option_text, is_correct, display_order)
                VALUES (?, ?, ?, ?)
            """, question_id, option_texts[i], is_correct, i + 1)

@admin_bp.route('/users')
@admin_required
def admin_users():
    """Управление пользователями"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT u.user_id, u.username, u.email, u.created_at,
               (SELECT COUNT(*) FROM learning_progress WHERE user_id = u.user_id AND progress_type_id = 1) as articles_read,
               (SELECT COUNT(*) FROM learning_progress WHERE user_id = u.user_id AND progress_type_id = 2) as tests_completed,
               (SELECT COUNT(*) FROM user_achievements WHERE user_id = u.user_id) as achievements_count
        FROM users u
        ORDER BY u.created_at DESC
    """)
    users = cursor.fetchall()

    conn.close()

    return render_template('admin/users.html', users=users)