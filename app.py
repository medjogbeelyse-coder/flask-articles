# app.py complet - Flask + Admin + SQLite pour Muni-Commerce

from flask import Flask, render_template, request, redirect, url_for, flash, session
from urllib.parse import quote_plus
import sqlite3
import os

# --- Configuration de l'application ---
app = Flask(__name__)
app.secret_key = 'une_cle_secrete_tres_sure'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# --- Variables globales ---
ADMIN_WHATSAPP_NUMBER = '22968593238'
MIN_INVESTMENT_AMOUNT = 50000
ADMIN_PASSWORD = 'Azouassi@11'

# --- Feature flags ---
FEATURE_FLAGS = {
    'COMMERCE_ACTIVE': True,
    'INVESTISSEMENT_ACTIVE': True,
    'RECRUTEMENT_ACTIVE': True
}

# --- Base de données SQLite ---
DB_NAME = "commerce.db"

def init_db():
    """Crée les tables si elles n'existent pas."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Table produits avec prix
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            designation TEXT NOT NULL,
            category TEXT NOT NULL,
            is_footer INTEGER DEFAULT 0,
            price REAL DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def get_products(category=None):
    """Récupère les produits, éventuellement filtrés par catégorie."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if category:
        c.execute("SELECT id, designation, category, is_footer, price FROM products WHERE category=? ORDER BY id ASC", (category,))
    else:
        c.execute("SELECT id, designation, category, is_footer, price FROM products ORDER BY id ASC")
    rows = c.fetchall()
    conn.close()
    return [{'id': r[0], 'designation': r[1], 'category': r[2], 'is_footer': bool(r[3]), 'price': r[4]} for r in rows]

def add_product(designation, category, is_footer=0, price=0):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO products (designation, category, is_footer, price) VALUES (?, ?, ?, ?)",
              (designation, category, is_footer, price))
    conn.commit()
    conn.close()

def delete_product(product_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id=?", (product_id,))
    conn.commit()
    conn.close()

# --- Fonctions utilitaires ---
def check_feature_active(feature_key):
    if not FEATURE_FLAGS.get(feature_key, False):
        return render_template('indisponible.html', section_name=feature_key.split('_')[0].capitalize())
    return None

def is_admin_logged_in():
    return session.get('logged_in', False)

# --- Routes Admin ---
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if is_admin_logged_in():
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash("Connexion Administrateur réussie !", 'admin_success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Mot de passe invalide.", 'admin_error')
    return render_template('admin-login.html')

@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if not is_admin_logged_in():
        flash("Veuillez vous connecter.", 'admin_warning')
        return redirect(url_for('admin_login'))

    # POST = ajout ou suppression produit
    if request.method == 'POST':
        # Ajouter produit
        if 'designation' in request.form and 'category' in request.form:
            designation = request.form['designation']
            category = request.form['category']
            is_footer = 1 if request.form.get('is_footer') else 0
            try:
                price = float(request.form.get('price', 0))
            except ValueError:
                price = 0
            add_product(designation, category, is_footer, price)
            flash(f"Produit '{designation}' ajouté avec succès.", 'admin_success')
            return redirect(url_for('admin_dashboard'))

        # Supprimer produit
        elif 'delete_id' in request.form:
            delete_product(int(request.form['delete_id']))
            flash("Produit supprimé avec succès.", 'admin_success')
            return redirect(url_for('admin_dashboard'))

    # GET = afficher les produits par catégorie
    products_foyer = get_products('foyer')
    products_marche = get_products('marche')
    return render_template(
        'admin-dashboard.html',
        products_foyer=products_foyer,
        products_marche=products_marche,
        flags=FEATURE_FLAGS
    )

@app.route('/admin/logout')
def admin_logout():
    session.pop('logged_in', None)
    flash("Déconnexion réussie.", 'admin_info')
    return redirect(url_for('home'))

# --- Routes principales ---
@app.route('/')
@app.route('/presentation')
def presentation():
    return render_template('presentation.html', flags=FEATURE_FLAGS)

@app.route('/home')
def home():
    return render_template('index.html', flags=FEATURE_FLAGS)

@app.route('/commerce')
def commerce():
    redirect_response = check_feature_active('COMMERCE_ACTIVE')
    if redirect_response:
        return redirect_response

    articles_foyer = get_products('foyer')
    produits_marche = get_products('marche')
    return render_template('commerce.html', articles_foyer=articles_foyer, produits_marche=produits_marche, flags=FEATURE_FLAGS)

@app.route('/investissement', methods=['GET', 'POST'])
def investissement():
    redirect_response = check_feature_active('INVESTISSEMENT_ACTIVE')
    if redirect_response:
        return redirect_response

    if request.method == 'POST':
        nom = request.form.get('nom')
        montant_str = request.form.get('montant')
        try:
            montant = int(montant_str)
        except ValueError:
            flash("Montant invalide.", 'error')
            return redirect(url_for('investissement'))

        if montant < MIN_INVESTMENT_AMOUNT:
            flash(f"Montant minimum: {MIN_INVESTMENT_AMOUNT} F.", 'error')
            return redirect(url_for('investissement'))

        message_to_admin = f"🚀 Nouvelle promesse d'investissement 🚀\nNom: {nom}\nMontant: {montant} F"
        encoded_message = quote_plus(message_to_admin)
        whatsapp_url = f"https://wa.me/{ADMIN_WHATSAPP_NUMBER}?text={encoded_message}"
        flash("Redirection vers WhatsApp pour finalisation.", 'success')
        return redirect(whatsapp_url)

    return render_template('investissement.html', flags=FEATURE_FLAGS)

@app.route('/recrutement', methods=['GET', 'POST'])
def recrutement():
    redirect_response = check_feature_active('RECRUTEMENT_ACTIVE')
    if redirect_response:
        return redirect_response

    if request.method == 'POST':
        prenom = request.form.get('prenom')
        nom = request.form.get('nom')
        message_to_admin = f"👤 Candidature: {prenom} {nom}"
        encoded_message = quote_plus(message_to_admin)
        whatsapp_url = f"https://wa.me/{ADMIN_WHATSAPP_NUMBER}?text={encoded_message}"
        flash("Redirection vers WhatsApp pour confirmation.", 'success')
        return redirect(whatsapp_url)

    return render_template('recrutement.html', flags=FEATURE_FLAGS)

# --- Démarrage ---
if __name__ == '__main__':
    if not os.path.exists(DB_NAME):
        init_db()
    app.run(debug=True)
