from flask import Flask, request, render_template, send_file
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

    c.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        skill_score REAL,
        ai_score REAL
    )
    """)

    conn.commit()
    conn.close()
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}

app = Flask(__name__)
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

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/analyzer")
def analyzer():
    return render_template("app.html")


@app.route("/upload", methods=["POST"])
def upload():

    global latest_results

    jd = request.form.get("resumeText", "")
    resume_files = request.files.getlist("resumeFile")

    if not jd and not resume_files:
        return render_template("app.html", message="Upload resumes or enter job description")

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
        return render_template("app.html", message="No valid resumes uploaded")

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

    return render_template(
        "app.html",
        results=top_results,
        message="Top Matching Resumes"
    )
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


@app.route("/chat", methods=["POST"])
def chat():
    user_msg = request.form.get("message", "").lower()

    if "best candidate" in user_msg:
        reply = "The top ranked candidate has highest skill match and AI score."

    elif "missing skills" in user_msg:
        reply = "Missing skills are calculated based on job description vs resume."

    elif "low score" in user_msg:
        reply = "Low score means fewer matching skills or less relevant content."

    elif "recommend job" in user_msg:
        reply = "Job role is suggested based on candidate skills."

    elif "how scoring works" in user_msg:
        reply = "Score is calculated using skill match and AI-based similarity."

    elif "top candidate" in user_msg:
        reply = latest_results[0]["name"]

    else:
        reply = "Ask about candidate ranking, missing skills, or scoring."

    return {"reply": reply}  


if __name__ == "__main__":

    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    init_db()
    app.run(debug=True)