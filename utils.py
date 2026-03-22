import json
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from models import User, Admin, Teacher, Student, Course, Question, Test, TestQuestion, Result
from utils import send_email, generate_random_password, role_required
from datetime import datetime

bp = Blueprint('main', __name__)

# ------------------- PUBLIC ROUTES -------------------
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

# ------------------- DEVELOPER PANEL -------------------
@bp.route('/developer/dashboard')
@login_required
@role_required('developer')
def developer_dashboard():
    total_admins = User.query.filter_by(role='admin').count()
    return render_template('developer/dashboard.html', total_admins=total_admins)

@bp.route('/developer/admins')
@login_required
@role_required('developer')
def manage_admins():
    admins = User.query.filter_by(role='admin').all()
    return render_template('developer/admins.html', admins=admins)

@bp.route('/developer/admins/create', methods=['POST'])
@login_required
@role_required('developer')
def create_admin():
    email = request.form.get('email')
    coaching_name = request.form.get('coaching_name')
    if User.query.filter_by(email=email).first():
        flash('Email already exists.')
        return redirect(url_for('main.manage_admins'))
    password = generate_random_password()
    hashed = generate_password_hash(password)
    user = User(email=email, password_hash=hashed, role='admin', is_active=True)
    db.session.add(user)
    db.session.commit()
    admin = Admin(user_id=user.id, coaching_name=coaching_name, subscription_status='active')
    db.session.add(admin)
    db.session.commit()
    send_email(email, 'Your Admin Account', f'Your login: {email}\nPassword: {password}')
    flash('Admin created. Password sent via email.')
    return redirect(url_for('main.manage_admins'))

@bp.route('/developer/admins/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('developer')
def edit_admin(id):
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
        return redirect(url_for('main.manage_admins'))
    return render_template('developer/edit_admin.html', user=user, admin=admin)

@bp.route('/developer/admins/<int:id>/delete', methods=['POST'])
@login_required
@role_required('developer')
def delete_admin(id):
    user = User.query.get_or_404(id)
    if user.role != 'admin':
        abort(404)
    db.session.delete(user)
    db.session.commit()
    flash('Admin deleted.')
    return redirect(url_for('main.manage_admins'))

@bp.route('/developer/admins/<int:id>/toggle-active', methods=['POST'])
@login_required
@role_required('developer')
def toggle_admin_active(id):
    user = User.query.get_or_404(id)
    if user.role != 'admin':
        abort(404)
    user.is_active = not user.is_active
    db.session.commit()
    flash('Admin status toggled.')
    return redirect(url_for('main.manage_admins'))

@bp.route('/developer/admins/<int:id>/reset-password', methods=['POST'])
@login_required
@role_required('developer')
def reset_admin_password(id):
    user = User.query.get_or_404(id)
    if user.role != 'admin':
        abort(404)
    new_password = generate_random_password()
    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    send_email(user.email, 'Password Reset', f'Your new password: {new_password}')
    flash('Password reset and sent via email.')
    return redirect(url_for('main.manage_admins'))

# ------------------- ADMIN PANEL -------------------
@bp.route('/admin/dashboard')
@login_required
@role_required('admin')
def admin_dashboard():
    teacher_count = User.query.filter_by(role='teacher', admin_id=current_user.id).count()
    student_count = User.query.filter_by(role='student', admin_id=current_user.id).count()
    course_count = Course.query.filter_by(admin_id=current_user.id).count()
    test_count = Test.query.filter_by(admin_id=current_user.id).count()
    return render_template('admin/dashboard.html', 
                           teacher_count=teacher_count, student_count=student_count,
                           course_count=course_count, test_count=test_count)

@bp.route('/admin/profile', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_profile():
    admin = current_user.admin
    if request.method == 'POST':
        if 'logo' in request.files:
            logo = request.files['logo']
            if logo.filename:
                import os
                from werkzeug.utils import secure_filename
                filename = secure_filename(logo.filename)
                logo_path = os.path.join('static/uploads', filename)
                logo.save(logo_path)
                admin.logo = logo_path
        admin.coaching_name = request.form.get('coaching_name')
        db.session.commit()
        flash('Profile updated.')
        return redirect(url_for('main.admin_profile'))
    return render_template('admin/profile.html', admin=admin)

@bp.route('/admin/teachers')
@login_required
@role_required('admin')
def admin_teachers():
    teachers = User.query.filter_by(role='teacher', admin_id=current_user.id).all()
    return render_template('admin/teachers.html', teachers=teachers)

@bp.route('/admin/teachers/create', methods=['POST'])
@login_required
@role_required('admin')
def create_teacher():
    email = request.form.get('email')
    subject = request.form.get('subject')
    if User.query.filter_by(email=email).first():
        flash('Email already exists')
        return redirect(url_for('main.admin_teachers'))
    password = generate_random_password()
    hashed = generate_password_hash(password)
    user = User(email=email, password_hash=hashed, role='teacher', admin_id=current_user.id, is_active=True)
    db.session.add(user)
    db.session.commit()
    teacher = Teacher(user_id=user.id, subject=subject)
    db.session.add(teacher)
    db.session.commit()
    send_email(email, 'Your Teacher Account', f'Your login: {email}\nPassword: {password}')
    flash('Teacher created. Password sent via email.')
    return redirect(url_for('main.admin_teachers'))

@bp.route('/admin/teachers/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_teacher(id):
    user = User.query.get_or_404(id)
    if user.role != 'teacher' or user.admin_id != current_user.id:
        abort(403)
    db.session.delete(user)
    db.session.commit()
    flash('Teacher deleted.')
    return redirect(url_for('main.admin_teachers'))

@bp.route('/admin/students')
@login_required
@role_required('admin')
def admin_students():
    students = User.query.filter_by(role='student', admin_id=current_user.id).all()
    courses = Course.query.filter_by(admin_id=current_user.id).all()
    return render_template('admin/students.html', students=students, courses=courses)

@bp.route('/admin/students/create', methods=['POST'])
@login_required
@role_required('admin')
def create_student():
    email = request.form.get('email')
    course_id = request.form.get('course_id')
    if User.query.filter_by(email=email).first():
        flash('Email already exists')
        return redirect(url_for('main.admin_students'))
    password = generate_random_password()
    hashed = generate_password_hash(password)
    user = User(email=email, password_hash=hashed, role='student', admin_id=current_user.id, is_active=True)
    db.session.add(user)
    db.session.commit()
    student = Student(user_id=user.id, course_id=course_id)
    db.session.add(student)
    db.session.commit()
    send_email(email, 'Your Student Account', f'Your login: {email}\nPassword: {password}')
    flash('Student created. Password sent via email.')
    return redirect(url_for('main.admin_students'))

@bp.route('/admin/students/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_student(id):
    user = User.query.get_or_404(id)
    if user.role != 'student' or user.admin_id != current_user.id:
        abort(403)
    db.session.delete(user)
    db.session.commit()
    flash('Student deleted.')
    return redirect(url_for('main.admin_students'))

@bp.route('/admin/courses')
@login_required
@role_required('admin')
def admin_courses():
    courses = Course.query.filter_by(admin_id=current_user.id).all()
    return render_template('admin/courses.html', courses=courses)

@bp.route('/admin/courses/create', methods=['POST'])
@login_required
@role_required('admin')
def create_course():
    name = request.form.get('name')
    description = request.form.get('description')
    course = Course(admin_id=current_user.id, name=name, description=description)
    db.session.add(course)
    db.session.commit()
    flash('Course created.')
    return redirect(url_for('main.admin_courses'))

@bp.route('/admin/courses/<int:id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def delete_course(id):
    course = Course.query.get_or_404(id)
    if course.admin_id != current_user.id:
        abort(403)
    db.session.delete(course)
    db.session.commit()
    flash('Course deleted.')
    return redirect(url_for('main.admin_courses'))

@bp.route('/admin/tests')
@login_required
@role_required('admin')
def admin_tests():
    tests = Test.query.filter_by(admin_id=current_user.id, is_series=False).all()
    courses = Course.query.filter_by(admin_id=current_user.id).all()
    teachers = User.query.filter_by(role='teacher', admin_id=current_user.id).all()
    return render_template('admin/tests.html', tests=tests, courses=courses, teachers=teachers)

@bp.route('/admin/tests/create', methods=['POST'])
@login_required
@role_required('admin')
def create_test():
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
    return redirect(url_for('main.admin_tests'))

@bp.route('/admin/test-series')
@login_required
@role_required('admin')
def admin_test_series():
    tests = Test.query.filter_by(admin_id=current_user.id, is_series=True).all()
    courses = Course.query.filter_by(admin_id=current_user.id).all()
    return render_template('admin/test_series.html', tests=tests, courses=courses)

@bp.route('/admin/test-series/create', methods=['POST'])
@login_required
@role_required('admin')
def create_test_series():
    title = request.form.get('title')
    description = request.form.get('description')
    course_id = request.form.get('course_id')
    duration = request.form.get('duration')
    test = Test(admin_id=current_user.id, teacher_id=None, title=title,
                description=description, course_id=course_id, duration=duration, is_series=True)
    db.session.add(test)
    db.session.commit()
    flash('Test series created.')
    return redirect(url_for('main.admin_test_series'))

@bp.route('/admin/results')
@login_required
@role_required('admin')
def admin_results():
    # Fetch all results for admin's students
    students = User.query.filter_by(role='student', admin_id=current_user.id).all()
    student_ids = [s.id for s in students]
    results = Result.query.filter(Result.student_id.in_(student_ids)).order_by(Result.submitted_at.desc()).all()
    return render_template('admin/results.html', results=results)

# ------------------- TEACHER PANEL -------------------
@bp.route('/teacher/dashboard')
@login_required
@role_required('teacher')
def teacher_dashboard():
    total_questions = Question.query.filter_by(teacher_id=current_user.id).count()
    total_tests = Test.query.filter_by(teacher_id=current_user.id).count()
    return render_template('teacher/dashboard.html', total_questions=total_questions, total_tests=total_tests)

@bp.route('/teacher/questions', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def teacher_questions():
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
        return redirect(url_for('main.teacher_questions'))
    questions = Question.query.filter_by(teacher_id=current_user.id).all()
    return render_template('teacher/questions.html', questions=questions)

@bp.route('/teacher/tests', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def teacher_tests():
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
        return redirect(url_for('main.teacher_tests'))
    tests = Test.query.filter_by(teacher_id=current_user.id).all()
    courses = Course.query.filter_by(admin_id=current_user.admin_id).all()
    # For assigning questions to test
    all_questions = Question.query.filter_by(teacher_id=current_user.id).all()
    return render_template('teacher/tests.html', tests=tests, courses=courses, all_questions=all_questions)

@bp.route('/teacher/tests/<int:test_id>/assign', methods=['POST'])
@login_required
@role_required('teacher')
def assign_questions(test_id):
    test = Test.query.get_or_404(test_id)
    if test.teacher_id != current_user.id:
        abort(403)
    question_ids = request.form.getlist('question_ids')
    # Remove existing assignments
    TestQuestion.query.filter_by(test_id=test_id).delete()
    for idx, qid in enumerate(question_ids):
        tq = TestQuestion(test_id=test_id, question_id=qid, order=idx)
        db.session.add(tq)
    db.session.commit()
    flash('Questions assigned.')
    return redirect(url_for('main.teacher_tests'))

@bp.route('/teacher/results')
@login_required
@role_required('teacher')
def teacher_results():
    # Get results for tests created by this teacher
    tests = Test.query.filter_by(teacher_id=current_user.id).all()
    test_ids = [t.id for t in tests]
    results = Result.query.filter(Result.test_id.in_(test_ids)).order_by(Result.submitted_at.desc()).all()
    return render_template('teacher/results.html', results=results)

# ------------------- STUDENT PANEL -------------------
@bp.route('/student/dashboard')
@login_required
@role_required('student')
def student_dashboard():
    # Get assigned course
    student = current_user.student
    course = Course.query.get(student.course_id) if student.course_id else None
    # Get available tests for this course
    available_tests = Test.query.filter_by(course_id=student.course_id).all()
    # Get attempted tests
    attempted = Result.query.filter_by(student_id=current_user.id).all()
    attempted_test_ids = [r.test_id for r in attempted]
    return render_template('student/dashboard.html', course=course, available_tests=available_tests, attempted_test_ids=attempted_test_ids)

@bp.route('/student/tests')
@login_required
@role_required('student')
def student_tests():
    student = current_user.student
    available_tests = Test.query.filter_by(course_id=student.course_id).all()
    attempted = Result.query.filter_by(student_id=current_user.id).all()
    attempted_test_ids = [r.test_id for r in attempted]
    return render_template('student/tests.html', available_tests=available_tests, attempted_test_ids=attempted_test_ids)

@bp.route('/student/attempt/<int:test_id>', methods=['GET', 'POST'])
@login_required
@role_required('student')
def attempt_test(test_id):
    test = Test.query.get_or_404(test_id)
    # Check if student already attempted
    existing = Result.query.filter_by(student_id=current_user.id, test_id=test_id).first()
    if existing:
        flash('You have already attempted this test.')
        return redirect(url_for('main.student_results'))

    # Get questions
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
        return redirect(url_for('main.student_result_detail', result_id=result.id))

    return render_template('student/attempt_test.html', test=test, questions=questions)

@bp.route('/student/results')
@login_required
@role_required('student')
def student_results():
    results = Result.query.filter_by(student_id=current_user.id).order_by(Result.submitted_at.desc()).all()
    return render_template('student/results.html', results=results)

@bp.route('/student/result/<int:result_id>')
@login_required
@role_required('student')
def student_result_detail(result_id):
    result = Result.query.get_or_404(result_id)
    if result.student_id != current_user.id:
        abort(403)
    answers = json.loads(result.answers_json)
    # Fetch questions
    question_ids = list(answers.keys())
    questions = Question.query.filter(Question.id.in_(question_ids)).all()
    return render_template('student/result_detail.html', result=result, answers=answers, questions=questions)