from rag_api import views
import json
import ollama
import re

#Testing pipeline for the RAG chatbot, for this we are using the sample, SUMMERS FAMILY SUPER FUND (deed.pdf in the repo) as the source of truth

#Strip Qwen3 <think>...</think> tokens that sometimes leak into output
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
def strip_think_tags(text: str) -> str:
    return _THINK_RE.sub("", text).strip()

def get_chat_response(system_prompt, user_query):
    response = ollama.chat(model="qwen3",messages=[{"role": "system", "content": system_prompt},{"role": "user", "content": user_query}],stream=False ,options={"temperature": 0.0,"num_ctx": 8192},format="json")
    return strip_think_tags(response["message"]["content"])

#Correctness
def correctness():
    prompt = """
    You are a teacher grading a quiz. You will be given a QUESTION, the GROUND TRUTH (correct) ANSWER, and the STUDENT ANSWER. Here is the grade criteria to follow:
    (1) Grade the student answers based ONLY on their factual accuracy relative to the ground truth answer. (2) Ensure that the student answer does not contain any conflicting statements.
    (3) It is OK if the student answer contains more information than the ground truth answer, as long as it is factually accurate relative to the  ground truth answer.

    Correctness:
    A correctness value of True means that the student's answer meets all of the criteria.
    A correctness value of False means that the student's answer does not meet all of the criteria.

    Explain your reasoning in a step-by-step manner to ensure your reasoning and conclusion are correct. Avoid simply stating the correct answer at the outset.
    Return as valid json with the first field being your reasoning, titled reasoning, and the second field being a number rating on how good the student did, titled correct.
    so something like { "reasoning" : (Actual reasoning here), "correct" : (1.0-10.0)}
    """
    
    questions = """
                # 1. What is the current deed date for this fund, and has it been updated to reflect all legislative changes since that date?
                # 2. Does the deed specifically allow the commencement of account-based pensions, and are the payment and commutation rules consistent with current law?
                # 3. Does the deed support binding death benefit nominations (BDBNs), and are there any restrictions on who can be nominated as a beneficiary?
                # 4. Does the deed allow a corporate trustee to act, and has the fund properly transitioned from individual to corporate trustee if that change was made?
                # 5. Does the deed permit all contribution types being made to this fund - concessional, non-concessional, spouse, downsizer, and small business CGT contributions?
                # 6. Are there any clauses in this deed that conflict with the fund's current pension contribution, or investment strategy arrangements?
                # 7. Does the binding death benefit nomination on file match what the deed actually permits — is it valid under the deed's rules?
                """
                
    sampleAnswers = """
                    # 1. Deed dated 21 January 2012. No amendments are evidenced in the document, so whether it reflects legislative changes since 2012 cannot be confirmed from the deed alone — this requires checking for a variation/consolidation schedule outside this document.
                    # 2. Yes, the deed supports pensions generically (clause 17) and defers to ATO Guidelines for detailed rules, but does not itself contain specific account-based pension mechanics (minimum drawdown, commutation procedure). Consistency with current law cannot be verified from deed text alone — it relies on external ATO Guidelines by reference.
                    # 3. The deed records a death benefit nomination for each member (spouse-to-spouse, 100%), but the document does not use the term "binding" nor specify BDBN validity requirements (e.g., witness requirements, expiry/renewal period). No explicit beneficiary-eligibility restrictions are stated in the deed itself.
                    # 4. The deed allows for a corporate trustee (clause 10a), but as executed, the Fund uses individual trustees (John and Sandra Summers) — there is no evidence of a transition to corporate trustee in this document.
                    # 5. Deed explicitly permits employer, member (concessional/non-concessional), and government co-contributions, plus rollovers. Spouse contributions, downsizer contributions, and small business CGT contributions are not specifically named — the deed's general contribution clause may or may not extend to them, but this is not explicit in the text.
                    # 6. No explicit conflicting clauses are identifiable from the deed text alone; the deed is drafted to defer to external ATO Guidelines/SISA rather than fix specific rules, so a genuine conflict check requires comparing it against the fund's actual current investment strategy document and contribution/pension activity — not just the deed.
                    # 7. The nominations in the deed match clause 24(a) by definition, since they're recorded directly in the deed. Whether a separate BDBN form "on file" matches these terms and is independently valid cannot be determined from the deed alone — the deed does not set out formal execution/validity requirements for BDBNs, so this needs the actual BDBN form for comparison.
                    """
                    
    returnedAnswers = views.rag_logic(questions)
    userPrompt = f"""
    QUESTIONS : {questions}
    GROUND TRUTH : {sampleAnswers}
    STUDENT ANSWERS : {returnedAnswers}
    """
    grade = json.loads(get_chat_response(prompt,userPrompt))
    print(grade["reasoning"])
    return grade["correct"]
    

#Correctness
def correctness():
    #Relevance
    prompt = """
                You are a teacher grading a quiz. You will be given a QUESTION and a STUDENT ANSWER. Here is the grade criteria to follow:
                (1) Ensure the STUDENT ANSWER is concise and relevant to the QUESTION
                (2) Ensure the STUDENT ANSWER helps to answer the QUESTION

                Relevance:
                A relevance value of True means that the student's answer meets all of the criteria.
                A relevance value of False means that the student's answer does not meet all of the criteria.

                Explain your reasoning in a step-by-step manner to ensure your reasoning and conclusion are correct. Avoid simply stating the correct answer at the outset.
                Return as valid json with the first field being your reasoning, titled reasoning, and the second field being a number rating on how good the student did, titled relevant.
                    so something like { "reasoning" : (Actual reasoning here), "relevant" : (1.0-10.0)}
            """
    
    questions = """
                # 1. What is the current deed date for this fund, and has it been updated to reflect all legislative changes since that date?
                # 2. Does the deed specifically allow the commencement of account-based pensions, and are the payment and commutation rules consistent with current law?
                # 3. Does the deed support binding death benefit nominations (BDBNs), and are there any restrictions on who can be nominated as a beneficiary?
                # 4. Does the deed allow a corporate trustee to act, and has the fund properly transitioned from individual to corporate trustee if that change was made?
                # 5. Does the deed permit all contribution types being made to this fund - concessional, non-concessional, spouse, downsizer, and small business CGT contributions?
                # 6. Are there any clauses in this deed that conflict with the fund's current pension contribution, or investment strategy arrangements?
                # 7. Does the binding death benefit nomination on file match what the deed actually permits — is it valid under the deed's rules?
                """
                    
    returnedAnswers = views.rag_logic(questions)
    userPrompt = f"""
    QUESTIONS : {questions}
    STUDENT ANSWERS : {returnedAnswers}
    """
    grade = json.loads(get_chat_response(prompt,userPrompt))
    print(grade["reasoning"])
    return grade["relevant"]
    


        
        
#Groundedness
prompt = """


"""
#Retrieval relevance
prompt = """


"""
#Correctness
prompt = """


"""
