def recommend_job(skills):

    if "machine learning" in skills or "nlp" in skills:
        return "Data Scientist"

    elif "ml" in skills or "nlp" in skills:
        return "Data Scientist"
    elif "python" in skills and "sql" in skills:
        return "Data Analyst"

    elif "javascript" in skills or "react" in skills:
        return "Frontend Developer"

    elif "java" in skills or "spring" in skills:
        return "Backend Developer"

    elif "cloud" in skills or "aws" in skills:
        return "Cloud Engineer"

    else:
        return "General Software Role"