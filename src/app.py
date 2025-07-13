from fastapi import FastAPI, Request
from dotenv import dotenv_values
from pymongo import MongoClient
from bson.objectid import ObjectId
from Resume import Resume_Reader
from Ranking_System import model
import threading
from concurrent.futures import ThreadPoolExecutor
import uvicorn      #type: ignore
import requests  # Add this to your imports

GITHUB_SCRAPER_URL = "http://ec2-16-170-253-54.eu-north-1.compute.amazonaws.com:8000/github/scrape"
app = FastAPI()
MAX_WORKERS = 10

# Config
import os
config = dotenv_values(os.path.join("src", ".env"))

mongo_uri = config.get("MONGO_URI")
db_name = config.get("DB_NAME")

# Thread-safe dict
applicants = {}
applicants_lock = threading.Lock()

# DB Client
def startup_db_client():
    return MongoClient(mongo_uri)

# Get Job Description
def fetch_job_post(postID):
    print(f"🔍 Fetching job post with ID: {postID}")
    client = startup_db_client()
    db = client[db_name]
    post = db['posts'].find_one({'_id': ObjectId(postID)})
    if post:
        print("✅ Job post found.")
    else:
        print("❌ Job post not found.")
    return post
# Update application status
def update_application_status(db, post_id, user_id, status):
    db['applications'].update_many(
        {"postId": ObjectId(post_id), "userId": user_id},
        {"$set": {"status": status}}
    )

# Get Applications, Users, Registrations
def fetch_user_data(postID):
    print("📦 Fetching applications, users, and registrations from DB...")
    client = startup_db_client()
    db = client[db_name]
    
    applications = list(db['applications'].find({'postId': ObjectId(postID)}))
    print(f"📄 Applications found: {len(applications)}")

    registrations = []
    users = []

    for app in applications:
        uid = app.get("userId")
        reg_id = app.get("registrationId")

        if uid:
            user = db['users'].find_one({'_id': uid, 'type': 'Applicant'})
            if user:
                users.append(user)
            else:
                print(f"⚠️ No user found for userId: {uid}")

        if reg_id:
            reg = db['registrations'].find_one({'_id': reg_id})
            if reg:
                registrations.append(reg)
            else:
                print(f"⚠️ No registration found for ID: {reg_id}")

    print(f"👥 Users found: {len(users)}")
    print(f"📋 Registrations found: {len(registrations)}")
    return {"applications": applications, "users": users, "registrations": registrations}
# Process single applicant
def process_single_user(args):
    user, apps, reg_info = args
    client = startup_db_client()
    db = client[db_name]

    # Set status to Under Review
    update_application_status(db, user.get('postId'), user['_id'], "Under Review")
    print(f"🧑‍💻 Processing applicant: {user.get('name', 'Unknown')} ({user['_id']})")
    
    resume_url, skills, skill_matched = None, None, None
    about_applicant, cover_letter, work_experience = [], None, None
    github_url = None
    github_data = None

    # Extract registration data
    for reg in reg_info:
        if reg.get("owner") == user["_id"]:
            resume_url = reg.get("resume")
            skills = reg.get("skills")
            github_url = reg.get("github")
            about_applicant.extend([
                reg.get("explainYourself"),
                reg.get("passion"),
                reg.get("expectations")
            ])

    # Extract from application
    for app in apps:
        if app.get("userId") == user["_id"]:
            skill_matched = app.get("skillMatches")
            if not resume_url:
                resume_url = app.get("resume")
            cover_letter = app.get("coverLetter")
            work_experience = app.get("workExperience")

    # Resume Parsing
    resume_info = None
    if resume_url:
        print(f"📄 Parsing resume for {user['_id']}")
        try:
            resume_info = Resume_Reader.parseResume(user['_id'], resume_url, model='llama')
            print(f"✅ Resume parsed for {user['_id']}")
        except Exception as e:
            print(f"❌ Resume parsing error for {user['_id']}: {e}")

    # GitHub Scraping
    if github_url:
        print(f"🌐 Scraping GitHub for {user['_id']} - {github_url}")
        try:
            payload = {
                "applicant_id": str(user["_id"]),
                "github_url": github_url
            }
            headers = {"Content-Type": "application/json"}
            response = requests.post(GITHUB_SCRAPER_URL, json=payload, headers=headers, timeout=20)

            if response.ok:
                github_data = response.json()
                print(f"✅ GitHub data fetched for {user['_id']}")
            else:
                print(f"❌ GitHub scrape failed for {user['_id']} with status {response.status_code}: {response.text}")
        except requests.exceptions.Timeout:
            print(f"⏱️ GitHub scraping timed out for {user['_id']}")
        except requests.exceptions.RequestException as e:
            print(f"🚨 GitHub scraping error for {user['_id']}: {e}")

    # Prepare final data
    applicant_record = {
        "user": user,
        "skills": skills,
        "skill_matched": skill_matched,
        "about": [x for x in about_applicant if x],
        "cover_letter": cover_letter,
        "work_experience": work_experience,
        "resume_info": resume_info,
        "github_data": github_data
    }

    # Save in thread-safe dict
    with applicants_lock:
        applicants[user['_id']] = applicant_record

    # Store in MongoDB collection: Resume_Info
    try:
        client = startup_db_client()
        db = client[db_name]
        resume_info_collection = db["Resume_Info"]
        resume_info_collection.insert_one(applicant_record)
        print(f"📝 Stored applicant {user['_id']} data into Resume_Info")
        update_application_status(db, user.get('postId'), user['_id'], "Done")
    except Exception as e:
        print(f"❌ Failed to store Resume_Info for {user['_id']}: {e}")

    print(f"🏁 Finished processing {user['_id']}")

from src.Ranking_System import model
# Endpoint to trigger the process
@app.post("/process_post")
async def process_post(request: Request):
    data = await request.json()
    post_id = data.get("postId")

    print("📨 POST /process_post called")
    if not post_id:
        print("❌ Missing postId in request body")
        return {"error": "postId is required"}

    print(f"📥 Received post ID: {post_id}")
    job_post = fetch_job_post(post_id)
    if not job_post:
        return {"error": "Invalid postId or post not found"}

    info = fetch_user_data(post_id)
    users = info['users']
    apps = info['applications']
    regs = info['registrations']

    if not users or not regs:
        print("⚠️ No applicants or registration data found.")
        return {"message": "No applicants found for this post."}

    print("🚦 Starting applicant processing...")
    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(regs))) as executor:
        executor.map(process_single_user, [(u, apps, regs) for u in users])

    print("✅ All applicants processed.")

    # Get ranked list using model.py logic
    # Prepare minimal applicant list for ranking
    minimal_applicants = []
    for user_id, data in applicants.items():
        user = data.get("user", {})
        minimal_applicants.append({
            "applicantID": str(user.get("_id")),
            "applicantName": user.get("name", ""),
            "skills": data.get("skills", []),
            "matched_skills": data.get("skill_matched", []),
            "about": data.get("about", ""),
            "education": data.get("resume_info", {}).get("education", []),
            "experience": data.get("resume_info", {}).get("experience", []),
            "projects": data.get("resume_info", {}).get("projects", []),
        })

    ranked_list = model.get_ranked_list(job_post, minimal_applicants)
    top_10 = ranked_list[:10] if len(ranked_list) >= 10 else ranked_list

    # Store ranked applicants in DB
    model.store_ranked_applicants(post_id, top_10)

    return {
        "job_post": job_post,
        "applicants_processed": len(applicants),
        "ranked_applicants": top_10
    }


if __name__ == "__main__":
    print("🚀 Starting local API server on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
