from fastapi import FastAPI, Request
from dotenv import dotenv_values
from pymongo import MongoClient
from bson.objectid import ObjectId
from Resume import Resume_Reader
from Ranking_System import model
import threading
from concurrent.futures import ThreadPoolExecutor
import uvicorn
import requests
import time
import asyncio
from datetime import datetime

GITHUB_SCRAPER_URL = "http://ec2-16-170-253-54.eu-north-1.compute.amazonaws.com:8000/github/scrape"
app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Dr. Faisal API is live!"}

MAX_WORKERS = 10
POLLING_INTERVAL = 5  # seconds between database polls

# Config
import os
config = dotenv_values(os.path.join("src", ".env"))

mongo_uri = config.get("MONGO_URI")
db_name = config.get("DB_NAME")

# Thread-safe dict
applicants = {}
applicants_lock = threading.Lock()

# Global flag to control the listener
listener_running = False
listener_thread = None

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
    client.close()
    return post

# Update application status
def update_application_status(db, post_id, user_id, status):
    db['applications'].update_many(
        {"postId": ObjectId(post_id), "userId": user_id},
        {"$set": {"status": status}}
    )

# Update ranking request status
def update_ranking_request_status(post_id, status, result=None):
    client = startup_db_client()
    db = client[db_name]
    update_data = {
        "status": status,
        "processed_at": datetime.utcnow()
    }
    if result:
        update_data["result"] = result
    
    db['ranking_request'].update_one(
        {"postId": post_id},
        {"$set": update_data}
    )
    client.close()

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
    client.close()
    return {"applications": applications, "users": users, "registrations": registrations}

# Process single applicant
def process_single_user(args):
    user, apps, reg_info, post_id = args
    client = startup_db_client()
    db = client[db_name]

    # Set status to Under Review
    update_application_status(db, post_id, user['_id'], "Under Review")
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
        resume_info_collection = db["Resume_Info"]
        resume_info_collection.insert_one(applicant_record)
        print(f"📝 Stored applicant {user['_id']} data into Resume_Info")
        update_application_status(db, post_id, user['_id'], "Done")
    except Exception as e:
        print(f"❌ Failed to store Resume_Info for {user['_id']}: {e}")

    client.close()
    print(f"🏁 Finished processing {user['_id']}")

# Process a ranking request
def process_ranking_request(request_doc):
    try:
        post_id = request_doc.get("postId")
        print(f"🚀 Processing ranking request for post ID: {post_id}")
        
        # Update status to processing
        update_ranking_request_status(post_id, "processing")
        
        job_post = fetch_job_post(post_id)
        if not job_post:
            print(f"❌ Job post not found for ID: {post_id}")
            update_ranking_request_status(post_id, "failed", {"error": "Job post not found"})
            return

        info = fetch_user_data(post_id)
        users = info['users']
        apps = info['applications']
        regs = info['registrations']

        if not users or not regs:
            print("⚠️ No applicants or registration data found.")
            update_ranking_request_status(post_id, "completed", {"message": "No applicants found"})
            return

        print("🚦 Starting applicant processing...")
        
        # Clear previous applicants data for this post
        with applicants_lock:
            applicants.clear()
        
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(users))) as executor:
            executor.map(process_single_user, [(u, apps, regs, post_id) for u in users])

        print("✅ All applicants processed.")

        minimal_applicants = []
        with applicants_lock:
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

        try:
            model.store_ranked_applicants(post_id, top_10)
            print(f"✅ Stored ranked applicants for post {post_id}")
            
            # Update request status to completed
            result = {
                "applicants_processed": len(applicants),
                "ranked_applicants": top_10,
                "job_post_title": job_post.get("title", ""),
                "ranking_completed_at": datetime.utcnow().isoformat()
            }
            update_ranking_request_status(post_id, "completed", result)
            
        except Exception as e:
            print(f"❌ Failed to store ranked applicants: {e}")
            update_ranking_request_status(post_id, "failed", {"error": str(e)})

    except Exception as e:
        print(f"❌ Error processing ranking request: {e}")
        if 'post_id' in locals():
            update_ranking_request_status(post_id, "failed", {"error": str(e)})

# Continuous listener function
def ranking_request_listener():
    print("🎧 Starting ranking request listener...")
    global listener_running
    listener_running = True
    
    while listener_running:
        try:
            client = startup_db_client()
            db = client[db_name]
            
            # Find pending ranking requests
            pending_requests = list(db['ranking_request'].find({
                "status": {"$in": ["pending", None]}
            }).sort("created_at", 1))  # Process oldest first
            
            if pending_requests:
                print(f"📋 Found {len(pending_requests)} pending ranking requests")
                
                for request_doc in pending_requests:
                    if not listener_running:  # Check if we should stop
                        break
                    
                    print(f"📝 Processing request: {request_doc.get('_id')}")
                    process_ranking_request(request_doc)
                    
            else:
                print("💤 No pending requests found, waiting...")
            
            client.close()
            time.sleep(POLLING_INTERVAL)
            
        except Exception as e:
            print(f"❌ Error in ranking request listener: {e}")
            time.sleep(POLLING_INTERVAL)  # Wait before retrying
    
    print("🛑 Ranking request listener stopped")

# API endpoints for manual control (optional)
@app.post("/start_listener")
async def start_listener():
    global listener_thread, listener_running
    
    if listener_running:
        return {"message": "Listener is already running"}
    
    listener_thread = threading.Thread(target=ranking_request_listener, daemon=True)
    listener_thread.start()
    return {"message": "Ranking request listener started"}

@app.post("/stop_listener")
async def stop_listener():
    global listener_running
    
    if not listener_running:
        return {"message": "Listener is not running"}
    
    listener_running = False
    return {"message": "Ranking request listener stopping..."}

@app.get("/listener_status")
async def get_listener_status():
    return {
        "listener_running": listener_running,
        "polling_interval": POLLING_INTERVAL
    }

# Legacy endpoint (keeping for backward compatibility)
@app.post("/process_post")
async def process_post(request: Request):
    try:
        data = await request.json()
        post_id = data.get("postId")

        if not post_id:
            return {"error": "postId is required"}, 400

        # Instead of processing directly, add to ranking_request collection
        client = startup_db_client()
        db = client[db_name]
        
        # Check if request already exists
        existing_request = db['ranking_request'].find_one({"postId": post_id})
        if existing_request:
            return {"message": "Ranking request already exists for this post", "status": existing_request.get("status", "pending")}
        
        # Create new ranking request
        ranking_request = {
            "postId": post_id,
            "status": "pending",
            "created_at": datetime.utcnow(),
            "requested_via": "api"
        }
        
        result = db['ranking_request'].insert_one(ranking_request)
        client.close()
        
        return {
            "message": "Ranking request created successfully",
            "request_id": str(result.inserted_id),
            "postId": post_id,
            "status": "pending"
        }
        
    except Exception as e:
        print(f"❌ Error creating ranking request: {e}")
        return {"error": "Internal server error"}, 500

@app.on_event("startup")
async def startup_event():
    # Start the listener automatically when the app starts
    global listener_thread
    listener_thread = threading.Thread(target=ranking_request_listener, daemon=True)
    listener_thread.start()
    print("🚀 Ranking request listener started automatically")

if __name__ == "__main__":
    print("🚀 Starting local API server on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)