import os
import re
import json
from bson import ObjectId
from pymongo import MongoClient
from dotenv import dotenv_values
from ollama import Client as OllamaClient

# Load environment
config = dotenv_values(".env")
config = {'MONGO_URI': 'mongodb+srv://saffimuhammadhashir:bg5YjLngCwTKEsNp@cluster0.hu2z5r0.mongodb.net/?retryWrites=true&w=majority&tls=true', 'DB_NAME': 'Hiring_system_Testing_DataBase'}

mongo_uri = "mongodb://localhost:27017/"
db_name = "Resumes"
postID = '68599a8b423958c44a738225'

# Initialize Ollama client
llm_client = OllamaClient()
MAX_APPLICANTS = 50

# Fetch job description from remote DB
def fetch_job_post(postID):
    remote_client = MongoClient(config["MONGO_URI"])
    db = remote_client[config["DB_NAME"]]
    if isinstance(postID, str):
        try:
            postID = ObjectId(postID)
        except Exception as e:
            print(f"Invalid postID: {e}")
            return None
    return db['posts'].find_one({'_id': postID})

# Rank applicants using LLaMA2 prompt
def get_ranked_list(job_post: dict, applicant_list: list) -> list:
    prompt = f"""
    You are an expert hiring manager tasked with evaluating job applicants based on a provided job post and applicant data. Below are multiple example evaluations to illustrate the expected format, structure, and depth of analysis. Use these as a guide to evaluate each applicant consistently, ensuring your response includes a score, justification, key strengths, development areas, and a hiring recommendation.

    Example Evaluations:

    [
    {{
        "applicantID": "app_001",
        "applicantName": "Sarah Chen",
        "Score": 8.7,
        "Justification/Recommendation Note": "Exceptional full-stack developer with 4 years experience in React and Node.js. Led successful migration to microservices architecture. Strong educational background in CS from top-tier university. Minor gap in DevOps practices but demonstrates rapid learning ability.",
        "Key Strengths": ["Full-stack expertise", "Architecture design", "Leadership experience", "Strong academics"],
        "Development Areas": ["DevOps practices", "Container orchestration"],
        "Hiring Recommendation": "Highly Recommend"
    }},
    {{
        "applicantID": "app_002",
        "applicantName": "Mike Johnson",
        "Score": 6.2,
        "Justification/Recommendation Note": "Solid foundation in required technologies with 2 years junior developer experience. Good project portfolio showing competence in core skills. Limited exposure to senior-level responsibilities and some gaps in advanced frameworks. Shows potential for growth with proper mentorship.",
        "Key Strengths": ["Core programming skills", "Project completion", "Team collaboration"],
        "Development Areas": ["Advanced frameworks", "System architecture", "Leadership skills"],
        "Hiring Recommendation": "Consider"
    }},
    {{
        "applicantID": "app_003",
        "applicantName": "Aisha Malik",
        "Score": 4.9,
        "Justification/Recommendation Note": "Limited relevant experience for the role. Background in unrelated technologies and no strong alignment with required tech stack. Demonstrates enthusiasm and willingness to learn, but not currently ready for the position.",
        "Key Strengths": ["Motivation", "Communication skills"],
        "Development Areas": ["Tech stack alignment", "Project experience", "Problem-solving depth"],
        "Hiring Recommendation": "Do Not Recommend"
    }}
    ]

    Instructions:

    - Review the provided job post to understand the role's requirements, including required skills, experience, and qualifications.
    - Evaluate **each applicant** in the provided list against the job post requirements.
    - For each applicant, return an evaluation as part of a **JSON array**, formatted like the examples above. Each entry must include:
    - `applicantID`: The applicant's unique ID.
    - `applicantName`: The applicant's name.
    - `Score`: A numerical score (0–10) reflecting their fit for the role.
    - `Justification/Recommendation Note`: A concise narrative explaining the score and fit.
    - `Key Strengths`: A list of 3–5 role-relevant strengths.
    - `Development Areas`: A list of 2–4 areas needing improvement.
    - `Hiring Recommendation`: One of: "Highly Recommend", "Recommend", "Consider", or "Do Not Recommend".

    Be objective, concise, and consistent. If the job post or applicant list is missing or incomplete, respond with: "Please provide the job post and applicant list to proceed with the evaluation."

    Input:

    Job Post:
    {json.dumps(job_post, indent=2)}

    Applicants:
    {json.dumps(applicant_list, indent=2)}

    Begin Evaluation:
    """

    print("📝 Prompt sent to LLM:", prompt)
    try:
        response = llm_client.generate(model="gemma3n:e4b", prompt=prompt)
        raw_output = response.response
        def clean_llm_output(raw_output):
            # Remove code block markers
            cleaned = re.sub(r"```(?:json)?\n?|```", "", raw_output).strip()
            # Try to extract a JSON array first
            start = cleaned.find('[')
            end = cleaned.rfind(']')
            if start != -1 and end != -1 and end > start:
                return cleaned[start:end+1]
            # If no array, try to extract a JSON object
            start = cleaned.find('{')
            end = cleaned.rfind('}')
            if start != -1 and end != -1 and end > start:
                return cleaned[start:end+1]
            # Fallback: return cleaned string
            return cleaned
        
        cleaned_output = clean_llm_output(raw_output)
        print("🔍 Raw LLM output:", raw_output)
        print("\n\n📝 Parsed JSON:", cleaned_output)
        ranked_list = json.loads(cleaned_output)
        return ranked_list
    except Exception as e:
        print(f"❌ LLM failed: {e}")
        return []
def store_ranked_applicants(post_id, ranked_list):
    try:
        client = MongoClient(config["MONGO_URI"])
        db = client[config["DB_NAME"]]
        ranked_collection = db["Ranked_Applicants"]

        formatted = {
            "PostId": str(post_id),
            "List": [
                {
                    "ApplicantId": item.get("applicantID"),
                    "Score": item.get("Score"),
                    "Rank": idx + 1,
                    "Note": item.get("Justification/Recommendation Note", "")
                }
                for idx, item in enumerate(ranked_list)
            ]
        }
        ranked_collection.insert_one(formatted)
        print(f"✅ Stored ranked applicants for post {post_id}")
    except Exception as e:
        print(f"❌ Error storing ranked applicants: {e}")
        raise

def get_top_candidates_for_post(post_id):
    try:
        client = MongoClient(config["MONGO_URI"])
        db = client[config["DB_NAME"]]
        processed_collection = db["Resume_Info"]

        applicants = list(processed_collection.find({"user.postId": ObjectId(post_id)}))
        minimal_applicants = []
        for a in applicants:
            data = a.get("user", {})
            minimal_applicants.append({
                "applicantID": str(data.get("_id")),
                "applicantName": data.get("name", ""),
                "skills": a.get("skills", []),
                "matched_skills": a.get("skill_matched", []),
                "about": a.get("about", ""),
                "education": a.get("resume_info", {}).get("education", []),
                "experience": a.get("resume_info", {}).get("experience", []),
                "projects": a.get("resume_info", {}).get("projects", []),
            })

        job_post = db['posts'].find_one({'_id': ObjectId(post_id)})
        ranked_list = get_ranked_list(job_post, minimal_applicants)
        top_10 = ranked_list[:10] if len(ranked_list) >= 10 else ranked_list

        store_ranked_applicants(post_id, top_10)
        return top_10
    except Exception as e:
        print(f"❌ Error getting top candidates: {e}")
        return []