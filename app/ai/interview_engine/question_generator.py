from typing import List


class QuestionGenerator:
    @staticmethod
    def generate_questions(skills: List[str]) -> List[str]:
        questions = []
        for skill in skills:
            questions.append(f"Describe a project where you used {skill}.")
            questions.append(f"What challenges did you face while working with {skill}?")
        return questions
