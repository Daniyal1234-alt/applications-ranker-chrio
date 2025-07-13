from dotenv import dotenv_values
from pymongo import MongoClient
from LinkedIn import LinkedIn_Scraper
from Github import Github_Scraper
from Resume import Resume_Reader
from Ranking_System import model
from bson.objectid import ObjectId
import threading, time
from concurrent.futures import ThreadPoolExecutor

config = dotenv_values(".env")

MAX_WORKERS = int(config.get("MAX_WORKERS", 10))

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

def fetch_job_post(postID):
    client = startup_db_client
    db = client[config["DB_NAME"]]

    if isinstance(postID, str):
        try:
            postID = ObjectId(postID)
        except Exception as e:
            print(f"Invalid postID: {e}")
            return
    
    job_post = db['posts'].findOne({'_id': postID})
    return job_post


def fetch_user_data(postID):
    client = startup_db_client()
    db = client[config["DB_NAME"]]

    applications = []
    users = []
    registrations = []  

    if isinstance(postID, str):
        try:
            postID = ObjectId(postID)
        except Exception as e:
            print(f"Invalid postID: {e}")
            return

    for app in db["applications"].find({"postId": postID}):
        # print(f"\nApplication: {app}")
        applications.append(app)

        user_id = app.get("userId")
        if not user_id:
            print("Skipping app without userId")
            continue

        user = db["users"].find_one({
            "_id": user_id,
            "type": "Applicant"
        })

        if user:
            # print(f"👤 User: {user['name']} ({user['_id']})")
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

    LINKEDIN_INDEX = 0
    GITHUB_INDEX = 1
    RESUME_INDEX = 2
    threads = [None] * 3
    results = [None] * 3

    def run_linkedin():
        if linkedin_url:
            print(f"[{user['_id']}] Scraping LinkedIn")
            try:
                results[LINKEDIN_INDEX] = LinkedIn_Scraper.scrape_linkedin_profile(
                    user['_id'], linkedin_url, config['LINKEDIN_EMAIL'], config['LINKEDIN_PASSWORD']
                )   
            except Exception as e:
                print(f"LinkedIn scraping error for {user['id']}: {e}")

    def run_github():
        if github_url:
            print(f"[{user['_id']}] Scraping GitHub")
            try:
                results[GITHUB_INDEX] = Github_Scraper.scrape_github_profile(
                    user['_id'], github_url
                )
            except Exception as e:
                print(f"Github scraping error for {user['id']}: {e}")


    def run_resume():
        if resume_url:
            print(f"[{user['_id']}] Parsing Resume")
            try:
                results[RESUME_INDEX] = Resume_Reader.parseResume(
                    user['_id'], resume_url, model='llama'
                )
            except Exception as e:
                print(f"[{user['_id']}] Scraping GitHub")
            

    threads[0] = threading.Thread(target=run_linkedin)
    threads[1] = threading.Thread(target=run_github)
    threads[2] = threading.Thread(target=run_resume)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    linkedIn_info = results[LINKEDIN_INDEX]
    github_info = results[GITHUB_INDEX]
    resume_info = results[RESUME_INDEX]

    print(f"Finished {user['_id']}")

    applicant_data = {
        "user": user,
        "skills": skills,
        "skill_matched": skill_matched,
        "about": [item for item in about_applicant if item],  
        "cover_letter": cover_letter,
        "work_experience": work_experience,
        "linkedin_info": linkedIn_info,
        "github_info": github_info,
        "resume_info": resume_info
    }

    with applicants_lock:
        applicants[user['_id']] = applicant_data

def process_user_info(postID):
    print('Getting applicants list')
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

    print('Processing info in parallel...')

    num_threads = min(MAX_WORKERS, len(users))
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        user_ids = list(executor.map(
            process_single_user,
            [(u, apps, reg_info) for u in users]
        ))

    with applicants_lock:
        return dict(applicants)

if __name__ == "__main__":
    # start_time = time.time()

    postID = '68599a8b423958c44a738225'
    
    try:
        applicant_list = process_user_info(postID)
        job_post = fetch_job_post(postID)

        model.get_ranked_list(job_post, applicant_list)
        
        # end_time = time.time()
        # processing_time = end_time - start_time
        
        # print(f"\n=== Processing Summary ===")
        # print(f"Total applicants processed: {len(results)}")
        # print(f"Processing time: {processing_time:.2f} seconds")
        
        # for user_id, data in results.items():
        #     user_name = data['user'].get('name', 'Unknown')
        #     linkedin_status = "✓" if data['linkedin_info'] else "✗"
        #     github_status = "✓" if data['github_info'] else "✗"
        #     resume_status = "✓" if data['resume_info'] else "✗"
            
        #     print(f"{user_name} ({user_id}): LinkedIn {linkedin_status}, GitHub {github_status}, Resume {resume_status}")
            
    except KeyboardInterrupt:
        print("\nProcessing interrupted by user")
    except Exception as e:
        print(f"Error during processing: {e}")
        import traceback
        traceback.print_exc()