import os
import cloudinary
import cloudinary.uploader
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "prime_business_2026_key")

# --- 1. CONFIGURATION DE LA BASE (VERROUILLÉE) ---
# On définit les deux URLs clairement
URL_INTERNE = "postgresql://admin_primebusiness:fVTSULMTtE7HZDlZa5WRok4L5Fw8UXJc@dpg-d5sjmke3jp1c738b13q0-a/primebusiness_data"
URL_EXTERNE = "postgresql://admin_primebusiness:fVTSULMTtE7HZDlZa5WRok4L5Fw8UXJc@dpg-d5sjmke3jp1c738b13q0-a.virginia-postgres.render.com/primebusiness_data?sslmode=require"

# Si on est sur Render, on prend l'interne, sinon l'externe
if os.environ.get('RENDER') == 'True':
    uri = URL_INTERNE
else:
    uri = URL_EXTERNE

# Sécurité supplémentaire : si l'URL commence par postgres:// (sans le ql), on corrige
if uri and uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- 2. MODÈLES ---
class Produit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    designation = db.Column(db.String(100), nullable=False)
    prix = db.Column(db.Float, nullable=False)
    section = db.Column(db.String(50), nullable=False)
    image = db.Column(db.String(255))
    cloudinary_id = db.Column(db.String(100))

class Poste(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titre = db.Column(db.String(100), nullable=False)

class FeatureFlag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True)

# --- 3. CONFIGURATION CLOUDINARY ---
cloudinary.config( 
  cloud_name = "ds5exviel", 
  api_key = "128277898241178", 
  api_secret = "VhODvT9UTr0wim4SZuFPR-UmixE"
)

# --- 4. INJECTION DES FLAGS ---
@app.context_processor
def inject_flags():
    try:
        flags = {f.key: f.active for f in FeatureFlag.query.all()}
        return {'flags': flags}
    except:
        return {'flags': {'commerce': True, 'investissement': True, 'recrutement': True}}

# --- 5. INITIALISATION DES TABLES ---
with app.app_context():
    try:
        db.create_all()
        if not FeatureFlag.query.first():
            for k in ["commerce", "investissement", "recrutement"]:
                db.session.add(FeatureFlag(key=k, active=True))
            db.session.commit()
    except Exception as e:
        print(f"⚠️ Erreur DB: {e}")

# --- ROUTES ---

@app.route("/")
def presentation():
    return render_template("presentation.html")

@app.route("/accueil")
def home():
    return render_template("index.html")

@app.route("/section/<name>")
def view_section(name):
    try:
        flag = FeatureFlag.query.filter_by(key=name).first()
        if flag and flag.active:
            if name == "investissement":
                return render_template("section_investissement.html")
            if name == "recrutement":
                postes_list = Poste.query.all()
                return render_template("section_recrutement.html", postes=postes_list)
            
            prods = Produit.query.all()
            return render_template("section.html", name=name, produits=prods)
    except:
        pass
    return redirect(url_for('home'))

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        # Remplace 'votre_mot_de_passe' par ton mot de passe réel
        if request.form.get("password") == os.environ.get("ADMIN_PWD", "Azouassi@11"): 
            session["admin_logged_in"] = True
            return redirect(url_for("admin_panel"))
        flash("Mot de passe incorrect")
    return render_template("admin_login.html")

@app.route("/admin/panel", methods=["GET", "POST"])
def admin_panel():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    try:
        if request.method == "POST":
            if "flag_key" in request.form:
                f = FeatureFlag.query.filter_by(key=request.form.get("flag_key")).first()
                if f:
                    f.active = not f.active
                    db.session.commit()
            
            elif "designation" in request.form:
                file = request.files.get('image_file')
                img_url, p_id = "", ""
                if file and file.filename != '':
                    res = cloudinary.uploader.upload(file)
                    img_url, p_id = res['secure_url'], res['public_id']
                
                new_p = Produit(designation=request.form.get("designation"), 
                                prix=float(request.form.get("price")),
                                section=request.form.get("category"), 
                                image=img_url, cloudinary_id=p_id)
                db.session.add(new_p)
                db.session.commit()

            elif "delete_id" in request.form:
                p = Produit.query.get(int(request.form.get("delete_id")))
                if p:
                    if p.cloudinary_id: cloudinary.uploader.destroy(p.cloudinary_id)
                    db.session.delete(p)
                    db.session.commit()

            elif "titre_poste" in request.form:
                db.session.add(Poste(titre=request.form.get("titre_poste")))
                db.session.commit()

            elif "delete_poste_id" in request.form:
                po = Poste.query.get(int(request.form.get("delete_poste_id")))
                if po:
                    db.session.delete(po)
                    db.session.commit()

            return redirect(url_for("admin_panel"))

        return render_template("admin_panel.html", 
                               flags={f.key: f.active for f in FeatureFlag.query.all()}, 
                               produits=Produit.query.all(), 
                               postes=Poste.query.all())
    except Exception as e:
        return f"Erreur: {str(e)}"

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("presentation"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)