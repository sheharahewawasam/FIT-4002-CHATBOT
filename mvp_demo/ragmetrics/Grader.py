from rag_api import views
import json
import ollama
import re

#Testing pipeline for the RAG chatbot, for this we are using the sample, SUMMERS FAMILY SUPER FUND (deed.pdf in the repo) as the source of truth
#REMINDER THAT IT RELIES ON A COPY AND PASTE OF THE RAG LOGIC FROM THE VIEWS.PY FILE SINCE THE LOGIC IS COUPLED, SO UPDATES TO THE RAG LOGIC SHOULD BE RECOPY PASTED BEFORE TESTING AGANE

#Strip Qwen3 <think>...</think> tokens that sometimes leak into output
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
def strip_think_tags(text: str) -> str:
    return _THINK_RE.sub("", text).strip()

def get_chat_response(system_prompt, user_query):
    response = ollama.chat(model="qwen3",messages=[{"role": "system", "content": system_prompt},{"role": "user", "content": user_query}],stream=False ,options={"temperature": 0.0,"num_ctx": 8192},format="json")
    return strip_think_tags(response["message"]["content"])

def printRes(question:str,answer:str,grade:str,reasoning:str):
    print(f"Question is {question}")
    print("------------------------------------------------------")
    print(f"Answer Given is {answer}")
    print("--------------------------------------------------------")
    print(f"Grade Given is {grade}")
    print("--------------------------------------------------------")
    print(f"Reasoning Given is {reasoning}")
    print("\n=====================================================\n")
    
    

#Correctness
def correctness(question:str, sample:str):
    prompt = """
    You are a teacher grading a quiz. You will be given a QUESTION, the GROUND TRUTH (correct) ANSWER, and the STUDENT ANSWER. Here is the grade criteria to follow:
    (1) Grade the student answers based ONLY on their factual accuracy relative to the ground truth answer. 
    (2) Ensure that the student answer does not contain any conflicting statements.
    (3) It is OK if the student answer contains more information than the ground truth answer, as long as it is factually accurate relative to the  ground truth answer.

    Correctness:
    A correctness value of 10 means that the student's answer meets all of the criteria.
    A correctness value of 1 means that the student's answer does not meet any criteria at all.

    Explain your reasoning in a step-by-step manner to ensure your reasoning and conclusion are correct. Avoid simply stating the correct answer at the outset.
    Return as valid json with the first field being your reasoning, titled reasoning, and the second field being a number rating on how good the student did, titled correct.
    so something like { "reasoning" : (Actual reasoning here), "correct" : (1.0-10.0)}
    """
    returnedAnswer = views.rag_logic(question)
    userPrompt = f"""
    QUESTIONS : {question}
    GROUND TRUTH : {sample}
    STUDENT ANSWERS : {returnedAnswer}
    """
    grade = json.loads(get_chat_response(prompt,userPrompt))
    printRes(question,returnedAnswer,grade["correct"],grade["reasoning"])
    return grade["correct"]

#Relevance
def Relevance(question:str):
    prompt = """
                You are a teacher grading a quiz. You will be given a QUESTION and a STUDENT ANSWER. Here is the grade criteria to follow:
                (1) Ensure the STUDENT ANSWER is concise and relevant to the QUESTION
                (2) Ensure the STUDENT ANSWER helps to answer the QUESTION

                Relevance:
                A relevance value of 1 means that the student's answer is irrelevant and unhelpful,
                A relevance value of 10 means that the student's answer is fully relevant and directly answers the question with no extraneous content

                Explain your reasoning in a step-by-step manner to ensure your reasoning and conclusion are correct. Avoid simply stating the correct answer at the outset.
                Return as valid json with the first field being your reasoning, titled reasoning, and the second field being a number rating on how good the student did, titled relevant.
                so something like { "reasoning" : (Actual reasoning here), "relevant" : (1.0-10.0)}
            """
                    
    returnedAnswer = views.rag_logic(question)
    userPrompt = f"""
    QUESTIONS : {question}
    STUDENT ANSWERS : {returnedAnswer}
    """
    grade = json.loads(get_chat_response(prompt,userPrompt))
    printRes(question,returnedAnswer,grade["relevant"],grade["reasoning"])
    return grade["relevant"]
    

#Groundedness
def Groundedness(question:str):
    prompt = """
    You are a teacher grading a quiz. You will be given FACTS and a STUDENT ANSWER. Here is the grade criteria to follow:
    (1) Ensure the STUDENT ANSWER is grounded in the FACTS. \
    (2) Ensure the STUDENT ANSWER does not contain "hallucinated" information outside the scope of the FACTS.

    Grounded:
    A grounded value of 10 means that the student's answer meets all of the criteria.
    A grounded value of 1 means that the student's answer does not meet all of the criteria.

    Explain your reasoning in a step-by-step manner to ensure your reasoning and conclusion are correct. Avoid simply stating the correct answer at the outset.
    Return as valid json with the first field being your reasoning, titled reasoning, and the second field being a number rating on how good the student did, titled grounded.
    so something like { "reasoning" : (Actual reasoning here), "grounded" : (1.0-10.0)}
    """
                    
    returnedAnswer = views.rag_logic(question)
    userPrompt = f"""
    QUESTIONS : {question}
    STUDENT ANSWERS : {returnedAnswer}
    """
    grade = json.loads(get_chat_response(prompt,userPrompt))
    printRes(question,returnedAnswer,grade["grounded"],grade["reasoning"])
    return grade["grounded"]
    
#Retrieval relevance
def retRelevance(question:str):
    prompt = """
    You are a teacher grading a quiz. You will be given a QUESTION and a set of FACTS provided by the student. Here is the grade criteria to follow:
    (1) You goal is to identify FACTS that are completely unrelated to the QUESTION
    (2) If the facts contain ANY keywords or semantic meaning related to the question, consider them relevant
    (3) It is OK if the facts have SOME information that is unrelated to the question as long as (2) is met

    Relevance:
    A relevance value of 10 means that the FACTS contain ANY keywords or semantic meaning related to the QUESTION and are therefore relevant.
    A relevance value of 1 means that the FACTS are completely unrelated to the QUESTION.

    Explain your reasoning in a step-by-step manner to ensure your reasoning and conclusion are correct. Avoid simply stating the correct answer at the outset.
    Return as valid json with the first field being your reasoning, titled reasoning, and the second field being a number rating on how good the student did, titled retrel.
    so something like { "reasoning" : (Actual reasoning here), "retrel" : (1.0-10.0)}

    """
                    
    returnedAnswer = views.rag_logic(question)
    userPrompt = f"""
    QUESTIONS : {question}
    STUDENT ANSWERS : {returnedAnswer}
    """
    grade = json.loads(get_chat_response(prompt,userPrompt))
    printRes(question,returnedAnswer,grade["retrel"],grade["reasoning"])
    return grade["retrel"]


def correctnessBatch():
    results = []
    questions = [
        "What is the current deed date for this fund, and has it been updated to reflect all legislative changes since that date?",
        "Does the deed specifically allow the commencement of account-based pensions, and are the payment and commutation rules consistent with current law?",
        "Does the deed support binding death benefit nominations (BDBNs), and are there any restrictions on who can be nominated as a beneficiary?",
        "Does the deed allow a corporate trustee to act, and has the fund properly transitioned from individual to corporate trustee if that change was made?",
        "Does the deed permit all contribution types being made to this fund - concessional, non-concessional, spouse, downsizer, and small business CGT contributions?",
        "Are there any clauses in this deed that conflict with the fund's current pension contribution, or investment strategy arrangements?",
        "Does the binding death benefit nomination on file match what the deed actually permits — is it valid under the deed's rules?"
    ]
    
    samples = [
        "Deed dated 21 January 2012. No amendments are evidenced in the document, so whether it reflects legislative changes since 2012 cannot be confirmed from the deed alone — this requires checking for a variation/consolidation schedule outside this document.",
        "Yes, the deed supports pensions generically (clause 17) and defers to ATO Guidelines for detailed rules, but does not itself contain specific account-based pension mechanics (minimum drawdown, commutation procedure). Consistency with current law cannot be verified from deed text alone — it relies on external ATO Guidelines by reference.",
        "The deed records a death benefit nomination for each member (spouse-to-spouse, 100%), but the document does not use the term 'binding' nor specify BDBN validity requirements (e.g., witness requirements, expiry/renewal period). No explicit beneficiary-eligibility restrictions are stated in the deed itself.",
        "The deed allows for a corporate trustee (clause 10a), but as executed, the Fund uses individual trustees (John and Sandra Summers) — there is no evidence of a transition to corporate trustee in this document.",
        "Deed explicitly permits employer, member (concessional/non-concessional), and government co-contributions, plus rollovers. Spouse contributions, downsizer contributions, and small business CGT contributions are not specifically named — the deed's general contribution clause may or may not extend to them, but this is not explicit in the text.",
        "No explicit conflicting clauses are identifiable from the deed text alone; the deed is drafted to defer to external ATO Guidelines/SISA rather than fix specific rules, so a genuine conflict check requires comparing it against the fund's actual current investment strategy document and contribution/pension activity — not just the deed.",
        "The nominations in the deed match clause 24(a) by definition, since they're recorded directly in the deed. Whether a separate BDBN form 'on file' matches these terms and is independently valid cannot be determined from the deed alone — the deed does not set out formal execution/validity requirements for BDBNs, so this needs the actual BDBN form for comparison."
    ]
    
    for i in range(len(questions)):
        results.append(correctness(questions[i],samples[i]))
    return results

def batchEval():
    questions = [
        "What is the current deed date for this fund, and has it been updated to reflect all legislative changes since that date?",
        "Does the deed specifically allow the commencement of account-based pensions, and are the payment and commutation rules consistent with current law?",
        "Does the deed support binding death benefit nominations (BDBNs), and are there any restrictions on who can be nominated as a beneficiary?",
        "Does the deed allow a corporate trustee to act, and has the fund properly transitioned from individual to corporate trustee if that change was made?",
        "Does the deed permit all contribution types being made to this fund - concessional, non-concessional, spouse, downsizer, and small business CGT contributions?",
        "Are there any clauses in this deed that conflict with the fund's current pension contribution, or investment strategy arrangements?",
        "Does the binding death benefit nomination on file match what the deed actually permits — is it valid under the deed's rules?"
    ]
    
    print("CORRECTNESS \n ======================================")
    correctnessrez = correctnessBatch()
    avgCorrect = sum(correctnessrez)/len(correctnessrez)
    print(f"AVERAGE CORRECTNESS IS {avgCorrect}")
    
    print("RELEVANCE \n ======================================")
    results = []
    for i in questions:
        results.append(Relevance(i))
    avgGrade = sum(results)/len(results)
    print(f"AVERAGE RELEVANCE IS {avgGrade}")
    
    print("GROUNDEDNESS\n ======================================")
    results = []
    for i in questions:
        results.append(Groundedness(i))
    avgGrade = sum(results)/len(results)
    print(f"AVERAGE GROUNDEDNESS IS {avgGrade}")
    
    print("RETRIEVAL RELEVANCE\n ======================================")
    results = []
    for i in questions:
        results.append(retRelevance(i))
    avgGrade = sum(results)/len(results)
    print(f"AVERAGE RETRIEVAL RELEVANCE IS {avgGrade}")

