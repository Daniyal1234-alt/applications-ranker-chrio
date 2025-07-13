import os
import mimetypes
import gdown
import json
from pdfminer.high_level import extract_text
from docx import Document
import ollama
import re
from openai import OpenAI


def is_url(path_or_url):
    return path_or_url.startswith("http://") or path_or_url.startswith("https://")


class resumeParser:
    def __init__(self):
        self.counter = 0
        self.prompt_template = """
        You are a professional resume parser AI. Your task is to extract structured information from raw resume text and output it in a specific JSON format. You must be thorough, accurate, and consistent.
        Output Format Requirements
        Return ONLY a valid JSON object with this exact structure:
        json{
        "name": "",
        "email": "",
        "phone": "",
        "education": [
            {
            "degree": "",
            "institute": "",
            "marks_or_cgpa": "",
            "start": "",
            "end": "",
            "courses": []
            }
        ],
        "experience": [
            {
            "company": "",
            "role": "",
            "description": "",
            "start": "",
            "end": ""
            }
        ],
        "projects": [
            {
            "title": "",
            "tech": []
            }
        ],
        "skills": []
        }
        Extraction Rules
        Contact Information

        Name: Extract full name (first and last name)
        Email: Extract email address in standard format
        Phone: Extract phone number, normalize format (remove special characters except +, -, and spaces)

        Education

        Degree: Full degree name (e.g., "Bachelor of Science in Computer Science", "Master of Business Administration")
        Institute: Complete institution name
        Marks/CGPA: Extract as written - can be percentage ("85%"), fraction ("3.8/4.0"), or number ("989/1100")
        Start/End: Normalize dates to YYYY-MM format (e.g., "June 2023" → "2023-06", "2020" → "2020-01")
        Courses: Extract from coursework sections, relevant coursework, or course lists

        Experience

        Company: Full company/organization name
        Role: Job title/position
        Description: Complete job description or bullet points as single text
        Start/End: Normalize dates to YYYY-MM format, use "Present" for current positions

        Projects

        Title: Project name
        Tech: Array of all technologies, frameworks, languages, tools mentioned for that project

        Skills

        Extract all technical skills, programming languages, tools, frameworks, certifications
        Include soft skills if explicitly mentioned in a skills section

        Data Normalization Guidelines
        Date Formats

        "June 2023" → "2023-06"
        "Jun 2023" → "2023-06"
        "2023" → "2023-01"
        "Present", "Current", "Now" → "Present"

        Missing Information

        Use empty string "" for missing text fields
        Use empty array [] for missing array fields
        Never use null or omit fields

        Text Cleaning

        Remove excessive whitespace
        Preserve original capitalization for names and titles
        Clean up formatting artifacts (bullets, special characters)

        Examples
        Example 1: Standard Resume
        Input:
        John Doe
        john.doe@email.com | (555) 123-4567

        EDUCATION
        Bachelor of Science in Computer Science
        University of California, Berkeley
        GPA: 3.8/4.0
        Aug 2019 - May 2023
        Relevant Coursework: Data Structures, Algorithms, Database Systems

        EXPERIENCE
        Software Engineer
        Google Inc.
        June 2023 - Present
        - Developed web applications using React and Node.js
        - Collaborated with cross-functional teams

        PROJECTS
        E-commerce Website
        Technologies: React, Node.js, MongoDB, Express.js

        SKILLS
        Python, JavaScript, React, Node.js, SQL, Git
        Expected Output:
        json{
        "name": "John Doe",
        "email": "john.doe@email.com",
        "phone": "(555) 123-4567",
        "education": [
            {
            "degree": "Bachelor of Science in Computer Science",
            "institute": "University of California, Berkeley",
            "marks_or_cgpa": "3.8/4.0",
            "start": "2019-08",
            "end": "2023-05",
            "courses": ["Data Structures", "Algorithms", "Database Systems"]
            }
        ],
        "experience": [
            {
            "company": "Google Inc.",
            "role": "Software Engineer",
            "description": "Developed web applications using React and Node.js. Collaborated with cross-functional teams",
            "start": "2023-06",
            "end": "Present"
            }
        ],
        "projects": [
            {
            "title": "E-commerce Website",
            "tech": ["React", "Node.js", "MongoDB", "Express.js"]
            }
        ],
        "skills": ["Python", "JavaScript", "React", "Node.js", "SQL", "Git"]
        }
        Example 2: Minimal Resume
        Input:
        Jane Smith
        jane@email.com

        Software Developer at Tech Corp
        Built mobile apps

        Skills: Java, Android
        Expected Output:
        json{
        "name": "Jane Smith",
        "email": "jane@email.com",
        "phone": "",
        "education": [],
        "experience": [
            {
            "company": "Tech Corp",
            "role": "Software Developer",
            "description": "Built mobile apps",
            "start": "",
            "end": ""
            }
        ],
        "projects": [],
        "skills": ["Java", "Android"]
        }
        Critical Instructions

        Output ONLY the JSON - no explanations, comments, or additional text
        Maintain exact field names - case-sensitive
        Always include all fields - even if empty
        Validate JSON format - ensure proper syntax
        Be consistent - apply rules uniformly across all sections

        Error Handling

        If text is unclear or ambiguous, make reasonable assumptions
        If dates are incomplete, use available information (e.g., "2023" becomes "2023-01")
        If multiple formats exist for same information, choose the most complete one


        Raw resume text:
        """
        self.client = ollama.Client()

    def downloadFile(self, URL=None):
        if not URL:
            raise ValueError("❌ The URL is empty")

        fileID = URL.split('/d/')[1].split('/')[0]
        outputPath = f'Resume/CV/{fileID}.pdf'
        downloadURL = f'https://drive.google.com/uc?id={fileID}'

        if os.path.exists(outputPath):
            print("✅ File already exists locally.")
            return fileID, outputPath

        gdown.download(downloadURL, outputPath, quiet=False)
        return fileID, outputPath

    def checkFileType(self, filePath=None):
        if not filePath or not os.path.exists(filePath):
            return "❌ File does not exist."

        fileType, _ = mimetypes.guess_type(filePath)
        if fileType == "application/pdf":
            return "PDF"
        elif fileType == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            return "DOCX"
        else:
            return "UNSUPPORTED"

    def extractText(self, filePath):
        fileType = self.checkFileType(filePath)
        if fileType == "PDF":
            return extract_text(filePath)
        elif fileType == "DOCX":
            return self._extractDocxText(filePath)
        else:
            return "❌ Unsupported file type or file not found."

    def _extractDocxText(self, filePath):
        doc = Document(filePath)
        return "\n".join(para.text for para in doc.paragraphs)

    def jsonToDict(self, json_string):
        try:
            return json.loads(json_string)
        except json.JSONDecodeError as e:
            print(f"❌ JSON decode error: {e}")
            return {}

    def generateInformation_DeepSeekR1(self, text, api_key):
        prompt = self.prompt_template + text
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )
        completion = client.chat.completions.create(
            model="deepseek/deepseek-r1:free",
            messages=[{"role": "user", "content": prompt}]
        )
        return completion.choices[0].message.content

    def generateInformation_ChatGPT(self, text):
        pass  # For future use

    def generateInformation_LLAMA(self, text):
        prompt = self.prompt_template + text
        response = self.client.generate(model="llama2", prompt=prompt)
        return response.response

    def generateInformation_Mystel(self, text):
        prompt = self.prompt_template + text
        response = self.client.generate(model="mistral", prompt=prompt)
        return response.response

    def parseWithLLM(self, text, engine="llama", api_key=None):
        print("🧠 Extracting Information using", engine.capitalize(), "...")
        raw_json = ""

        if engine == "deepseek":
            raw_json = self.generateInformation_DeepSeekR1(text, api_key)
        elif engine == "chatgpt":
            raw_json = self.generateInformation_ChatGPT(text)
        elif engine == "llama":
            raw_json = self.generateInformation_LLAMA(text)
        elif engine == "mystel":
            raw_json = self.generateInformation_Mystel(text)
        else:
            raise ValueError("❌ Invalid engine selected. Choose from deepseek, chatgpt, llama, mystel.")

        def clean_llm_output(raw_output):
            # Remove code block markers
            cleaned = re.sub(r"```(?:json)?\n?|```", "", raw_output).strip()
            # Extract only the JSON object between the first { and last }
            start = cleaned.find('{')
            end = cleaned.rfind('}')
            if start != -1 and end != -1 and end > start:
                return cleaned[start:end+1]
            return cleaned
        cleaned_json = clean_llm_output(raw_json)
        print("📝 Parsed JSON:", cleaned_json)
        return self.jsonToDict(cleaned_json)

    def resumeToDictionary(self, path_or_url=None, model=None, api_key=None):
        """
        High-level method that handles both URLs and local files.
        Parameters:
            path_or_url (str): Google Drive link OR local file path.
        """
        if not path_or_url:
            return "❌ URL or file path is empty."

        # Handle Google Drive download
        if is_url(path_or_url):
            file_id, local_path = self.downloadFile(path_or_url)
        else:
            local_path = path_or_url
            if not os.path.exists(local_path):
                return "❌ Local file does not exist."

        raw_text = self.extractText(local_path)
        parsed_resume = self.parseWithLLM(raw_text, model, api_key)
        return parsed_resume


def parseResume(applicant_id, path_or_url, model=None, api_key=None):
    parser = resumeParser()
    data = {
        "id": applicant_id,
        "source": "resume",
        "data": parser.resumeToDictionary(path_or_url, model, api_key)
    }
    return data

# === Test ===
# result = parseResume("123", "CV/sample.pdf", model="llama")
# print(result)
