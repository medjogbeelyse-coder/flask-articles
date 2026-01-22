from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from flask_sqlalchemy import SQLAlchemy
from urllib.parse import quote_plus
from datetime import datetime, timedelta, timezone
from werkzeug.utils import secure_filename
import os
import cloudinary
import cloudinary.uploader

# ===== APP INIT =====
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'une_cle_secrete_tres_sure')

app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.permanent_session_lifetime = timedelta(minutes=30)

ADMIN_WHATSAPP_NUMBER = '22968593238'
MIN_INVESTMENT_AMOUNT = 50000
ADMIN_PASSWORD = "Azouassi@11"

# ===== DATABASE CONFIG =====
supabase_password = quote_plus("Medjogbe@11")  # mot de passe Supabase
SUPABASE_URI = f"postgresql://postgres:{supabase_password}@db.mqjbgfiqyhgveicjubcs.supabase.co:5432/postgres"
LOCAL_URI = "sqlite:///local_dev.db"

# Tentative Supabase sinon fallback SQLite
try:
    from sqlalchemy import create_engine
    engine = create_engine(SUPABASE_URI, connect_args={"connect_timeout": 5})
    conn = engine.connect()
    conn.close()
    app.config['SQLALCHEMY_DATABASE_URI'] = SUPABASE_URI
    print("✅ Connexion Supabase OK")
except Exception as e:
    print("⚠️ Connexion Supabase échouée, fallback vers SQLite local")
    print(e)
    app.config['SQLALCHEMY_DATABASE_URI'] = LOCAL_URI

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ===== CLOUDINARY =====
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
    secure=True
)

# ===== MODELS =====
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    designation = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    is_footer = db.Column(db.Boolean, default=False)
    price = db.Column(db.Float, default=0)
    image = db.Column(db.String(255), nullable=True)

class FeatureFlag(db.Model):
    key = db.Column(db.String(50), primary_key=True)
    active = db.Column(db.Boolean, default=True)

class AdminLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class RateLimit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(100))
    endpoint = db.Column(db.String(100))
    count = db.Column(db.Integer, default=0)
    last_time = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

# ===== HELPERS =====
def log_action(action):
    db.session.add(AdminLog(action=action))
    db.session.commit()

def check_rate_limit(ip, endpoint, limit=5, minutes=1):
    record = RateLimit.query.filter_by(ip=ip, endpoint=endpoint).first()
    now = datetime.now(timezone.utc)
    if not record:
        record = RateLimit(ip=ip, endpoint=endpoint, count=1, last_time=now)
        db.session.add(record)
        db.session.commit()
        return True
    if now - record.last_time > timedelta(minutes=minutes):
        record.count = 1
        record.last_time = now
        db.session.commit()
        return True
    if record.count >= limit:
        return False
    record.count += 1
    db.session.commit()
    return True

def is_admin_logged_in():
    return session.get('logged_in', False)

def feature_active(key):
    flag = FeatureFlag.query.filter_by(key=key).first()
    return flag and flag.active

def get_products(category=None):
    q = Product.query
    if category:
        q = q.filter_by(category=category)
    return q.all()

@app.template_filter('get_attr')
def get_attr(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

@app.context_processor
def inject_flags():
    return {'flags': {f.key: f.active for f in FeatureFlag.query.all()}}

# ===== INIT DB =====
def initialize_db():
    db.create_all()
    for key in ['COMMERCE_ACTIVE', 'INVESTISSEMENT_ACTIVE', 'RECRUTEMENT_ACTIVE']:
        if not FeatureFlag.query.filter_by(key=key).first():
            db.session.add(FeatureFlag(key=key, active=True))
    db.session.commit()

# ===== ROUTES ADMIN =====
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if is_admin_logged_in():
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        if not check_rate_limit(request.remote_addr, 'admin_login'):
            abort(429)
        if request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            session.permanent = True
            log_action("Connexion admin")
            return redirect(url_for('admin_dashboard'))
        flash("Mot de passe invalide")
    return render_template('admin-login.html')

@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if not is_admin_logged_in():
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        if 'designation' in request.form:
            image_file = request.files.get('image')
            image_url = None
            if image_file and image_file.filename:
                upload_result = cloudinary.uploader.upload(image_file)
                image_url = upload_result['secure_url']

            p = Product(
                designation=request.form['designation'],
                category=request.form['category'],
                is_footer=bool(request.form.get('is_footer')),
                price=float(request.form.get('price', 0)),
                image=image_url
            )
            db.session.add(p)
            db.session.commit()
            log_action(f"Ajout produit {p.designation}")

        elif 'delete_id' in request.form:
            p = Product.query.get(int(request.form['delete_id']))
            if p:
                db.session.delete(p)
                db.session.commit()
                log_action(f"Suppression produit {p.designation}")

        elif 'flag_key' in request.form:
            flag = FeatureFlag.query.filter_by(key=request.form['flag_key']).first()
            if flag:
                flag.active = not flag.active
                db.session.commit()
                log_action(f"Toggle {flag.key}")

        return redirect(url_for('admin_dashboard'))

    return render_template(
        'admin-dashboard.html',
        products_foyer=get_products('foyer'),
        products_marche=get_products('marche')
    )

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    log_action("Déconnexion admin")
    return redirect(url_for('home'))

# ===== ROUTES PUBLIQUES =====
@app.route('/')
@app.route('/presentation')
def presentation():
    return render_template('presentation.html')

@app.route('/home')
def home():
    return render_template('index.html')

@app.route('/commerce')
def commerce():
    if not feature_active('COMMERCE_ACTIVE'):
        return render_template('indisponible.html', section_name="Commerce")
    return render_template(
        'commerce.html',
        articles_foyer=get_products('foyer'),
        produits_marche=get_products('marche')
    )

@app.route('/investissement', methods=['GET', 'POST'])
def investissement():
    if not feature_active('INVESTISSEMENT_ACTIVE'):
        return render_template('indisponible.html', section_name="Investissement")
    if request.method == 'POST':
        if not check_rate_limit(request.remote_addr, 'investissement'):
            abort(429)
        montant = int(request.form.get('montant', 0))
        if montant < MIN_INVESTMENT_AMOUNT:
            return redirect(url_for('investissement'))
        msg = quote_plus(f"Investissement\nNom:{request.form.get('nom')}\nMontant:{montant}")
        return redirect(f"https://wa.me/{ADMIN_WHATSAPP_NUMBER}?text={msg}")
    return render_template('investissement.html')

@app.route('/recrutement', methods=['GET', 'POST'])
def recrutement():
    if not feature_active('RECRUTEMENT_ACTIVE'):
        return render_template('indisponible.html', section_name="Recrutement")
    if request.method == 'POST':
        if not check_rate_limit(request.remote_addr, 'recrutement'):
            abort(429)
        msg = quote_plus(f"Candidature {request.form.get('prenom')} {request.form.get('nom')}")
        return redirect(f"https://wa.me/{ADMIN_WHATSAPP_NUMBER}?text={msg}")
    return render_template('recrutement.html')

# ===== MAIN =====
if __name__ == '__main__':
    with app.app_context():
        initialize_db()
    app.run(host='0.0.0.0', port=5000, debug=False)
