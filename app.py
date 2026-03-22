import json
import secrets
import string
import os
import uuid
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, render_template, redirect, url_for, flash, request, abort, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from dotenv import load_dotenv

load_dotenv()

# ------------------- Configuration -------------------
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-prod'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///coaching.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAIL_SERVER = os.environ.get('MAIL_SERVER') or 'smtp.gmail.com'
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 587)
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = MAIL_USERNAME

# ------------------- Extensions -------------------
db = SQLAlchemy()
login_manager = LoginManager()
mail = Mail()

# ------------------- Database Creation Helper (Robust) -------------------
def ensure_database_exists(app):
    """
    Create the PostgreSQL database if it does not exist.
    For SQLite, this function does nothing.
    If psycopg2 cannot be imported (e.g., Python version incompatibility),
    it assumes the database already exists and continues.
    """
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']
    
    # Skip if SQLite
    if db_uri.startswith('sqlite'):
        return
    
    # Lazy import – only when we need to connect to PostgreSQL
    try:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    except ImportError as e:
        print(f"⚠️  psycopg2 not available: {e}")
        print("   Assuming the PostgreSQL database already exists.")
        return  # Assume database exists (typical in production)
    
    # Parse PostgreSQL URI
    parsed = urlparse(db_uri)
    db_name = parsed.path[1:]  # remove leading '/'
    db_user = parsed.username
    db_password = parsed.password
    db_host = parsed.hostname
    db_port = parsed.port or 5432
    
    try:
        # Connect to the default 'postgres' database
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database='postgres'
        )
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Check if target database exists
        cursor.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (db_name,))
        exists = cursor.fetchone()
        
        if not exists:
            cursor.execute(f'CREATE DATABASE {db_name}')
            print(f"✅ Database '{db_name}' created successfully.")
        else:
            print(f"✅ Database '{db_name}' already exists.")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"⚠️  Could not create database: {e}")
        print("   Please ensure the database exists and connection parameters are correct.")

# ------------------- Models -------------------
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    force_password_change = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    admin = db.relationship('Admin', backref='user', uselist=False, cascade='all, delete-orphan')
    teacher = db.relationship('Teacher', backref='user', uselist=False, cascade='all, delete-orphan')
    student = db.relationship('Student', backref='user', uselist=False, cascade='all, delete-orphan')

class Admin(db.Model):
    __tablename__ = 'admins'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    coaching_name = db.Column(db.String(100), nullable=False)
    logo = db.Column(db.String(200))
    subscription_status = db.Column(db.String(20), default='active')
    subscription_expiry = db.Column(db.DateTime)

class Teacher(db.Model):
    __tablename__ = 'teachers'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    subject = db.Column(db.String(100))

class Student(db.Model):
    __tablename__ = 'students'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))

class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Question(db.Model):
    __tablename__ = 'questions'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(500), nullable=False)
    option_b = db.Column(db.String(500), nullable=False)
    option_c = db.Column(db.String(500), nullable=False)
    option_d = db.Column(db.String(500), nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Test(db.Model):
    __tablename__ = 'tests'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))
    duration = db.Column(db.Integer)
    is_series = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TestQuestion(db.Model):
    __tablename__ = 'test_questions'
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('tests.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    order = db.Column(db.Integer)

class Result(db.Model):
    __tablename__ = 'results'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    test_id = db.Column(db.Integer, db.ForeignKey('tests.id'), nullable=False)
    score = db.Column(db.Float)
    total_questions = db.Column(db.Integer)
    correct_count = db.Column(db.Integer)
    wrong_count = db.Column(db.Integer)
    answers_json = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

# ------------------- Utilities -------------------
def generate_random_password(length=8):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def send_email(to, subject, body):
    try:
        msg = Message(subject, recipients=[to])
        msg.body = body
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Email failed: {e}")
        return False

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ------------------- Flask App Factory -------------------
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Ensure the PostgreSQL database exists (if using PostgreSQL)
    ensure_database_exists(app)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    mail.init_app(app)

    with app.app_context():
        db.create_all()
        os.makedirs(os.path.join('static', 'uploads'), exist_ok=True)

        # Create default developer if not exists
        dev = User.query.filter_by(email='dev@coaching.com').first()
        if not dev:
            dev = User(
                email='dev@coaching.com',
                password_hash=generate_password_hash('devpass123'),
                role='developer',
                is_active=True,
                force_password_change=False
            )
            db.session.add(dev)
            db.session.commit()
            print("\n" + "="*50)
            print("✅ DEFAULT DEVELOPER ACCOUNT CREATED!")
            print("="*50)
            print("📧 Email: dev@coaching.com")
            print("🔑 Password: devpass123")
            print("="*50)
            print("⚠️  IMPORTANT: Change this password after first login!\n")
        else:
            print("\n✅ Developer account already exists: dev@coaching.com")

    # ------------------- Context Processor (for logo) -------------------
    @app.context_processor
    def utility_processor():
        def get_coaching_logo():
            if current_user.is_authenticated and current_user.admin_id:
                admin = Admin.query.get(current_user.admin_id)
                if admin and admin.logo:
                    return url_for('static', filename=admin.logo)
            return None
        return dict(get_coaching_logo=get_coaching_logo)

    # ------------------- Routes -------------------
    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            email = request.form.get('email')
            password = request.form.get('password')
            user = User.query.filter_by(email=email).first()
            if user and check_password_hash(user.password_hash, password) and user.is_active:
                login_user(user)
                if user.force_password_change:
                    return redirect(url_for('change_password'))
                if user.role == 'developer':
                    return redirect(url_for('developer_dashboard'))
                elif user.role == 'admin':
                    return redirect(url_for('admin_dashboard'))
                elif user.role == 'teacher':
                    return redirect(url_for('teacher_dashboard'))
                elif user.role == 'student':
                    return redirect(url_for('student_dashboard'))
            flash('Invalid email or password')
        return render_template('login.html')

    @app.route('/change-password', methods=['GET', 'POST'])
    @login_required
    def change_password():
        if request.method == 'POST':
            current = request.form.get('current_password')
            new = request.form.get('new_password')
            confirm = request.form.get('confirm_password')
            if not check_password_hash(current_user.password_hash, current):
                flash('Current password is incorrect.', 'danger')
            elif new != confirm:
                flash('New passwords do not match.', 'danger')
            else:
                current_user.password_hash = generate_password_hash(new)
                current_user.force_password_change = False
                db.session.commit()
                flash('Password changed successfully.', 'success')
                if current_user.role == 'admin':
                    return redirect(url_for('admin_dashboard'))
                elif current_user.role == 'teacher':
                    return redirect(url_for('teacher_dashboard'))
                elif current_user.role == 'student':
                    return redirect(url_for('student_dashboard'))
                else:
                    return redirect(url_for('developer_dashboard'))
        return render_template('change_password.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('index'))

    @app.route('/forgot-password', methods=['GET', 'POST'])
    def forgot_password():
        if request.method == 'POST':
            email = request.form.get('email')
            user = User.query.filter_by(email=email).first()
            if user:
                s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
                token = s.dumps(email, salt='password-reset')
                reset_url = url_for('reset_password', token=token, _external=True)
                if send_email(email, 'Password Reset', f'Click here to reset your password: {reset_url}'):
                    flash('Password reset link sent to your email.')
                else:
                    flash('Password reset link could not be sent. Please contact support.', 'danger')
            else:
                flash('Email not found.')
        return render_template('forgot_password.html')

    @app.route('/reset-password/<token>', methods=['GET', 'POST'])
    def reset_password(token):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        try:
            email = s.loads(token, salt='password-reset', max_age=3600)
        except:
            flash('Invalid or expired token.')
            return redirect(url_for('login'))
        if request.method == 'POST':
            password = request.form.get('password')
            user = User.query.filter_by(email=email).first()
            if user:
                user.password_hash = generate_password_hash(password)
                user.force_password_change = True
                db.session.commit()
                flash('Password updated. Please login and change your password.', 'warning')
                return redirect(url_for('login'))
        return render_template('reset_password.html')

    # ------------------- Developer Panel -------------------
    @app.route('/developer/dashboard')
    @login_required
    @role_required('developer')
    def developer_dashboard():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))

        total_admins = User.query.filter_by(role='admin').count()
        total_students = User.query.filter_by(role='student').count()
        total_teachers = User.query.filter_by(role='teacher').count()
        active_subscriptions = Admin.query.filter_by(subscription_status='active').count()
        expired_subscriptions = Admin.query.filter_by(subscription_status='expired').count()

        recent_admins = User.query.filter_by(role='admin').order_by(User.created_at.desc()).limit(5).all()

        recent_activities = []
        for admin in User.query.filter_by(role='admin').order_by(User.created_at.desc()).limit(5):
            recent_activities.append({
                'type': 'admin', 'message': f'New admin created: {admin.email}',
                'time': admin.created_at, 'icon': 'fas fa-user-plus', 'color': 'primary'
            })
        for teacher in User.query.filter_by(role='teacher').order_by(User.created_at.desc()).limit(5):
            recent_activities.append({
                'type': 'teacher', 'message': f'Teacher added: {teacher.email}',
                'time': teacher.created_at, 'icon': 'fas fa-chalkboard-user', 'color': 'info'
            })
        for student in User.query.filter_by(role='student').order_by(User.created_at.desc()).limit(5):
            recent_activities.append({
                'type': 'student', 'message': f'New student enrolled: {student.email}',
                'time': student.created_at, 'icon': 'fas fa-graduation-cap', 'color': 'success'
            })
        recent_activities.sort(key=lambda x: x['time'], reverse=True)
        recent_activities = recent_activities[:5]

        # User growth for the last 6 months
        today = date.today()
        months = []
        user_counts = []
        for i in range(5, -1, -1):
            month_date = today - relativedelta(months=i)
            month_start = datetime(month_date.year, month_date.month, 1)
            month_end = (month_start + relativedelta(months=1)) - timedelta(days=1)
            months.append(month_date.strftime('%b %Y'))
            count = User.query.filter(User.created_at >= month_start, User.created_at <= month_end).count()
            user_counts.append(count)

        return render_template('developer/dashboard.html',
                               total_admins=total_admins,
                               total_students=total_students,
                               total_teachers=total_teachers,
                               active_subscriptions=active_subscriptions,
                               expired_subscriptions=expired_subscriptions,
                               recent_admins=recent_admins,
                               recent_activities=recent_activities,
                               months=months,
                               user_counts=user_counts)

    @app.route('/developer/admins')
    @login_required
    @role_required('developer')
    def manage_admins():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        admins = User.query.filter_by(role='admin').all()
        return render_template('developer/admins.html', admins=admins)

    @app.route('/developer/admins/create', methods=['POST'])
    @login_required
    @role_required('developer')
    def create_admin():
        email = request.form.get('email')
        coaching_name = request.form.get('coaching_name')
        if User.query.filter_by(email=email).first():
            flash('Email already exists.')
            return redirect(url_for('manage_admins'))
        password = generate_random_password()
        hashed = generate_password_hash(password)
        user = User(email=email, password_hash=hashed, role='admin', is_active=True, force_password_change=True)
        db.session.add(user)
        db.session.commit()
        admin = Admin(user_id=user.id, coaching_name=coaching_name, subscription_status='active')
        db.session.add(admin)
        db.session.commit()
        if send_email(email, 'Your Admin Account', f'Your login: {email}\nPassword: {password}'):
            flash('Admin created. Password sent via email.')
        else:
            flash(f'Admin created but email failed. Use this password: {password}', 'warning')
        return redirect(url_for('manage_admins'))

    @app.route('/developer/admins/<int:id>/edit', methods=['GET', 'POST'])
    @login_required
    @role_required('developer')
    def edit_admin(id):
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        user = User.query.get_or_404(id)
        if user.role != 'admin':
            abort(404)
        admin = user.admin
        if request.method == 'POST':
            user.email = request.form.get('email')
            admin.coaching_name = request.form.get('coaching_name')
            admin.subscription_status = request.form.get('subscription_status')
            db.session.commit()
            flash('Admin updated.')
            return redirect(url_for('manage_admins'))
        return render_template('developer/edit_admin.html', user=user, admin=admin)

    @app.route('/developer/admins/<int:id>/delete', methods=['POST'])
    @login_required
    @role_required('developer')
    def delete_admin(id):
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        user = User.query.get_or_404(id)
        if user.role != 'admin':
            abort(404)
        db.session.delete(user)
        db.session.commit()
        flash('Admin deleted.')
        return redirect(url_for('manage_admins'))

    @app.route('/developer/admins/<int:id>/toggle-active', methods=['POST'])
    @login_required
    @role_required('developer')
    def toggle_admin_active(id):
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        user = User.query.get_or_404(id)
        if user.role != 'admin':
            abort(404)
        user.is_active = not user.is_active
        db.session.commit()
        flash('Admin status toggled.')
        return redirect(url_for('manage_admins'))

    @app.route('/developer/admins/<int:id>/reset-password', methods=['POST'])
    @login_required
    @role_required('developer')
    def reset_admin_password(id):
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        user = User.query.get_or_404(id)
        if user.role != 'admin':
            abort(404)
        new_password = generate_random_password()
        user.password_hash = generate_password_hash(new_password)
        user.force_password_change = True
        db.session.commit()
        if send_email(user.email, 'Password Reset', f'Your new password: {new_password}'):
            flash('Password reset and sent via email.')
        else:
            flash(f'Password reset but email failed. New password: {new_password}', 'warning')
        return redirect(url_for('manage_admins'))

    # ------------------- Admin Panel -------------------
    @app.route('/admin/dashboard')
    @login_required
    @role_required('admin')
    def admin_dashboard():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))

        teacher_count = User.query.filter_by(role='teacher', admin_id=current_user.id).count()
        student_count = User.query.filter_by(role='student', admin_id=current_user.id).count()
        course_count = Course.query.filter_by(admin_id=current_user.id).count()
        test_count = Test.query.filter_by(admin_id=current_user.id).count()

        # Recent activities: last 5 student/teacher creations
        recent_activities = []
        for student in User.query.filter_by(role='student', admin_id=current_user.id).order_by(User.created_at.desc()).limit(3):
            recent_activities.append({
                'type': 'student',
                'message': f'New student enrolled: {student.email}',
                'time': student.created_at,
                'icon': 'fas fa-graduation-cap',
                'color': 'success'
            })
        for teacher in User.query.filter_by(role='teacher', admin_id=current_user.id).order_by(User.created_at.desc()).limit(3):
            recent_activities.append({
                'type': 'teacher',
                'message': f'Teacher added: {teacher.email}',
                'time': teacher.created_at,
                'icon': 'fas fa-chalkboard-user',
                'color': 'info'
            })
        recent_activities.sort(key=lambda x: x['time'], reverse=True)
        recent_activities = recent_activities[:5]

        # Student growth data for the last 6 months
        today = date.today()
        months = []
        student_counts = []
        for i in range(5, -1, -1):
            month_date = today - relativedelta(months=i)
            month_start = datetime(month_date.year, month_date.month, 1)
            month_end = (month_start + relativedelta(months=1)) - timedelta(days=1)
            months.append(month_date.strftime('%b %Y'))
            count = Student.query.join(User).filter(
                User.created_at >= month_start,
                User.created_at <= month_end,
                User.role == 'student',
                User.admin_id == current_user.id
            ).count()
            student_counts.append(count)

        current_date = date.today().strftime('%A, %d %B %Y')

        return render_template('admin/dashboard.html',
                               teacher_count=teacher_count,
                               student_count=student_count,
                               course_count=course_count,
                               test_count=test_count,
                               recent_activities=recent_activities,
                               months=months,
                               student_counts=student_counts,
                               current_date=current_date,
                               admin=current_user.admin)

    @app.route('/admin/profile', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def admin_profile():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        admin = current_user.admin
        if request.method == 'POST':
            if 'logo' in request.files:
                logo = request.files['logo']
                if logo.filename:
                    ext = logo.filename.rsplit('.', 1)[1].lower() if '.' in logo.filename else 'jpg'
                    filename = f"{uuid.uuid4()}.{ext}"
                    upload_dir = os.path.join('static', 'uploads')
                    os.makedirs(upload_dir, exist_ok=True)
                    logo_path = os.path.join(upload_dir, filename)
                    logo.save(logo_path)
                    admin.logo = f'uploads/{filename}'
            admin.coaching_name = request.form.get('coaching_name')
            db.session.commit()
            flash('Profile updated.')
            return redirect(url_for('admin_profile'))
        return render_template('admin/profile.html', admin=admin)

    @app.route('/admin/teachers')
    @login_required
    @role_required('admin')
    def admin_teachers():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        teachers = User.query.filter_by(role='teacher', admin_id=current_user.id).all()
        return render_template('admin/teachers.html', teachers=teachers)

    @app.route('/admin/teachers/create', methods=['POST'])
    @login_required
    @role_required('admin')
    def create_teacher():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        email = request.form.get('email')
        subject = request.form.get('subject')
        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('admin_teachers'))
        password = generate_random_password()
        hashed = generate_password_hash(password)
        user = User(email=email, password_hash=hashed, role='teacher', admin_id=current_user.id, is_active=True, force_password_change=True)
        db.session.add(user)
        db.session.commit()
        teacher = Teacher(user_id=user.id, subject=subject)
        db.session.add(teacher)
        db.session.commit()
        if send_email(email, 'Your Teacher Account', f'Your login: {email}\nPassword: {password}'):
            flash('Teacher created. Password sent via email.')
        else:
            flash(f'Teacher created but email failed. Use this password: {password}', 'warning')
        return redirect(url_for('admin_teachers'))

    @app.route('/admin/teachers/<int:id>/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def delete_teacher(id):
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        user = User.query.get_or_404(id)
        if user.role != 'teacher' or user.admin_id != current_user.id:
            abort(403)
        db.session.delete(user)
        db.session.commit()
        flash('Teacher deleted.')
        return redirect(url_for('admin_teachers'))

    @app.route('/admin/students')
    @login_required
    @role_required('admin')
    def admin_students():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        students = User.query.filter_by(role='student', admin_id=current_user.id).all()
        courses = Course.query.filter_by(admin_id=current_user.id).all()
        return render_template('admin/students.html', students=students, courses=courses)

    @app.route('/admin/students/create', methods=['POST'])
    @login_required
    @role_required('admin')
    def create_student():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        email = request.form.get('email')
        course_id = request.form.get('course_id')
        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('admin_students'))
        password = generate_random_password()
        hashed = generate_password_hash(password)
        user = User(email=email, password_hash=hashed, role='student', admin_id=current_user.id, is_active=True, force_password_change=True)
        db.session.add(user)
        db.session.commit()
        student = Student(user_id=user.id, course_id=course_id)
        db.session.add(student)
        db.session.commit()
        if send_email(email, 'Your Student Account', f'Your login: {email}\nPassword: {password}'):
            flash('Student created. Password sent via email.')
        else:
            flash(f'Student created but email failed. Use this password: {password}', 'warning')
        return redirect(url_for('admin_students'))

    @app.route('/admin/students/<int:id>/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def delete_student(id):
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        user = User.query.get_or_404(id)
        if user.role != 'student' or user.admin_id != current_user.id:
            abort(403)
        db.session.delete(user)
        db.session.commit()
        flash('Student deleted.')
        return redirect(url_for('admin_students'))

    @app.route('/admin/courses')
    @login_required
    @role_required('admin')
    def admin_courses():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        courses = Course.query.filter_by(admin_id=current_user.id).all()
        return render_template('admin/courses.html', courses=courses)

    @app.route('/admin/courses/create', methods=['POST'])
    @login_required
    @role_required('admin')
    def create_course():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        name = request.form.get('name')
        description = request.form.get('description')
        course = Course(admin_id=current_user.id, name=name, description=description)
        db.session.add(course)
        db.session.commit()
        flash('Course created.')
        return redirect(url_for('admin_courses'))

    @app.route('/admin/courses/<int:id>/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def delete_course(id):
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        course = Course.query.get_or_404(id)
        if course.admin_id != current_user.id:
            abort(403)
        db.session.delete(course)
        db.session.commit()
        flash('Course deleted.')
        return redirect(url_for('admin_courses'))

    @app.route('/admin/tests')
    @login_required
    @role_required('admin')
    def admin_tests():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        tests = Test.query.filter_by(admin_id=current_user.id, is_series=False).all()
        courses = Course.query.filter_by(admin_id=current_user.id).all()
        teachers = User.query.filter_by(role='teacher', admin_id=current_user.id).all()
        return render_template('admin/tests.html', tests=tests, courses=courses, teachers=teachers)

    @app.route('/admin/tests/create', methods=['POST'])
    @login_required
    @role_required('admin')
    def create_test():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        title = request.form.get('title')
        description = request.form.get('description')
        course_id = request.form.get('course_id')
        duration = request.form.get('duration')
        teacher_id = request.form.get('teacher_id')
        test = Test(admin_id=current_user.id, teacher_id=teacher_id, title=title,
                    description=description, course_id=course_id, duration=duration, is_series=False)
        db.session.add(test)
        db.session.commit()
        flash('Test created.')
        return redirect(url_for('admin_tests'))

    @app.route('/admin/test-series')
    @login_required
    @role_required('admin')
    def admin_test_series():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        tests = Test.query.filter_by(admin_id=current_user.id, is_series=True).all()
        courses = Course.query.filter_by(admin_id=current_user.id).all()
        return render_template('admin/test_series.html', tests=tests, courses=courses)

    @app.route('/admin/test-series/create', methods=['POST'])
    @login_required
    @role_required('admin')
    def create_test_series():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        title = request.form.get('title')
        description = request.form.get('description')
        course_id = request.form.get('course_id')
        duration = request.form.get('duration')
        test = Test(admin_id=current_user.id, teacher_id=None, title=title,
                    description=description, course_id=course_id, duration=duration, is_series=True)
        db.session.add(test)
        db.session.commit()
        flash('Test series created.')
        return redirect(url_for('admin_test_series'))

    @app.route('/admin/results')
    @login_required
    @role_required('admin')
    def admin_results():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        students = User.query.filter_by(role='student', admin_id=current_user.id).all()
        student_ids = [s.id for s in students]
        results = Result.query.filter(Result.student_id.in_(student_ids)).order_by(Result.submitted_at.desc()).all()
        return render_template('admin/results.html', results=results)

    # ------------------- Teacher Panel -------------------
    @app.route('/teacher/dashboard')
    @login_required
    @role_required('teacher')
    def teacher_dashboard():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        total_questions = Question.query.filter_by(teacher_id=current_user.id).count()
        total_tests = Test.query.filter_by(teacher_id=current_user.id).count()
        return render_template('teacher/dashboard.html', total_questions=total_questions, total_tests=total_tests)

    @app.route('/teacher/questions', methods=['GET', 'POST'])
    @login_required
    @role_required('teacher')
    def teacher_questions():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        if request.method == 'POST':
            text = request.form.get('text')
            opt_a = request.form.get('opt_a')
            opt_b = request.form.get('opt_b')
            opt_c = request.form.get('opt_c')
            opt_d = request.form.get('opt_d')
            correct = request.form.get('correct')
            q = Question(admin_id=current_user.admin_id, teacher_id=current_user.id,
                         text=text, option_a=opt_a, option_b=opt_b, option_c=opt_c, option_d=opt_d,
                         correct_option=correct)
            db.session.add(q)
            db.session.commit()
            flash('Question added.')
            return redirect(url_for('teacher_questions'))
        questions = Question.query.filter_by(teacher_id=current_user.id).all()
        return render_template('teacher/questions.html', questions=questions)

    @app.route('/teacher/tests', methods=['GET', 'POST'])
    @login_required
    @role_required('teacher')
    def teacher_tests():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            course_id = request.form.get('course_id')
            duration = request.form.get('duration')
            test = Test(admin_id=current_user.admin_id, teacher_id=current_user.id,
                        title=title, description=description, course_id=course_id,
                        duration=duration, is_series=False)
            db.session.add(test)
            db.session.commit()
            flash('Test created.')
            return redirect(url_for('teacher_tests'))
        tests = Test.query.filter_by(teacher_id=current_user.id).all()
        courses = Course.query.filter_by(admin_id=current_user.admin_id).all()
        all_questions = Question.query.filter_by(teacher_id=current_user.id).all()
        return render_template('teacher/tests.html', tests=tests, courses=courses, all_questions=all_questions)

    @app.route('/teacher/tests/<int:test_id>/assign', methods=['POST'])
    @login_required
    @role_required('teacher')
    def assign_questions(test_id):
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        test = Test.query.get_or_404(test_id)
        if test.teacher_id != current_user.id:
            abort(403)
        question_ids = request.form.getlist('question_ids')
        TestQuestion.query.filter_by(test_id=test_id).delete()
        for idx, qid in enumerate(question_ids):
            tq = TestQuestion(test_id=test_id, question_id=qid, order=idx)
            db.session.add(tq)
        db.session.commit()
        flash('Questions assigned.')
        return redirect(url_for('teacher_tests'))

    @app.route('/teacher/results')
    @login_required
    @role_required('teacher')
    def teacher_results():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        tests = Test.query.filter_by(teacher_id=current_user.id).all()
        test_ids = [t.id for t in tests]
        results = Result.query.filter(Result.test_id.in_(test_ids)).order_by(Result.submitted_at.desc()).all()
        return render_template('teacher/results.html', results=results)

    # ------------------- Student Panel -------------------
    @app.route('/student/dashboard')
    @login_required
    @role_required('student')
    def student_dashboard():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        student = current_user.student
        course = Course.query.get(student.course_id) if student.course_id else None
        available_tests = Test.query.filter_by(course_id=student.course_id).all()
        attempted = Result.query.filter_by(student_id=current_user.id).all()
        attempted_test_ids = [r.test_id for r in attempted]
        return render_template('student/dashboard.html', course=course, available_tests=available_tests, attempted_test_ids=attempted_test_ids)

    @app.route('/student/tests')
    @login_required
    @role_required('student')
    def student_tests():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        student = current_user.student
        available_tests = Test.query.filter_by(course_id=student.course_id).all()
        attempted = Result.query.filter_by(student_id=current_user.id).all()
        attempted_test_ids = [r.test_id for r in attempted]
        return render_template('student/tests.html', available_tests=available_tests, attempted_test_ids=attempted_test_ids)

    @app.route('/student/attempt/<int:test_id>', methods=['GET', 'POST'])
    @login_required
    @role_required('student')
    def attempt_test(test_id):
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        test = Test.query.get_or_404(test_id)
        existing = Result.query.filter_by(student_id=current_user.id, test_id=test_id).first()
        if existing:
            flash('You have already attempted this test.')
            return redirect(url_for('student_results'))

        test_questions = TestQuestion.query.filter_by(test_id=test_id).order_by(TestQuestion.order).all()
        questions = [Question.query.get(tq.question_id) for tq in test_questions]

        if request.method == 'POST':
            answers = {}
            correct_count = 0
            for q in questions:
                selected = request.form.get(f'q_{q.id}')
                if selected:
                    answers[q.id] = selected
                    if selected == q.correct_option:
                        correct_count += 1
            total = len(questions)
            wrong = total - correct_count
            score = (correct_count / total) * 100 if total > 0 else 0
            result = Result(student_id=current_user.id, test_id=test_id, score=score,
                            total_questions=total, correct_count=correct_count,
                            wrong_count=wrong, answers_json=json.dumps(answers))
            db.session.add(result)
            db.session.commit()
            flash('Test submitted.')
            return redirect(url_for('student_result_detail', result_id=result.id))

        return render_template('student/attempt_test.html', test=test, questions=questions)

    @app.route('/student/results')
    @login_required
    @role_required('student')
    def student_results():
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        results = Result.query.filter_by(student_id=current_user.id).order_by(Result.submitted_at.desc()).all()
        return render_template('student/results.html', results=results)

    @app.route('/student/result/<int:result_id>')
    @login_required
    @role_required('student')
    def student_result_detail(result_id):
        if current_user.force_password_change:
            return redirect(url_for('change_password'))
        result = Result.query.get_or_404(result_id)
        if result.student_id != current_user.id:
            abort(403)
        answers = json.loads(result.answers_json)
        question_ids = list(answers.keys())
        questions = Question.query.filter(Question.id.in_(question_ids)).all()
        return render_template('student/result_detail.html', result=result, answers=answers, questions=questions)

    return app

# ------------------- Run App -------------------
app = create_app()  # Create app instance at module level (for Gunicorn)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    print("\n" + "="*60)
    print("🚀 COACHING SYSTEM IS STARTING...")
    print("="*60)
    print("\n📋 Default Login Credentials:")
    print("   Developer Email: dev@coaching.com")
    print("   Developer Password: devpass123")
    print(f"\n📍 Access the application at: http://127.0.0.1:{port}")
    print("="*60 + "\n")
    app.run(debug=debug, host='0.0.0.0', port=port)
