from dotenv import dotenv_values
from pymongo import MongoClient
from LinkedIn import LinkedIn_Scraper
from Github import Github_Scraper
from Resume import Resume_Reader
from bson import ObjectId
import os, threading
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty
import time

config = dotenv_values(".env")

MAX_WORKERS = int(config.get("MAX_WORKERS", 10))
SCRAPER_TIMEOUT = int(config.get("SCRAPER_TIMEOUT", 30))
QUEUE_TIMEOUT = int(config.get("QUEUE_TIMEOUT", 5))

linkedin_queue = Queue()
github_queue = Queue()
resume_queue = Queue()

applicants_lock = threading.Lock()
applicants = {}

def startup_db_client():
    try:
        client = MongoClient(config["MONGO_URI"])
        print("Connected to the MongoDB database!")
        return client
    except Exception as e:
        print(f"Database connection failed: {e}")
        raise

def fetch_user_data(postID):
    client = startup_db_client()
    try:
        db = client[config["DB_NAME"]]

        applications = []
        users = []
        registrations = []  

        if isinstance(postID, str):
            try:
                postID = ObjectId(postID)
            except Exception as e:
                print(f"Invalid postID: {e}")
                return None

        for app in db["applications"].find({"postId": postID}):
            applications.append(app)

            # Get user
            user_id = app.get("userId")
            if not user_id:
                print("Skipping app without userId")
                continue

            user = db["users"].find_one({
                "_id": user_id,
                "type": "Applicant"
            })

            if user:
                users.append(user)
            else:
                print(f"No matching applicant for userId: {user_id}")

            reg_id = app.get("registrationId")
            if reg_id:
                registration = db["registrations"].find_one({"_id": reg_id})
                if registration:
                    registrations.append(registration)
                else:
                    print(f"No registration found for ID {reg_id}")

        return {
            "applications": applications,
            "users": users,
            "registrations": registrations
        }
    finally:
        client.close()

def process_single_user(args):
    user, apps, reg_info = args

    resume_url = None
    linkedin_url = None
    github_url = None
    skills = None
    skill_matched = None
    cover_letter = None
    work_experience = None
    about_applicant = []

    for reg_inst in reg_info:
        if user['_id'] == reg_inst['owner']:
            resume_url = reg_inst.get('resume')
            linkedin_url = reg_inst.get('linkedIn')
            github_url = reg_inst.get('github')
            skills = reg_inst.get('skills')
            about_applicant.append(reg_inst.get('explainYourself'))
            about_applicant.append(reg_inst.get('passion'))

    for app in apps:
        if app['userId'] == user['_id']:
            skill_matched = app.get('skillMatches')
            if linkedin_url is None:
                linkedin_url = app.get('linkedIn')
            if resume_url is None:
                resume_url = app.get('resume')

            if app.get('type') == 'intern':
                interests = app.get('interests')
                if interests:
                    about_applicant.append(interests)

            if app.get('type') == 'job':
                cover_letter = app.get('coverLetter')
                work_experience = app.get('workExperience')

    user_id = user['_id']
    
    if linkedin_url:
        linkedin_queue.put({
            'id': user_id, 
            'url': linkedin_url,
            'email': config.get('LINKEDIN_EMAIL'),
            'password': config.get('LINKEDIN_PASSWORD')
        })
    
    if github_url:
        github_queue.put({'id': user_id, 'url': github_url})
    
    if resume_url:
        resume_queue.put({'id': user_id, 'url': resume_url})

    applicant_data = {
        "user": user,
        "skills": skills,
        "skill_matched": skill_matched,
        "about": [item for item in about_applicant if item],  
        "cover_letter": cover_letter,
        "work_experience": work_experience,
        "linkedin_info": None,
        "github_info": None,
        "resume_info": None
    }

    with applicants_lock:
        applicants[user_id] = applicant_data

    print(f"Finished processing user data for {user_id}")
    return user_id

def linkedin_worker():
    while True:
        try:
            task = linkedin_queue.get(timeout=QUEUE_TIMEOUT)
            user_id = task['id']
            
            print(f"[{user_id}] Scraping LinkedIn")
            try:
                result = LinkedIn_Scraper.scrape_linkedin_profile(
                    user_id, task['url'], task['email'], task['password']
                )
                
                with applicants_lock:
                    if user_id in applicants:
                        applicants[user_id]['linkedin_info'] = result
                        print(f"[{user_id}] LinkedIn scraping completed")
                    
            except Exception as e:
                print(f"LinkedIn scraping error for {user_id}: {e}")
            finally:
                linkedin_queue.task_done()
                
        except Empty:
            print("LinkedIn worker: No more tasks, exiting")
            break
        except Exception as e:
            print(f"LinkedIn worker error: {e}")

def github_worker():
    while True:
        try:
            task = github_queue.get(timeout=QUEUE_TIMEOUT)
            user_id = task['id']
            
            print(f"[{user_id}] Scraping GitHub")
            try:
                result = Github_Scraper.scrape_github_profile(user_id, task['url'])
                
                with applicants_lock:
                    if user_id in applicants:
                        applicants[user_id]['github_info'] = result
                        print(f"[{user_id}] GitHub scraping completed")
                        
            except Exception as e:
                print(f"GitHub scraping error for {user_id}: {e}")
            finally:
                github_queue.task_done()
                
        except Empty:
            print("GitHub worker: No more tasks, exiting")
            break
        except Exception as e:
            print(f"GitHub worker error: {e}")

def resume_worker():
    while True:
        try:
            task = resume_queue.get(timeout=QUEUE_TIMEOUT)
            user_id = task['id']
            
            print(f"[{user_id}] Parsing Resume")
            try:
                result = Resume_Reader.parseResume(user_id, task['url'], model='llama')
                
                with applicants_lock:
                    if user_id in applicants:
                        applicants[user_id]['resume_info'] = result
                        print(f"[{user_id}] Resume parsing completed")
                        
            except Exception as e:
                print(f"Resume parsing error for {user_id}: {e}")
            finally:
                resume_queue.task_done()
                
        except Empty:
            print("Resume worker: No more tasks, exiting")
            break
        except Exception as e:
            print(f"Resume worker error: {e}")

def start_scraper_workers():
    workers = []
    
    linkedin_workers = int(config.get("LINKEDIN_WORKERS", 3))
    github_workers = int(config.get("GITHUB_WORKERS", 3))
    resume_workers = int(config.get("RESUME_WORKERS", 3))
    
    for i in range(linkedin_workers):
        worker_thread = threading.Thread(target=linkedin_worker, name=f"LinkedInWorker-{i}")
        worker_thread.daemon = True
        worker_thread.start()
        workers.append(worker_thread)
    
    for i in range(github_workers):
        worker_thread = threading.Thread(target=github_worker, name=f"GitHubWorker-{i}")
        worker_thread.daemon = True
        worker_thread.start()
        workers.append(worker_thread)
    
    for i in range(resume_workers):
        worker_thread = threading.Thread(target=resume_worker, name=f"ResumeWorker-{i}")
        worker_thread.daemon = True
        worker_thread.start()
        workers.append(worker_thread)
    
    return workers

def wait_for_scrapers_completion():
    print("Waiting for LinkedIn scraping to complete...")
    linkedin_queue.join()
    print("LinkedIn scraping completed")
    
    print("Waiting for GitHub scraping to complete...")
    github_queue.join()
    print("GitHub scraping completed")
    
    print("Waiting for Resume parsing to complete...")
    resume_queue.join()
    print("Resume parsing completed")

def process_user_info(postID):
    global applicants
    
    with applicants_lock:
        applicants.clear()
    
    print('Getting applicants list...')
    info_dict = fetch_user_data(postID)
    if not info_dict:
        print("Failed to fetch user data")
        return {}
    
    users = info_dict['users']
    apps = info_dict['applications']
    reg_info = info_dict['registrations']
    
    if not users:
        print("No users found for the given post ID")
        return {}
    
    print(f'Processing {len(users)} users in parallel...')
    
    workers = start_scraper_workers()
    
    num_threads = min(MAX_WORKERS, len(users))
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        user_ids = list(executor.map(
            process_single_user,
            [(u, apps, reg_info) for u in users]
        ))
    
    print("User data processing completed. Waiting for external scraping...")
    
    wait_for_scrapers_completion()
    
    time.sleep(1)
    
    print("All processing completed!")
    
    with applicants_lock:
        return dict(applicants)

def get_processing_status():
    """Get current processing status"""
    return {
        "linkedin_queue_size": linkedin_queue.qsize(),
        "github_queue_size": github_queue.qsize(),
        "resume_queue_size": resume_queue.qsize(),
        "total_applicants": len(applicants)
    }

if __name__ == "__main__":
    start_time = time.time()
    
    try:
        results = process_user_info('68599a8b423958c44a738225')
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        print(f"\n=== Processing Summary ===")
        print(f"Total applicants processed: {len(results)}")
        print(f"Processing time: {processing_time:.2f} seconds")
        
        for user_id, data in results.items():
            user_name = data['user'].get('name', 'Unknown')
            linkedin_status = "✓" if data['linkedin_info'] else "✗"
            github_status = "✓" if data['github_info'] else "✗"
            resume_status = "✓" if data['resume_info'] else "✗"
            
            print(f"{user_name} ({user_id}): LinkedIn {linkedin_status}, GitHub {github_status}, Resume {resume_status}")
            
    except KeyboardInterrupt:
        print("\nProcessing interrupted by user")
    except Exception as e:
        print(f"Error during processing: {e}")
        import traceback
        traceback.print_exc()

