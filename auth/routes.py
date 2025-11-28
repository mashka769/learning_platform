from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import pyodbc
import hashlib
import re

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

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

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_valid_username(username):
    return len(username) >= 3 and username.isalnum()

def is_admin(user_id):
    """Проверка является ли пользователь админом"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM admins 
        WHERE user_id = ? AND is_active = 1
    """, user_id)
    is_admin_user = cursor.fetchone() is not None
    conn.close()
    return is_admin_user

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к базе данных', 'error')
            return render_template('auth/login.html')

        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, username, password_hash FROM users WHERE username = ?",
            username
        )
        user = cursor.fetchone()

        if user and user[2] == hash_password(password):
            session['user_id'] = user[0]
            session['username'] = user[1]

            # проверка на админа
            cursor.execute("SELECT 1 FROM admins WHERE user_id = ? AND is_active = 1", user[0])
            is_admin_user = cursor.fetchone() is not None
            session['is_admin'] = is_admin_user

            conn.close()
            flash('Успешный вход! Добро пожаловать!', 'success')
            return redirect(url_for('index'))
        else:
            conn.close()
            flash('Неверное имя пользователя или пароль', 'error')

    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Валидация
        if not is_valid_username(username):
            flash('Имя пользователя должно содержать только буквы и цифры, минимум 3 символа', 'error')
            return render_template('auth/register.html')

        if not is_valid_email(email):
            flash('Введите корректный email адрес', 'error')
            return render_template('auth/register.html')

        if len(password) < 6:
            flash('Пароль должен содержать минимум 6 символов', 'error')
            return render_template('auth/register.html')

        if password != confirm_password:
            flash('Пароли не совпадают', 'error')
            return render_template('auth/register.html')

        conn = get_db_connection()
        if not conn:
            flash('Ошибка подключения к базе данных', 'error')
            return render_template('auth/register.html')

        cursor = conn.cursor()

        # Проверяем существование пользователя
        cursor.execute("SELECT user_id FROM users WHERE username = ? OR email = ?",
                       username, email)
        if cursor.fetchone():
            conn.close()
            flash('Пользователь с таким именем или email уже существует', 'error')
            return render_template('auth/register.html')

        # Создаем пользователя
        try:
            cursor.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                username, email, hash_password(password)
            )
            conn.commit()
            conn.close()

            flash('Регистрация успешна! Теперь вы можете войти.', 'success')
            return redirect(url_for('auth.login'))

        except Exception as e:
            conn.close()
            flash('Ошибка при регистрации. Попробуйте еще раз.', 'error')

    return render_template('auth/register.html')