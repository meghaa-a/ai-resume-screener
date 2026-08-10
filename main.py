from flask import Flask, request, render_template, send_file,redirect
import os
import PyPDF2
import docx2txt
import re
from skills import extract_skills
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import csv
import sqlite3


def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # Existing table
    c.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        skill_score REAL,
        ai_score REAL
    )
    """)

    # NEW TABLE
    c.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        description TEXT
    )
    """)

    conn.commit()
    conn.close()
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}

from flask import Flask, render_template, request, session, redirect, url_for

app = Flask(__name__)

app.secret_key = "your_secret_key"
latest_results = []
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ================== UTIL FUNCTIONS ==================

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def clean_text(text):
    text = text.lower()
    text = re.sub(r"\W+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


# ================== FILE EXTRACTION ==================

def extract_text_pdf(file_path):
    text = ""
    with open(file_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            if page.extract_text():
                text += page.extract_text()
    return text


def extract_text_docx(file_path):
    return docx2txt.process(file_path)


def extract_text_txt(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()


def extract_text(file_path):
    if file_path.endswith(".pdf"):
        return extract_text_pdf(file_path)
    elif file_path.endswith(".docx"):
        return extract_text_docx(file_path)
    elif file_path.endswith(".txt"):
        return extract_text_txt(file_path)
    return ""


# ================== MATCHING ==================

def match_resumes(job_description, resumes):
    documents = [job_description] + resumes

    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(documents)

    similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]

    ranked = sorted(
        enumerate(similarity),
        key=lambda x: x[1],
        reverse=True
    )

    return ranked


# ================== ROUTES ==================
@app.route("/add_job", methods=["POST"])
def add_job():
    title = request.form.get("title").strip().lower()
    description = request.form.get("description")

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # 🔍 CHECK if job already exists
    c.execute("SELECT * FROM jobs WHERE LOWER(title)=?", (title,))
    existing = c.fetchone()

    if existing:
        conn.close()
        return redirect("/dashboard")  # already exists → do nothing

    # ✅ Insert only if not exists
    c.execute(
        "INSERT INTO jobs (title, description) VALUES (?, ?)",
        (title, description)
    )

    conn.commit()
    conn.close()

    return redirect("/dashboard")
@app.route("/dashboard")
def dashboard():
    import sqlite3

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT * FROM jobs")
    jobs = c.fetchall()

    conn.close()

    return render_template("dashboard.html", jobs=jobs)
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/analyzer")
def analyzer():
    return render_template("app.html")


@app.route("/upload", methods=["GET", "POST"])
def upload():

    global latest_results
    if request.method == "GET":

        results = session.pop("results", None)
        message = session.pop("message", None)
        job_desc = session.pop("job_desc", "")

        return render_template(
            "app.html",
            results=results,
            message=message,
            job_desc=job_desc
        )

    jd = request.form.get("resumeText", "")
    resume_files = request.files.getlist("resumeFile")

    if not jd and not resume_files:
        return render_template(
        "app.html",
        message="Upload resumes or enter job description",
        job_desc=request.form.get("resumeText", "")
    )
    jd = clean_text(jd)

    resumes = []
    filenames = []

    for file in resume_files:
        if file and allowed_file(file.filename):

            filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
            file.save(filepath)

            text = extract_text(filepath)
            text = clean_text(text)

            resumes.append(text)
            filenames.append(file.filename)

    if not resumes:
        return render_template(
        "app.html",
        message="No valid resumes uploaded",
        job_desc=request.form.get("resumeText", "")
    )

    ranked = match_resumes(jd, resumes)

    job_skills = extract_skills(jd)

    top_results = []

    for index, ai_score in ranked:

        resume_text = resumes[index]
        skills_found = extract_skills(resume_text)

        matched = list(set(job_skills) & set(skills_found))
        missing = list(set(job_skills) - set(skills_found))

        # Skill score
        if len(job_skills) > 0:
            skill_score = (len(matched) / len(job_skills)) * 100
        else:
            skill_score = 0

        # AI score
        ai_score_percent = ai_score * 100

        # Final score (optional)
        final_score = (skill_score * 0.7) + (ai_score_percent * 0.3)

        # Reason
        reason = []
        if missing:
            reason.append("Missing skills: " + ", ".join(missing))
        if len(skills_found) < 3:
            reason.append("Not enough skills in resume")

        top_results.append({
            "name": filenames[index] if index < len(filenames) else "Unknown",
            "skill_score": round(skill_score, 2),
            "ai_score": round(ai_score_percent, 2),
            "final_score": round(final_score, 2),
            "skills": skills_found,
            "missing": missing,
            "reason": reason
        })

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute(
            "INSERT INTO history (filename, skill_score, ai_score) VALUES (?, ?, ?)",
            (filenames[index], skill_score, ai_score_percent)
        )

        conn.commit()
        conn.close()

    latest_results = top_results

    session["results"] = top_results
    session["message"] = "Top Matching Resumes"
    session["job_desc"] = request.form.get("resumeText", "")

    return redirect(url_for("upload"))
@app.route("/history")
def history():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT * FROM history")
    data = c.fetchall()

    conn.close()

    return render_template("history.html", data=data)

@app.route("/visualize")
def visualize():
    return render_template("visualize.html", data=latest_results)


@app.route("/download")
def download():

    file_path = "results.csv"

    with open(file_path, "w", newline="") as file:
        writer = csv.writer(file)

        writer.writerow([
            "Rank",
            "Candidate",
            "Skill Score",
            "AI Score",
            "Skills Found",
            "Missing Skills",
            "Reason"
        ])

        for i, r in enumerate(latest_results, start=1):
            writer.writerow([
                i,
                r["name"],
                r["skill_score"],
                r["ai_score"],
                ", ".join(r["skills"]),
                ", ".join(r["missing"]),
                ", ".join(r["reason"])
            ])

    return send_file(file_path, as_attachment=True)


# ================== RUN ================== 


@app.route("/job/<int:job_id>")
def view_job(job_id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
    job = c.fetchone()

    conn.close()

    return render_template("job_detail.html", job=job)


@app.route("/delete_job/<int:job_id>")
def delete_job(job_id):

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("DELETE FROM jobs WHERE id=?", (job_id,))

    conn.commit()
    conn.close()

    return redirect("/dashboard")

@app.route("/edit_job/<int:job_id>", methods=["GET", "POST"])
def edit_job(job_id):

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if request.method == "POST":

        title = request.form["title"]
        description = request.form["description"]

        c.execute(
            """
            UPDATE jobs
            SET title=?, description=?
            WHERE id=?
            """,
            (title, description, job_id)
        )

        conn.commit()
        conn.close()

        return redirect("/dashboard")

    c.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
    job = c.fetchone()

    conn.close()

    return render_template("edit_job.html", job=job)

@app.route("/chat", methods=["POST"])
def chat():

    user_msg = request.form.get("message", "").lower()

    if "hello" in user_msg or "hi" in user_msg:
        reply = "Hello! I am your Resume Screening Assistant. How can I help you?"

    elif "skill" in user_msg:
        reply = "Skills represent the technologies and competencies identified in the resume and matched with the job description."

    elif "ai score" in user_msg:
        reply = "AI Score is generated using TF-IDF and Cosine Similarity to measure resume relevance."

    elif "final score" in user_msg or "score" in user_msg:
        reply = "The final score is calculated using both AI matching and skill matching scores to rank candidates."

    elif "missing skills" in user_msg or "missing" in user_msg:
        reply = "Missing skills are the skills present in the job description but not found in the uploaded resume."

    elif "best candidate" in user_msg or "top candidate" in user_msg:
        if latest_results:
            reply = f"The top candidate is {latest_results[0]['name']}."
        else:
            reply = "No resumes have been analyzed yet."

    elif "low score" in user_msg:
        reply = "Low score means the resume contains fewer matching skills or less relevant content."

    elif "recommend job" in user_msg:
        reply = "Job roles can be recommended based on the candidate's extracted skills."

    elif "how scoring works" in user_msg:
        reply = "The score is calculated using Skill Match Score and AI-based similarity score."

    elif "what is tf-idf and cosine similarity" in user_msg:
        reply = (
        "TF-IDF converts the job description and resumes into numerical vectors by assigning "
        "weights to important words. Cosine Similarity then compares these vectors to calculate "
        "a matching score. Higher similarity indicates that the resume is more relevant to the job description."
    )

    elif "tf-idf" in user_msg or "tfidf" in user_msg:
        reply = (
        "TF-IDF stands for Term Frequency-Inverse Document Frequency..."
    )

    elif "cosine similarity" in user_msg:
        reply = (
        "Cosine Similarity is a mathematical measure..."
    )
    elif "project" in user_msg:
        reply = "This AI Resume Screening System automates resume analysis and candidate ranking using NLP techniques."

    else:
        reply = "Sorry, Please try something else."


    from flask import jsonify
    return jsonify({"reply": reply})

if __name__ == "__main__":

    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    init_db()
    app.run(debug=True)