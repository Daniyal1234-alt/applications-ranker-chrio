    def _get_skills(self, main_profile_url: str) -> List[str]:
        """Extract skills by navigating to the skills page"""
        skills_list = []
        try:
            print("Looking for 'Show all skills' link...")

            # Try different selectors for the "Show all skills" link
            skills_link_selectors = [
                'a[href*="/details/skills"]',  # Most specific
                'a[id*="Show-all"][id*="skills"]',  # Based on the ID pattern
                "a.pvs-navigation__text-wrapper",
                'a[aria-label*="skills"]',
            ]

            skills_link = None
            for selector in skills_link_selectors:
                try:
                    links = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for link in links:
                        link_text = link.text.lower()
                        href = link.get_attribute("href") or ""

                        if (
                            "show all" in link_text and "skill" in link_text
                        ) or "/details/skills" in href:
                            skills_link = link
                            print(
                                f"Found skills link with text: '{link.text}' and href: '{href}'"
                            )
                            break

                    if skills_link:
                        break
                except Exception as e:
                    print(f"Error with selector {selector}: {e}")
                    continue

            if skills_link:
                # Navigate to skills page
                skills_url = skills_link.get_attribute("href")
                print(f"Navigating to skills page: {skills_url}")
                self.driver.get(skills_url)
                time.sleep(3)  # Wait for skills page to load

                # Extract all skills from the skills page
                skills_list = self._extract_skills_from_page()

                # Navigate back to main profile
                print(f"Navigating back to main profile: {main_profile_url}")
                self.driver.get(main_profile_url)
                time.sleep(2)  # Wait for main page to load

            else:
                print(
                    "No 'Show all skills' link found, trying to extract from main page"
                )
                skills_list = self._extract_skills_from_main_page()

        except Exception as e:
            print(f"Error in _get_skills: {e}")
            # Fallback to main page extraction
            try:
                skills_list = self._extract_skills_from_main_page()
            except:
                pass

        print(f"Total unique skills found: {len(skills_list)}")
        if skills_list:
            print(f"First few skills: {skills_list[:5]}")

        return skills_list

    def _extract_skills_from_page(self) -> List[str]:
        """Extract skills from the dedicated skills page"""
        skills_list = []
        try:
            print("Extracting skills from skills page...")

            # Wait for the skills page to load
            time.sleep(2)

            # Scroll to load all skills
            self._scroll_page()

            # Try different selectors for skills on the dedicated page
            skills_selectors = [
                '.pvs-list__item .display-flex.align-items-center.mr1.hoverable-link-text.t-bold span[aria-hidden="true"]',
                '.pvs-list__item .hoverable-link-text.t-bold span[aria-hidden="true"]',
                '.pvs-list__item .t-bold span[aria-hidden="true"]',
                'li.artdeco-list__item .display-flex.align-items-center.mr1.hoverable-link-text.t-bold span[aria-hidden="true"]',
                'li.artdeco-list__item .hoverable-link-text.t-bold span[aria-hidden="true"]',
                'li.artdeco-list__item .t-bold span[aria-hidden="true"]',
                ".skill-category-entity__name",
                ".pv-skill-category-entity__name",
            ]

            for selector in skills_selectors:
                try:
                    skill_elements = self.driver.find_elements(
                        By.CSS_SELECTOR, selector
                    )
                    if skill_elements:
                        print(
                            f"Found {len(skill_elements)} skills with selector: {selector}"
                        )
                        for element in skill_elements:
                            try:
                                skill_name = element.text.strip()
                                if skill_name and skill_name not in skills_list:
                                    skills_list.append(skill_name)
                            except Exception as e:
                                print(f"Error extracting skill: {e}")
                                continue

                        if skills_list:
                            break
                except Exception as e:
                    print(f"Error with selector {selector}: {e}")
                    continue

            # If no skills found with specific selectors, try fallback
            if not skills_list:
                print("Trying fallback extraction on skills page...")
                fallback_selectors = [
                    '.pvs-list__item span[aria-hidden="true"]',
                    "li.artdeco-list__item span",
                    ".pvs-entity__caption-wrapper",
                ]

                for selector in fallback_selectors:
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            print(
                                f"Found {len(elements)} elements with fallback selector: {selector}"
                            )
                            for element in elements:
                                try:
                                    text = element.text.strip()
                                    # Filter out non-skill text
                                    if (
                                        text
                                        and len(text) > 1
                                        and len(text) < 100
                                        and not any(
                                            word in text.lower()
                                            for word in [
                                                "endorsed",
                                                "connections",
                                                "show",
                                                "all",
                                                "skills",
                                            ]
                                        )
                                        and text not in skills_list
                                    ):
                                        skills_list.append(text)
                                except:
                                    continue

                            if skills_list:
                                break
                    except Exception as e:
                        print(f"Error with fallback selector {selector}: {e}")
                        continue

        except Exception as e:
            print(f"Error extracting skills from page: {e}")

        # Clean up the skills list
        skills_list = list(dict.fromkeys(skills_list))  # Remove duplicates
        skills_list = [
            skill for skill in skills_list if skill and len(skill.strip()) > 1
        ]

        return skills_list

    def _extract_skills_from_main_page(self) -> List[str]:
        """Fallback method to extract skills from main profile page"""
        skills_list = []
        try:
            print("Extracting skills from main profile page...")

            # Try to find skills section on main page
            selectors = [
                "#skills",
                ".skills-section",
                ".pv-skill-categories-section",
                ".pv-skill-category-list",
            ]

            for selector in selectors:
                try:
                    skills_section = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )

                    # Find parent section
                    try:
                        parent_section = skills_section.find_element(
                            By.XPATH,
                            './ancestor::section[contains(@class, "artdeco-card")]',
                        )
                    except:
                        parent_section = skills_section

                    # Extract visible skills
                    skill_selectors = [
                        'li.artdeco-list__item .display-flex.align-items-center.mr1.hoverable-link-text.t-bold span[aria-hidden="true"]',
                        'li.artdeco-list__item .hoverable-link-text.t-bold span[aria-hidden="true"]',
                        ".skill-item .skill-item__name",
                        ".pv-skill-category-entity__name",
                    ]

                    for skill_selector in skill_selectors:
                        try:
                            skill_items = parent_section.find_elements(
                                By.CSS_SELECTOR, skill_selector
                            )
                            if skill_items:
                                print(
                                    f"Found {len(skill_items)} skills with selector: {skill_selector}"
                                )
                                for item in skill_items:
                                    try:
                                        skill_name = item.text.strip()
                                        if skill_name and skill_name not in skills_list:
                                            skills_list.append(skill_name)
                                    except:
                                        continue

                                if skills_list:
                                    break
                        except:
                            continue

                    if skills_list:
                        break

                except Exception as e:
                    print(f"Error with main page selector {selector}: {e}")
                    continue

        except Exception as e:
            print(f"Error extracting skills from main page: {e}")

        return skills_list
