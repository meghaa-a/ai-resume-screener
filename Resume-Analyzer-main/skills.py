skills = [
    "python",
    "sql",
    "machine learning",
    "artificial intelligence",
    "ai",
    "ml",
    "data analysis",
    "nlp",
    "deep learning",
    "pandas",
    "numpy"
]

def extract_skills(text):

    found = []

    for skill in skills:
        if skill in text.lower():
            found.append(skill)

    return found
