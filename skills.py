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
    text = text.lower()      # Convert once

    for skill in skills:
        if skill.lower() in text:
            found.append(skill)

    return found
