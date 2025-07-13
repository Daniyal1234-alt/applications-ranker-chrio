from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import json
from typing import Dict, List, Optional
import re
import os
from dotenv import load_dotenv


class LinkedInScraper:
    def __init__(self):
        self.driver = None
        self.wait = None

    def setup_driver(self):
        """Initialize the Chrome WebDriver with appropriate options"""
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        # Add performance options
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-blink-features=AutomationControlled")
        # Uncomment the line below if you want to run in headless mode
        # options.add_argument('--headless')
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 10)  # Reduced wait time

    def login(self, email: str, password: str):
        """Login to LinkedIn"""
        self.driver.get("https://www.linkedin.com/login")

        # Enter email
        email_field = self.wait.until(
            EC.presence_of_element_located((By.ID, "username"))
        )
        email_field.send_keys(email)

        # Enter password
        password_field = self.driver.find_element(By.ID, "password")
        password_field.send_keys(password)

        # Click login button
        login_button = self.driver.find_element(
            By.CSS_SELECTOR, 'button[type="submit"]'
        )
        login_button.click()

        # Wait for login to complete
        time.sleep(2)  # Reduced wait time

    def validate_linkedin_url(self, url: str) -> str:
        """Validate and format LinkedIn profile URL"""
        # Remove any query parameters
        url = url.split("?")[0]

        # Handle different URL formats
        patterns = [
            r"https?://(?:www\.)?linkedin\.com/in/([^/]+)/?",  # Standard format
            r"https?://(?:www\.)?linkedin\.com/profile/view\?id=([^&]+)",  # ID format
            r"([^/]+)",  # Just the username
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                username = match.group(1)
                return f"https://www.linkedin.com/in/{username}/"

        raise ValueError("Invalid LinkedIn profile URL format")

    def get_profile_info(self, profile_url: str) -> Dict:
        """Extract information from a LinkedIn profile"""
        # Validate and format the URL
        formatted_url = self.validate_linkedin_url(profile_url)
        print(f"Accessing profile: {formatted_url}")

        self.driver.get(formatted_url)
        time.sleep(2)  # Reduced wait time

        # Scroll down to load more content
        self._scroll_page()

        profile_data = {
            "profile_url": formatted_url,
            "about": self._get_about(),
            "experience": self._get_experience(),
            "education": self._get_education(),
            "projects": self._get_projects(formatted_url),
            "certificates": self._get_certificates(formatted_url),
        }

        return profile_data

    def _scroll_page(self):
        """Scroll down the page to load more content"""
        SCROLL_PAUSE_TIME = 1  # Reduced pause time
        last_height = self.driver.execute_script("return document.body.scrollHeight")

        # Scroll more times to load posts and other content
        for _ in range(5):  # Increased from 3 to 5
            # Scroll down
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
            time.sleep(SCROLL_PAUSE_TIME)

            # Calculate new scroll height
            new_height = self.driver.execute_script("return document.body.scrollHeight")

            # Break if no more content
            if new_height == last_height:
                break
            last_height = new_height

    def _get_about(self) -> Optional[str]:
        """Extract about section"""
        try:
            # Try different selectors for about section
            selectors = [
                '.yozeCfRsmxqzgPSAFUghMVylfzjWitoNfLlqTd span[aria-hidden="true"]',  # More specific selector
                ".yozeCfRsmxqzgPSAFUghMVylfzjWitoNfLlqTd",  # Original selector
                ".display-flex.ph5.pv3 .inline-show-more-text",
                ".pv-shared-text-with-see-more-text .inline-show-more-text",
                ".pv-about__summary-text",
            ]

            for selector in selectors:
                try:
                    about_element = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    text = about_element.text.strip()
                    if text:
                        return text
                except:
                    continue
            return None
        except TimeoutException:
            return None

    def _get_experience(self) -> List[Dict]:
        """Extract experience information"""
        experience_list = []
        try:
            # Try different selectors for experience section
            selectors = [
                "#experience",  # New ID from HTML
                "#experience-section",
                ".experience-section",
                ".pv-experience-section",
            ]

            for selector in selectors:
                try:
                    experience_section = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )

                    # Find the parent section that contains the experience list
                    parent_section = experience_section.find_element(
                        By.XPATH,
                        './ancestor::section[contains(@class, "artdeco-card")]',
                    )

                    # Try different selectors for experience items based on new HTML structure
                    item_selectors = [
                        "li.artdeco-list__item",  # New structure
                        ".experience-item",
                        ".pv-entity__position-group-pager",
                        ".pv-entity__summary-info",
                    ]

                    for item_selector in item_selectors:
                        experience_items = parent_section.find_elements(
                            By.CSS_SELECTOR, item_selector
                        )
                        if experience_items:
                            for item in experience_items:
                                try:
                                    # Extract job title - try multiple selectors
                                    title = self._get_element_text(
                                        item,
                                        [
                                            '.display-flex.align-items-center.mr1.hoverable-link-text.t-bold span[aria-hidden="true"]',
                                            ".hoverable-link-text.t-bold span",
                                            ".experience-item__title",
                                            ".pv-entity__name",
                                            ".pv-entity__summary-info h3",
                                        ],
                                    )

                                    # Extract company name - try multiple selectors
                                    company = self._get_element_text(
                                        item,
                                        [
                                            '.t-14.t-normal span[aria-hidden="true"]',
                                            ".experience-item__subtitle",
                                            ".pv-entity__secondary-title",
                                            ".pv-entity__company-name",
                                        ],
                                    )

                                    # Extract duration - try multiple selectors
                                    duration = self._get_element_text(
                                        item,
                                        [
                                            '.t-14.t-normal.t-black--light .pvs-entity__caption-wrapper[aria-hidden="true"]',
                                            '.t-14.t-normal.t-black--light span[aria-hidden="true"]',
                                            ".experience-item__duration",
                                            ".pv-entity__date-range span:nth-child(2)",
                                            ".pv-entity__date-range",
                                        ],
                                    )

                                    # Extract location if available
                                    location = self._get_element_text(
                                        item,
                                        [
                                            '.t-14.t-normal.t-black--light span[aria-hidden="true"]:last-child',
                                            ".pv-entity__location span",
                                        ],
                                    )

                                    # Clean up company name (remove extra text like "· Internship")
                                    if company:
                                        company_parts = company.split(" · ")
                                        company_name = company_parts[0]
                                        job_type = (
                                            company_parts[1]
                                            if len(company_parts) > 1
                                            else None
                                        )
                                    else:
                                        company_name = company
                                        job_type = None

                                    if title or company_name:
                                        exp_data = {
                                            "title": title,
                                            "company": company_name,
                                            "duration": duration,
                                            "location": location,
                                        }
                                        if job_type:
                                            exp_data["job_type"] = job_type

                                        experience_list.append(exp_data)
                                except Exception as e:
                                    print(f"Error extracting experience item: {e}")
                                    continue

                            if experience_list:
                                break

                    if experience_list:
                        break

                except Exception as e:
                    print(
                        f"Error finding experience section with selector {selector}: {e}"
                    )
                    continue

        except TimeoutException:
            print("Timeout waiting for experience section")
            pass

        return experience_list

    def _get_education(self) -> List[Dict]:
        """Extract education information"""
        education_list = []
        try:
            # Try different selectors for education section
            selectors = [
                "#education",  # New ID pattern
                "#education-section",
                ".education-section",
                ".pv-education-section",
            ]

            for selector in selectors:
                try:
                    education_section = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )

                    # Find the parent section that contains the education list
                    try:
                        parent_section = education_section.find_element(
                            By.XPATH,
                            './ancestor::section[contains(@class, "artdeco-card")]',
                        )
                    except:
                        parent_section = education_section

                    # Try different selectors for education items based on new HTML structure
                    item_selectors = [
                        "li.artdeco-list__item",  # New structure
                        ".education-item",
                        ".pv-education-entity",
                        ".pv-entity__summary-info",
                    ]

                    for item_selector in item_selectors:
                        education_items = parent_section.find_elements(
                            By.CSS_SELECTOR, item_selector
                        )
                        if education_items:
                            for item in education_items:
                                try:
                                    # Extract school name - try multiple selectors
                                    school = self._get_element_text(
                                        item,
                                        [
                                            '.display-flex.align-items-center.mr1.hoverable-link-text.t-bold span[aria-hidden="true"]',
                                            ".hoverable-link-text.t-bold span",
                                            ".education-item__school-name",
                                            ".pv-entity__school-name",
                                            ".pv-entity__degree-name",
                                        ],
                                    )

                                    # Extract degree - try multiple selectors
                                    degree = self._get_element_text(
                                        item,
                                        [
                                            '.t-14.t-normal span[aria-hidden="true"]',
                                            ".education-item__degree-name",
                                            ".pv-entity__degree-name",
                                            ".pv-entity__fos",
                                        ],
                                    )

                                    # Extract duration - try multiple selectors
                                    duration = self._get_element_text(
                                        item,
                                        [
                                            '.t-14.t-normal.t-black--light .pvs-entity__caption-wrapper[aria-hidden="true"]',
                                            '.t-14.t-normal.t-black--light span[aria-hidden="true"]',
                                            ".education-item__duration",
                                            ".pv-entity__dates span:nth-child(2)",
                                            ".pv-entity__dates",
                                        ],
                                    )

                                    if school or degree:
                                        education_list.append(
                                            {
                                                "school": school,
                                                "degree": degree,
                                                "duration": duration,
                                            }
                                        )
                                except Exception as e:
                                    print(f"Error extracting education item: {e}")
                                    continue

                            if education_list:
                                break

                    if education_list:
                        break

                except Exception as e:
                    print(
                        f"Error finding education section with selector {selector}: {e}"
                    )
                    continue

        except TimeoutException:
            print("Timeout waiting for education section")
            pass

        return education_list

    def _get_projects(self, main_profile_url: str) -> List[Dict]:
        """Extract projects data"""
        projects_list = []
        try:
            print("Looking for projects section...")

            # First check if any projects section exists at all
            initial_check_selectors = [
                'a[href*="/details/projects"]',
                'a[id*="navigation-index-see-all-projects"]',
                'a[href*="projects"]',
                'button[aria-label*="projects"]',
                "#projects",
                ".projects-section",
                ".pv-projects-section",
            ]

            projects_exist = False
            for selector in initial_check_selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    projects_exist = True
                    break

            if not projects_exist:
                print(
                    "No projects section found on this profile. Skipping projects extraction."
                )
                return projects_list

            # Try to find and click "Show all projects" button
            try:
                # Look for projects section button
                projects_button_selectors = [
                    'a[href*="/details/projects"]',
                    'a[id*="navigation-index-see-all-projects"]',
                    'a[href*="projects"]',
                    'button[aria-label*="projects"]',
                ]

                projects_button = None
                for selector in projects_button_selectors:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        element_text = element.text.lower()
                        href = element.get_attribute("href") or ""

                        if (
                            "show all" in element_text and "project" in element_text
                        ) or "/details/projects" in href:
                            projects_button = element
                            print(
                                f"Found projects button with text: '{element.text}' and href: '{href}'"
                            )
                            break

                    if projects_button:
                        break

                if projects_button:
                    # Navigate to projects page
                    projects_url = projects_button.get_attribute("href")
                    print(f"Navigating to projects page: {projects_url}")
                    self.driver.get(projects_url)
                    time.sleep(3)  # Wait for projects page to load

                    # Extract all projects from the projects page
                    projects_list = self._extract_projects_from_page()

                    # Navigate back to main profile
                    print(f"Navigating back to main profile: {main_profile_url}")
                    self.driver.get(main_profile_url)
                    time.sleep(2)  # Wait for main page to load

                else:
                    print(
                        "No 'Show all projects' button found, trying to extract from main page"
                    )
                    projects_list = self._extract_projects_from_main_page()

            except Exception as e:
                print(f"Error navigating to projects section: {e}")
                # Fallback to main page extraction
                projects_list = self._extract_projects_from_main_page()

        except Exception as e:
            print(f"Error getting projects: {e}")
            print("Continuing without projects data...")

        print(f"Total projects found: {len(projects_list)}")
        return projects_list

    def _extract_projects_from_page(self) -> List[Dict]:
        """Extract projects from the dedicated projects page"""
        projects_list = []
        try:
            print("Extracting projects from projects page...")

            # Wait for the projects page to load
            time.sleep(2)

            # Scroll to load all projects
            self._scroll_page()

            # Try different selectors for project items on the dedicated page
            project_selectors = [
                "li.pvs-list__paged-list-item",  # Main container for project items
                "li.artdeco-list__item.pvs-list__item--line-separated",  # More specific selector
                "li.artdeco-list__item",  # Main container for project items
                ".pvs-list__item",
                'div[data-view-name="profile-component-entity"]',
            ]

            for selector in project_selectors:
                try:
                    project_elements = self.driver.find_elements(
                        By.CSS_SELECTOR, selector
                    )
                    if project_elements:
                        print(
                            f"Found {len(project_elements)} projects with selector: {selector}"
                        )

                        for i, element in enumerate(project_elements):
                            try:
                                print(
                                    f"Processing project {i+1}/{len(project_elements)}"
                                )
                                project_data = self._extract_project_data(element)
                                if project_data:
                                    # Check for duplicates by title
                                    is_duplicate = any(
                                        proj.get("title") == project_data.get("title")
                                        for proj in projects_list
                                    )
                                    if not is_duplicate:
                                        projects_list.append(project_data)
                                        print(
                                            f"Added project: {project_data.get('title', 'Unknown')}"
                                        )
                                    else:
                                        print(
                                            f"Skipped duplicate project: {project_data.get('title', 'Unknown')}"
                                        )
                            except Exception as e:
                                print(f"Error extracting project {i+1}: {e}")
                                continue

                        if projects_list:
                            break

                except Exception as e:
                    print(f"Error with selector {selector}: {e}")
                    continue

        except Exception as e:
            print(f"Error extracting projects from page: {e}")

        return projects_list

    def _extract_projects_from_main_page(self) -> List[Dict]:
        """Fallback method to extract projects from main profile page"""
        projects_list = []
        try:
            print("Extracting projects from main profile page...")

            # Try to find projects section on main page - use non-blocking find_elements
            selectors = [
                "#projects",
                ".projects-section",
                ".pv-projects-section",
            ]

            for selector in selectors:
                try:
                    # Use find_elements instead of wait.until to avoid timeout exceptions
                    projects_sections = self.driver.find_elements(
                        By.CSS_SELECTOR, selector
                    )

                    if not projects_sections:
                        continue

                    projects_section = projects_sections[0]
                    print(f"Found projects section with selector: {selector}")

                    # Find parent section
                    try:
                        parent_section = projects_section.find_element(
                            By.XPATH,
                            './ancestor::section[contains(@class, "artdeco-card")]',
                        )
                    except:
                        parent_section = projects_section

                    # Extract visible projects
                    project_items = parent_section.find_elements(
                        By.CSS_SELECTOR, "li.artdeco-list__item"
                    )

                    if project_items:
                        print(f"Found {len(project_items)} projects on main page")
                        for item in project_items:
                            try:
                                project_data = self._extract_project_data(item)
                                if project_data:
                                    projects_list.append(project_data)
                            except:
                                continue

                    if projects_list:
                        break

                except Exception as e:
                    print(f"Error with main page selector {selector}: {e}")
                    continue

            if not projects_list:
                print("No projects found on main profile page")

        except Exception as e:
            print(f"Error extracting projects from main page: {e}")

        return projects_list

    def _extract_project_data(self, project_element) -> Optional[Dict]:
        """Extract data from a single project"""
        try:
            project_data = {}

            # Extract project title - try multiple selectors
            title_selectors = [
                '.display-flex.align-items-center.mr1.t-bold span[aria-hidden="true"]',
                '.hoverable-link-text.t-bold span[aria-hidden="true"]',
                '.t-bold span[aria-hidden="true"]',
                '.display-flex.align-items-center.mr1.hoverable-link-text.t-bold span[aria-hidden="true"]',
            ]

            title = self._get_element_text(project_element, title_selectors)
            if title:
                project_data["title"] = title

            # Extract project duration
            duration_selectors = [
                '.t-14.t-normal span[aria-hidden="true"]',
                ".t-14.t-normal",
                '.pvs-entity__caption-wrapper span[aria-hidden="true"]',
            ]

            duration = self._get_element_text(project_element, duration_selectors)
            if duration:
                project_data["duration"] = duration

            # Extract project description
            description_selectors = [
                '.inline-show-more-text span[aria-hidden="true"]',
                '.bdZjlATLciupslqErVKaEhgLJmpKCjM span[aria-hidden="true"]',
                '.t-14.t-normal.t-black.display-flex.align-items-center span[aria-hidden="true"]',
            ]

            description = self._get_element_text(project_element, description_selectors)
            if description:
                project_data["description"] = description

            # Extract associated skills
            try:
                skills_elements = project_element.find_elements(
                    By.CSS_SELECTOR,
                    ".hoverable-link-text.display-flex.align-items-center.t-14.t-normal.t-black strong",
                )
                if skills_elements:
                    skills_text = skills_elements[0].text.strip()
                    project_data["skills"] = skills_text
            except:
                pass

            # Extract external links/URLs
            try:
                link_elements = project_element.find_elements(
                    By.CSS_SELECTOR, 'a[href]:not([href*="linkedin.com"])'
                )
                if link_elements:
                    external_links = []
                    for link in link_elements:
                        href = link.get_attribute("href")
                        if href and href.startswith("http"):
                            link_data = {"url": href}

                            # Try to get link title
                            try:
                                link_title_element = link.find_element(
                                    By.CSS_SELECTOR,
                                    '.t-14.t-bold.break-words span[aria-hidden="true"]',
                                )
                                link_data["title"] = link_title_element.text.strip()
                            except:
                                pass

                            external_links.append(link_data)

                    if external_links:
                        project_data["external_links"] = external_links
            except:
                pass

            # Only return if we have at least a title
            if project_data.get("title"):
                return project_data

        except Exception as e:
            print(f"Error extracting individual project data: {e}")

        return None

    def _get_certificates(self, main_profile_url: str) -> List[Dict]:
        """Extract certificates and licenses data"""
        certificates_list = []
        try:
            print("Looking for certificates section...")

            # First check if any certificates section exists at all
            initial_check_selectors = [
                'a[href*="/details/certifications"]',
                'a[id*="navigation-index-see-all-licenses-and-certifications"]',
                'a[href*="certifications"]',
                'button[aria-label*="certificates"]',
                'button[aria-label*="licenses"]',
                "#licenses_and_certifications",
                "#certifications",
                ".licenses-certifications-section",
                ".pv-certifications-section",
            ]

            certificates_exist = False
            for selector in initial_check_selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    certificates_exist = True
                    break

            if not certificates_exist:
                print(
                    "No certificates section found on this profile. Skipping certificates extraction."
                )
                return certificates_list

            # Try to find and click "Show all certificates" button
            try:
                # Look for certificates section button
                certificates_button_selectors = [
                    'a[href*="/details/certifications"]',
                    'a[id*="navigation-index-see-all-licenses-and-certifications"]',
                    'a[href*="certifications"]',
                    'button[aria-label*="certificates"]',
                    'button[aria-label*="licenses"]',
                ]

                certificates_button = None
                for selector in certificates_button_selectors:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for element in elements:
                        element_text = element.text.lower()
                        href = element.get_attribute("href") or ""

                        if (
                            "show all" in element_text
                            and (
                                "certificate" in element_text
                                or "license" in element_text
                            )
                        ) or "/details/certifications" in href:
                            certificates_button = element
                            print(
                                f"Found certificates button with text: '{element.text}' and href: '{href}'"
                            )
                            break

                    if certificates_button:
                        break

                if certificates_button:
                    # Navigate to certificates page
                    certificates_url = certificates_button.get_attribute("href")
                    print(f"Navigating to certificates page: {certificates_url}")
                    self.driver.get(certificates_url)
                    time.sleep(3)  # Wait for certificates page to load

                    # Extract all certificates from the certificates page
                    certificates_list = self._extract_certificates_from_page()

                    # Navigate back to main profile
                    print(f"Navigating back to main profile: {main_profile_url}")
                    self.driver.get(main_profile_url)
                    time.sleep(2)  # Wait for main page to load

                else:
                    print(
                        "No 'Show all certificates' button found, trying to extract from main page"
                    )
                    certificates_list = self._extract_certificates_from_main_page()

            except Exception as e:
                print(f"Error navigating to certificates section: {e}")
                # Fallback to main page extraction
                certificates_list = self._extract_certificates_from_main_page()

        except Exception as e:
            print(f"Error getting certificates: {e}")
            print("Continuing without certificates data...")

        print(f"Total certificates found: {len(certificates_list)}")
        return certificates_list

    def _extract_certificates_from_page(self) -> List[Dict]:
        """Extract certificates from the dedicated certificates page"""
        certificates_list = []
        try:
            print("Extracting certificates from certificates page...")

            # Wait for the certificates page to load
            time.sleep(2)

            # Scroll to load all certificates
            self._scroll_page()

            # Try different selectors for certificate items on the dedicated page
            certificate_selectors = [
                "li.pvs-list__paged-list-item",  # Main container for certificate items
                "li.artdeco-list__item.pvs-list__item--line-separated",  # More specific selector
                "li.artdeco-list__item",
                ".pvs-list__item",
                'div[data-view-name="profile-component-entity"]',
            ]

            for selector in certificate_selectors:
                try:
                    certificate_elements = self.driver.find_elements(
                        By.CSS_SELECTOR, selector
                    )
                    if certificate_elements:
                        print(
                            f"Found {len(certificate_elements)} certificates with selector: {selector}"
                        )

                        for i, element in enumerate(certificate_elements):
                            try:
                                print(
                                    f"Processing certificate {i+1}/{len(certificate_elements)}"
                                )
                                certificate_data = self._extract_certificate_data(
                                    element
                                )
                                if certificate_data:
                                    # Check for duplicates by title
                                    is_duplicate = any(
                                        cert.get("title")
                                        == certificate_data.get("title")
                                        for cert in certificates_list
                                    )
                                    if not is_duplicate:
                                        certificates_list.append(certificate_data)
                                        print(
                                            f"Added certificate: {certificate_data.get('title', 'Unknown')}"
                                        )
                                    else:
                                        print(
                                            f"Skipped duplicate certificate: {certificate_data.get('title', 'Unknown')}"
                                        )
                            except Exception as e:
                                print(f"Error extracting certificate {i+1}: {e}")
                                continue

                        if certificates_list:
                            break

                except Exception as e:
                    print(f"Error with selector {selector}: {e}")
                    continue

        except Exception as e:
            print(f"Error extracting certificates from page: {e}")

        return certificates_list

    def _extract_certificates_from_main_page(self) -> List[Dict]:
        """Fallback method to extract certificates from main profile page"""
        certificates_list = []
        try:
            print("Extracting certificates from main profile page...")

            # Try to find certificates section on main page
            selectors = [
                "#licenses_and_certifications",
                "#certifications",
                ".licenses-certifications-section",
                ".pv-certifications-section",
            ]

            for selector in selectors:
                try:
                    # Use find_elements instead of wait.until to avoid timeout exceptions
                    certificates_sections = self.driver.find_elements(
                        By.CSS_SELECTOR, selector
                    )

                    if not certificates_sections:
                        continue

                    certificates_section = certificates_sections[0]
                    print(f"Found certificates section with selector: {selector}")

                    # Find parent section
                    try:
                        parent_section = certificates_section.find_element(
                            By.XPATH,
                            './ancestor::section[contains(@class, "artdeco-card")]',
                        )
                    except:
                        parent_section = certificates_section

                    # Extract visible certificates
                    certificate_items = parent_section.find_elements(
                        By.CSS_SELECTOR, "li.artdeco-list__item"
                    )

                    if certificate_items:
                        print(
                            f"Found {len(certificate_items)} certificates on main page"
                        )
                        for item in certificate_items:
                            try:
                                certificate_data = self._extract_certificate_data(item)
                                if certificate_data:
                                    certificates_list.append(certificate_data)
                            except:
                                continue

                    if certificates_list:
                        break

                except Exception as e:
                    print(f"Error with main page selector {selector}: {e}")
                    continue

            if not certificates_list:
                print("No certificates found on main profile page")

        except Exception as e:
            print(f"Error extracting certificates from main page: {e}")

        return certificates_list

    def _extract_certificate_data(self, certificate_element) -> Optional[Dict]:
        """Extract data from a single certificate"""
        try:
            certificate_data = {}

            # Extract certificate title - try multiple selectors
            title_selectors = [
                '.display-flex.align-items-center.mr1.hoverable-link-text.t-bold span[aria-hidden="true"]',
                '.hoverable-link-text.t-bold span[aria-hidden="true"]',
                '.display-flex.align-items-center.mr1.t-bold span[aria-hidden="true"]',
                '.t-bold span[aria-hidden="true"]',
            ]

            title = self._get_element_text(certificate_element, title_selectors)
            if title:
                certificate_data["title"] = title

            # Extract issuing organization
            organization_selectors = [
                '.t-14.t-normal span[aria-hidden="true"]',
                ".t-14.t-normal",
            ]

            organization = self._get_element_text(
                certificate_element, organization_selectors
            )
            if organization:
                certificate_data["issuing_organization"] = organization

            # Extract issue date and expiry
            date_selectors = [
                '.t-14.t-normal.t-black--light .pvs-entity__caption-wrapper[aria-hidden="true"]',
                '.t-14.t-normal.t-black--light span[aria-hidden="true"]',
                '.pvs-entity__caption-wrapper span[aria-hidden="true"]',
            ]

            # Get all date-related text elements
            date_elements = []
            for selector in date_selectors:
                try:
                    elements = certificate_element.find_elements(
                        By.CSS_SELECTOR, selector
                    )
                    for elem in elements:
                        text = elem.text.strip()
                        if text and (
                            "issued" in text.lower()
                            or "expired" in text.lower()
                            or any(
                                month in text.lower()
                                for month in [
                                    "jan",
                                    "feb",
                                    "mar",
                                    "apr",
                                    "may",
                                    "jun",
                                    "jul",
                                    "aug",
                                    "sep",
                                    "oct",
                                    "nov",
                                    "dec",
                                ]
                            )
                        ):
                            date_elements.append(text)
                except:
                    continue

            # Parse issue and expiry dates
            for date_text in date_elements:
                if "issued" in date_text.lower():
                    certificate_data["issue_date"] = date_text
                elif "expired" in date_text.lower():
                    certificate_data["expiry_date"] = date_text

            # Extract credential ID
            try:
                credential_elements = certificate_element.find_elements(
                    By.CSS_SELECTOR,
                    '.t-14.t-normal.t-black--light span[aria-hidden="true"]',
                )
                for elem in credential_elements:
                    text = elem.text.strip()
                    if "credential id" in text.lower():
                        certificate_data["credential_id"] = text
                        break
            except:
                pass

            # Extract associated skills
            try:
                skills_elements = certificate_element.find_elements(
                    By.CSS_SELECTOR,
                    '.display-flex.align-items-center.t-14.t-normal.t-black span[aria-hidden="true"]',
                )
                for elem in skills_elements:
                    text = elem.text.strip()
                    if "skills:" in text.lower():
                        # Extract skills part after "Skills:"
                        skills_part = text.split("Skills:")[-1].strip()
                        certificate_data["skills"] = skills_part
                        break
            except:
                pass

            # Extract external credential links
            try:
                # Look for "Show credential" buttons
                credential_buttons = certificate_element.find_elements(
                    By.CSS_SELECTOR,
                    'a[aria-label*="Show credential"], a[href]:not([href*="linkedin.com"])',
                )

                external_links = []
                for button in credential_buttons:
                    href = button.get_attribute("href")
                    if href and href.startswith("http") and "linkedin.com" not in href:
                        link_data = {"url": href, "type": "credential"}

                        # Try to get button text
                        button_text = button.text.strip()
                        if button_text:
                            link_data["text"] = button_text

                        external_links.append(link_data)

                if external_links:
                    certificate_data["external_links"] = external_links
            except:
                pass

            # Extract certificate documents/PDFs
            try:
                document_links = certificate_element.find_elements(
                    By.CSS_SELECTOR, 'a[href*="single-media-viewer"]'
                )

                documents = []
                for link in document_links:
                    href = link.get_attribute("href")
                    if href:
                        doc_data = {"url": href, "type": "document"}

                        # Try to get document title
                        try:
                            doc_title_element = link.find_element(
                                By.CSS_SELECTOR,
                                '.t-14.t-bold.break-words span[aria-hidden="true"]',
                            )
                            doc_data["title"] = doc_title_element.text.strip()
                        except:
                            pass

                        documents.append(doc_data)

                if documents:
                    certificate_data["documents"] = documents
            except:
                pass

            # Only return if we have at least a title
            if certificate_data.get("title"):
                return certificate_data

        except Exception as e:
            print(f"Error extracting individual certificate data: {e}")

        return None

    def _get_element_text(self, element, selectors: List[str]) -> Optional[str]:
        """Try multiple selectors to get element text"""
        for selector in selectors:
            try:
                text_element = element.find_element(By.CSS_SELECTOR, selector)
                return text_element.text.strip()
            except NoSuchElementException:
                continue
        return None

    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()


def scrape_linkedin_profile(
    applicant_id: str, profile_url: str, email: str = None, password: str = None
) -> Dict:

    if not email or not password:
        load_dotenv()
        email = email or os.getenv("LINKEDIN_EMAIL")
        password = password or os.getenv("LINKEDIN_PASSWORD")

        if not email or not password:
            raise ValueError(
                "LinkedIn credentials not found. Please provide email and password or set them in .env file"
            )

    # Initialize the scraper
    scraper = LinkedInScraper()
    scraper.setup_driver()

    try:
        # Login to LinkedIn
        scraper.login(email, password)

        # Scrape profile information
        profile_data = scraper.get_profile_info(profile_url)
        data = {"id": applicant_id,
                "source": "linkedin",
                "data": profile_data}
        return data

    except Exception as e:
        raise Exception(f"Error scraping profile: {str(e)}")
    finally:
        scraper.close()


# Example usage:
# if __name__ == "__main__":
#     # Example 1: Using environment variables
#     profile_data = scrape_linkedin_profile(
#         "https://www.linkedin.com/in/moaz-farooq-466326304/"
#     )

#     # Save to file
#     filename = f"profile_data_{int(time.time())}.json"
#     with open(filename, "w", encoding="utf-8") as f:
#         json.dump(profile_data, f, indent=4, ensure_ascii=False)
#     print(f"Profile data has been saved to '{filename}'")
