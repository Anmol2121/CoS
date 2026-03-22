from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from models import User, Admin, Teacher, Student, Course
from utils import send_email, generate_random_password, role_required
import datetime

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password) and user.is_active:
            login_user(user)
            # Redirect based on role
            if user.role == 'developer':
                return redirect(url_for('main.developer_dashboard'))
            elif user.role == 'admin':
                return redirect(url_for('main.admin_dashboard'))
            elif user.role == 'teacher':
                return redirect(url_for('main.teacher_dashboard'))
            elif user.role == 'student':
                return redirect(url_for('main.student_dashboard'))
        flash('Invalid email or password')
    return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if user:
            # Generate token and send email
            from itsdangerous import URLSafeTimedSerializer
            s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
            token = s.dumps(email, salt='password-reset')
            reset_url = url_for('main.reset_password', token=token, _external=True)
            send_email(email, 'Password Reset', f'Click here to reset your password: {reset_url}')
            flash('Password reset link sent to your email.')
        else:
            flash('Email not found.')
    return render_template('forgot_password.html')

@bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    from itsdangerous import URLSafeTimedSerializer
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = s.loads(token, salt='password-reset', max_age=3600)
    except:
        flash('Invalid or expired token.')
        return redirect(url_for('main.login'))
    if request.method == 'POST':
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user:
            user.password_hash = generate_password_hash(password)
            db.session.commit()
            flash('Password updated. Please login.')
            return redirect(url_for('main.login'))
    return render_template('reset_password.html')


@bp.route('/teacher/questions', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def teacher_questions():
    if request.method == 'POST':
        text = request.form['text']
        opt_a = request.form['opt_a']
        opt_b = request.form['opt_b']
        opt_c = request.form['opt_c']
        opt_d = request.form['opt_d']
        correct = request.form['correct']
        q = Question(admin_id=current_user.admin_id, teacher_id=current_user.id,
                     text=text, option_a=opt_a, option_b=opt_b, option_c=opt_c, option_d=opt_d,
                     correct_option=correct)
        db.session.add(q)
        db.session.commit()
        flash('Question added')
        return redirect(url_for('main.teacher_questions'))
    questions = Question.query.filter_by(teacher_id=current_user.id).all()
    return render_template('teacher/questions.html', questions=questions)