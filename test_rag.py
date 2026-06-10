def get_answer(question):

    if "register" in question.lower():
        return "Use POST /auth/register endpoint"

    if "login" in question.lower():
        return "Use POST /auth/login endpoint"

    return "I don't know"