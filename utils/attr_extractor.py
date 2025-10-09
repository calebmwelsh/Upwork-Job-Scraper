"""
Upwork Job Data Extraction Module

This module extracts specific job data fields from HTML strings containing Upwork job postings.
It handles various data sources including JSON embedded in script tags, HTML attributes, and text content.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

# Configure logging
from .logger import Logger

logger_obj = Logger(level="DEBUG")
logger = logger_obj.get_logger()

class JobAttrExtractor:
    """Extract job data from Upwork HTML content"""
    
    def __init__(self):
        # Define the fields we want to extract
        self.target_fields = [
            'applicants',
            'buyer_avgHourlyJobsRate_amount',
            'buyer_company_contractDate',
            'buyer_hire_rate_pct',
            'buyer_jobs_openCount',
            'buyer_jobs_postedCount',
            'buyer_location_city',
            'buyer_location_countryTimezone',
            'buyer_location_localTime',
            'buyer_location_offsetFromUtcMillis',
            'buyer_stats_activeAssignmentsCount',
            'buyer_stats_hoursCount',
            'buyer_stats_totalJobsWithHires',
            'category',
            'categoryGroup_name',
            'categoryGroup_urlSlug',
            'category_name',
            'category_urlSlug',
            'clientActivity_invitationsSent',
            'clientActivity_totalHired',
            'clientActivity_totalInvitedToInterview',
            'clientActivity_unansweredInvites',
            'client_company_size',
            'client_country',
            'client_hires',
            'client_industry',
            'client_rating',
            'client_reviews',
            'client_total_spent',
            'connects_required',
            'contractorTier',
            'currency',
            'description',
            'duration',
            'enterpriseJob',
            'fixed_budget_amount',
            'hourly_max',
            'hourly_min',
            'isContractToHire',
            'job_id',
            'lastBuyerActivity',
            'level',
            'numberOfPositionsToHire',
            'payment_verified',
            'phone_verified',
            'premium',
            'qualifications',
            'questions',
            'skills',
            'title',
            'ts_create',
            'ts_publish',
            'type',
            'url'
        ]
    
    def extract_from_html(self, html_content: str, job_id: str = None) -> Dict[str, Any]:
        """
        Extract job data from HTML content string
        
        Args:
            html_content: HTML content as string
            job_id: Optional job ID to include in results
            
        Returns:
            Dictionary containing extracted job data
        """
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            extracted_data = {}
            
            if job_id:
                extracted_data['job_id'] = job_id
            
            # Method 1: Extract from JSON in script tags
            json_data = self._extract_json_from_scripts(soup)
            if json_data:
                extracted_data.update(self._extract_from_json(json_data))
            
            # Method 2: Extract from HTML attributes and text content
            html_data = self._extract_from_html_elements(soup)
            extracted_data.update(html_data)
            
            # Method 3: Extract from meta tags and other sources
            meta_data = self._extract_from_meta_tags(soup)
            extracted_data.update(meta_data)
            
            # Method 4: Extract from data attributes
            data_attrs = self._extract_from_data_attributes(soup)
            extracted_data.update(data_attrs)
            
            # Method 5: Extract from HTML content and text
            html_content_data = self._extract_from_html_content(soup)
            extracted_data.update(html_content_data)
            
            # Method 6: Parse Nuxt data and resolve indices
            nuxt_data = self._parse_nuxt_data(html_content)
            nuxt_lookup = {}
            if nuxt_data:
                nuxt_lookup = self._build_nuxt_lookup(nuxt_data)
                # Resolve all extracted values that might be indices
                for key, value in extracted_data.items():
                    # Never resolve buyer_hire_rate_pct to avoid turning numbers like 100 into Nuxt indexes
                    if key == 'buyer_hire_rate_pct':
                        continue
                    # Don't resolve fields that were correctly extracted from targeted blocks
                    if key in ['client_hires', 'buyer_stats_hoursCount', 'client_reviews', 'client_rating', 'buyer_stats_totalJobsWithHires']:
                        continue
                    if value != "Not found":
                        resolved_value = self._resolve_nuxt_index(value, nuxt_lookup)
                        if resolved_value != value:
                            extracted_data[key] = resolved_value
            
            self._extract_missing_fields(html_content, extracted_data, nuxt_lookup)
            
            # Method 7.5: Targeted block extraction AFTER all Nuxt resolution is complete
            self._extract_targeted_block(html_content, extracted_data)
            
            # Method 7.6: Clean up any remaining random values for protected fields
            self._cleanup_protected_fields(extracted_data)
            
            # Method 8: Calculate hire rate percentage from resolved data
            if 'buyer_stats_totalJobsWithHires' in extracted_data and 'buyer_jobs_postedCount' in extracted_data:
                try:
                    # Extract numeric values, handling non-numeric strings
                    jobs_with_hires_str = str(extracted_data['buyer_stats_totalJobsWithHires']).strip()
                    total_jobs_posted_str = str(extracted_data['buyer_jobs_postedCount']).strip()
                    
                    # Only proceed if both values are numeric
                    if jobs_with_hires_str.replace('.', '').replace('-', '').isdigit() and total_jobs_posted_str.replace('.', '').replace('-', '').isdigit():
                        jobs_with_hires = int(float(jobs_with_hires_str))
                        total_jobs_posted = int(float(total_jobs_posted_str))
                        if total_jobs_posted > 0:
                            # If numerator exceeds denominator, clamp to 100
                            if jobs_with_hires >= total_jobs_posted:
                                rate_for_log = 100
                                extracted_data['buyer_hire_rate_pct'] = 100
                            else:
                                rate_for_log = round((jobs_with_hires / total_jobs_posted) * 100)
                                # Clamp any rounding anomalies
                                extracted_data['buyer_hire_rate_pct'] = min(100, max(0, rate_for_log))
                    else:
                        pass
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not calculate hire rate: {e}")

            # Final safeguard: if buyer_hire_rate_pct is present and > 100, cap at 100
            if 'buyer_hire_rate_pct' in extracted_data:
                try:
                    pct_val = int(float(str(extracted_data['buyer_hire_rate_pct']).strip()))
                    if pct_val > 100:
                        extracted_data['buyer_hire_rate_pct'] = 100
                except (ValueError, TypeError):
                    pass

            # Final safeguard: normalize client_total_spent (e.g., 19K -> 19000)
            if 'client_total_spent' in extracted_data and extracted_data['client_total_spent'] not in (None, "Not found"):
                extracted_data['client_total_spent'] = self._normalize_client_total_spent(
                    str(extracted_data['client_total_spent'])
                )
            
            # Ensure job type consistency: hourly jobs should have fixed_budget_amount = 0
            if 'type' in extracted_data and extracted_data['type'] == 'Hourly':
                extracted_data['fixed_budget_amount'] = '0'
            elif 'type' in extracted_data and extracted_data['type'] == 'Fixed':
                # Fixed jobs should not have hourly rates
                if 'hourly_min' in extracted_data:
                    extracted_data['hourly_min'] = '0'
                if 'hourly_max' in extracted_data:
                    extracted_data['hourly_max'] = '0'
            
            # Ensure all target fields are present with default values if missing
            for field in self.target_fields:
                if field not in extracted_data:
                    extracted_data[field] = ""
            
            return extracted_data
            
        except Exception as e:
            logger.error(f"Error extracting data from HTML: {str(e)}")
            return {}
    
    def _extract_json_from_scripts(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extract JSON data from script tags"""
        try:
            # Look for common patterns in script tags
            script_patterns = [
                r'window\.__NUXT__\s*=\s*({.*?});',
                r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
                r'window\.data\s*=\s*({.*?});',
                r'window\.job\s*=\s*({.*?});',
                r'window\.jobData\s*=\s*({.*?});',
                r'window\.__NUXT__\.data\s*=\s*({.*?});'
            ]
            
            scripts = soup.find_all('script', type='text/javascript')
            for script in scripts:
                if script.string:
                    content = script.string
                    for pattern in script_patterns:
                        matches = re.findall(pattern, content, re.DOTALL)
                        for match in matches:
                            try:
                                return json.loads(match)
                            except json.JSONDecodeError:
                                continue
            
            # Also look for JSON in script content without window assignment
            for script in scripts:
                if script.string:
                    content = script.string.strip()
                    if content.startswith('{') and content.endswith('}'):
                        try:
                            return json.loads(content)
                        except json.JSONDecodeError:
                            continue
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting JSON from scripts: {str(e)}")
            return None
    
    def _extract_from_json(self, json_data: Dict) -> Dict[str, Any]:
        """Extract target fields from JSON data"""
        extracted = {}
        
        def search_in_dict(data, path=""):
            """Recursively search for target fields in nested dictionary"""
            if isinstance(data, dict):
                for key, value in data.items():
                    current_path = f"{path}.{key}" if path else key
                    
                    # Check if this key matches any target field
                    for target_field in self.target_fields:
                        if key == target_field or current_path.endswith(f".{target_field}"):
                            extracted[target_field] = value
                    
                    # Recursively search nested dictionaries
                    if isinstance(value, dict):
                        search_in_dict(value, current_path)
                    elif isinstance(value, list):
                        for i, item in enumerate(value):
                            if isinstance(item, dict):
                                search_in_dict(item, f"{current_path}[{i}]")
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    if isinstance(item, dict):
                        search_in_dict(item, f"{path}[{i}]")
        
        search_in_dict(json_data)
        return extracted

    def _parse_nuxt_data(self, html_content):
        """Parse the __NUXT_DATA__ script tag to extract the data array"""
        # Look for the __NUXT_DATA__ script tag
        nuxt_pattern = r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>'
        match = re.search(nuxt_pattern, html_content, re.DOTALL)
        
        if not match:
            logger.warning("Could not find __NUXT_DATA__ script tag")
            return None
        
        try:
            # Parse the JSON data
            nuxt_data = json.loads(match.group(1))
            return nuxt_data
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse __NUXT_DATA__ JSON: {e}")
            return None

    def _build_nuxt_lookup(self, nuxt_data):
        """Build a lookup dictionary from the Nuxt data array"""
        lookup = {}
        
        if not nuxt_data or not isinstance(nuxt_data, list):
            logger.warning("Invalid Nuxt data format")
            return lookup
        
        # The Nuxt data is a flat array where each index corresponds to a value
        # We need to build the lookup from the entire array
        for i, value in enumerate(nuxt_data):
            lookup[i] = value
            if i < 200:  # Only log first 200 entries to avoid spam
                pass
        
        return lookup

    def _resolve_nuxt_index(self, value, nuxt_lookup):
        """Resolve a Nuxt index to its actual value"""
        # Only resolve if the value is a pure number (likely an index)
        # Don't resolve if it's already a meaningful value like a percentage
        if isinstance(value, (int, str)) and str(value).isdigit():
            index = int(value)
            # Only resolve if the index is within a reasonable range for Nuxt data
            # and the value looks like it could be an index (not a meaningful number)
            if 0 <= index < len(nuxt_lookup) and index in nuxt_lookup:
                resolved = nuxt_lookup[index]
                # Don't resolve if the resolved value looks like an IP address or other non-meaningful data
                if isinstance(resolved, str) and '.' in resolved and len(resolved.split('.')) == 4:
                    # This looks like an IP address, don't resolve
                    return value
                # Don't resolve if the resolved value is a complex object (dict/list)
                if isinstance(resolved, (dict, list)):
                    # This is a complex object, don't resolve
                    return value
                return resolved
        return value
    
    def _extract_from_html_elements(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract data from HTML elements"""
        extracted = {}
        
        # Extract title from title tag
        title_tag = soup.find('title')
        if title_tag:
            extracted['title'] = title_tag.get_text().strip()
        
        # Extract description from meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            extracted['description'] = meta_desc.get('content', '').strip()
        
        # Look for job-specific data in various HTML elements
        data_elements = soup.find_all(attrs={'data-test': True})
        for element in data_elements:
            data_test = element.get('data-test')
            if data_test in ['job-title', 'job-description', 'job-budget', 'job-duration']:
                text_content = element.get_text().strip()
                if text_content:
                    if data_test == 'job-title':
                        extracted['title'] = text_content
                    elif data_test == 'job-description':
                        extracted['description'] = text_content
        
        return extracted
    
    def _extract_from_meta_tags(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract data from meta tags"""
        extracted = {}
        
        # Look for job-related meta tags
        meta_tags = soup.find_all('meta')
        for meta in meta_tags:
            name = meta.get('name', '').lower()
            content = meta.get('content', '')
            
            if 'job' in name or 'title' in name:
                if 'title' in name:
                    extracted['title'] = content
            elif 'description' in name:
                extracted['description'] = content
        
        return extracted
    
    def _extract_from_data_attributes(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract data from data attributes"""
        extracted = {}
        
        # Look for elements with data attributes that might contain job data
        elements_with_data = soup.find_all(attrs=lambda x: x and isinstance(x, dict) and any(
            attr.startswith('data-') for attr in x.keys()
        ))
        
        for element in elements_with_data:
            for attr, value in element.attrs.items():
                if attr.startswith('data-'):
                    # Check if this data attribute might contain job information
                    if any(field in attr.lower() for field in ['job', 'title', 'description', 'budget', 'duration']):
                        # Try to extract meaningful data
                        if isinstance(value, str) and value.strip():
                            # Map common data attributes to our target fields
                            if 'title' in attr.lower():
                                extracted['title'] = value
                            elif 'description' in attr.lower():
                                extracted['description'] = value
        
        return extracted
    
    def _extract_from_html_content(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract data from HTML content and text"""
        extracted = {}
        
        # Extract title from title tag
        title_tag = soup.find('title')
        if title_tag:
            extracted['title'] = title_tag.get_text().strip()
        
        # Look for job description in various elements
        description_selectors = [
            'div[data-test="job-description"]',
            'div[data-test="description"]',
            'div[data-test="Description"]',  # Handle uppercase D
            '.job-description',
            '.description',
            'section[data-test="description"]',
            'section[data-test="Description"]'  # Handle uppercase D
        ]
        
        for selector in description_selectors:
            desc_element = soup.select_one(selector)
            if desc_element:
                # For the specific Description structure, look for the p tag inside
                if 'data-test="Description"' in selector:
                    p_tag = desc_element.find('p')
                    if p_tag:
                        desc_text = p_tag.get_text().strip()
                    else:
                        desc_text = desc_element.get_text().strip()
                else:
                    desc_text = desc_element.get_text().strip()
                
                # If the element is actually just the job type token, use it for type and skip as description
                lowered = desc_text.lower()
                if lowered in ('hourly', 'fixed', 'fixed-price', 'fixed price'):
                    extracted['type'] = 'Hourly' if 'hourly' in lowered else 'Fixed'
                    # extracted['type'] = desc_element.get_text().strip()
                    # Do not treat this token as description; continue searching
                    continue
                # Prefer substantive descriptions (avoid short tokens like "Hourly") and keep the longest
                if desc_text and (len(desc_text) >= 40 or '\n' in desc_text):
                    if 'description' not in extracted or len(str(extracted['description'])) < len(desc_text):
                        extracted['description'] = desc_text
                    break
        
        # Look for job details in various data-test attributes
        data_test_elements = soup.find_all(attrs={'data-test': True})
        for element in data_test_elements:
            data_test = element.get('data-test', '')
            text_content = element.get_text().strip()
            
            if text_content:
                if 'job-title' in data_test or 'title' in data_test:
                    extracted['title'] = text_content
                elif 'job-description' in data_test or 'description' in data_test or 'Description' in data_test:
                    # For Description with uppercase D, look for p tag inside
                    if data_test == 'Description':
                        p_tag = element.find('p')
                        if p_tag:
                            extracted['description'] = p_tag.get_text().strip()
                        else:
                            extracted['description'] = text_content
                    else:
                        extracted['description'] = text_content
                elif 'budget' in data_test:
                    # Try to extract budget information
                    if 'fixed' in text_content.lower():
                        extracted['type'] = 'Fixed'
                    elif 'hourly' in text_content.lower():
                        extracted['type'] = 'Hourly'
                elif 'duration' in data_test:
                    extracted['duration'] = text_content
                elif 'level' in data_test:
                    extracted['level'] = text_content
                elif 'skills' in data_test:
                    # Extract skills as a list
                    skills = [skill.strip() for skill in text_content.split(',') if skill.strip()]
                    if skills:
                        extracted['skills'] = skills
                elif 'deliverable' in data_test:
                    # Extract deliverables
                    if 'qualifications' not in extracted:
                        extracted['qualifications'] = []
                    extracted['qualifications'].append(text_content)
        
        # Look for specific client/buyer data using data-qa attributes
        data_qa_elements = soup.find_all(attrs={'data-qa': True})
        for element in data_qa_elements:
            data_qa = element.get('data-qa', '')
            text_content = element.get_text().strip()
            
            if text_content:
                if data_qa == 'client-hourly-rate':
                    # Extract hourly rate: "$23.45 /hr avg hourly rate paid"
                    rate_match = re.search(r'\$([\d.]+)', text_content)
                    if rate_match:
                        extracted['buyer_avgHourlyJobsRate_amount'] = rate_match.group(1)
                elif data_qa == 'client-job-posting-stats':
                    # Extract hire rate: "40% hire rate, 5 open jobs"
                    hire_rate_match = re.search(r'(\d+)% hire rate', text_content)
                    if hire_rate_match:
                        extracted['buyer_hire_rate_pct'] = hire_rate_match.group(1)
                elif data_qa == 'client-location':
                    # Extract location: "United States" and "Davenport"
                    if 'United States' in text_content:
                        extracted['client_country'] = 'United States'
                    # Look for city and time in the div content
                    city_div = element.find('div')
                    if city_div:
                        city_text = city_div.get_text().strip()
                        if city_text and city_text != 'United States':
                            # If the entire text looks like a time (e.g., "6:09" or "12:09 PM"), store as localTime only
                            if re.match(r'^\s*\d{1,2}:\d{2}(\s*[AP]M)?\s*$', city_text, re.IGNORECASE):
                                extracted['buyer_location_localTime'] = city_text.strip()
                                # Don't set city in this case
                                continue
                            # Handle cases where city and time are concatenated, possibly with stray letters like "Vs10:35 PM"
                            # Strategy 1: direct split by locating the time token anywhere in the string
                            time_token = re.search(r'(\d{1,2}:\d{2}\s*(?:[AP]M)?)', city_text, re.IGNORECASE)
                            if time_token:
                                city_part = city_text[:time_token.start()].strip()
                                time_part = time_token.group(1).strip()
                                if city_part:
                                    extracted['buyer_location_city'] = city_part
                                extracted['buyer_location_localTime'] = time_part
                            else:
                                # Strategy 2: pattern city + optional non-digits + time at end
                                time_match = re.search(r'^(.*?)(?:\D{0,4})?(\d{1,2}:\d{2}\s*(?:[AP]M)?)$', city_text, re.IGNORECASE)
                                if time_match:
                                    city_part = time_match.group(1).strip()
                                    time_part = time_match.group(2).strip()
                                    if city_part:
                                        extracted['buyer_location_city'] = city_part
                                    extracted['buyer_location_localTime'] = time_part
                                else:
                                    # Fallback to space splitting
                                    parts = city_text.split()
                                    if len(parts) >= 2:
                                        # Detect a time token anywhere in the remainder
                                        remainder = ' '.join(parts[1:])
                                        m = re.search(r'(\d{1,2}:\d{2}\s*(?:[AP]M)?)', remainder, re.IGNORECASE)
                                        if m:
                                            extracted['buyer_location_city'] = parts[0]
                                            extracted['buyer_location_localTime'] = m.group(1).strip()
                                        else:
                                            extracted['buyer_location_city'] = city_text
                                    else:
                                        # Single token: ensure it's not just a time before assigning as city
                                        if re.match(r'^\s*\d{1,2}:\d{2}(\s*[AP]M)?\s*$', city_text, re.IGNORECASE):
                                            extracted['buyer_location_localTime'] = city_text.strip()
                                        else:
                                            extracted['buyer_location_city'] = city_text
                elif data_qa == 'client-spend':
                    # Extract total spent: "$19K total spent"
                    spend_match = re.search(r'\$([\d.]+K?)', text_content)
                    if spend_match:
                        extracted['client_total_spent'] = self._normalize_client_total_spent(spend_match.group(1))
                elif data_qa == 'client-hires':
                    # Extract hires: "35 hires, 5 active"
                    hires_match = re.search(r'(\d+) hires', text_content)
                    if hires_match:
                        extracted['client_hires'] = hires_match.group(1)
                elif data_qa == 'client-hours':
                    # Extract hours: "441 hours"
                    hours_match = re.search(r'(\d+) hours', text_content)
                    if hours_match:
                        extracted['buyer_stats_hoursCount'] = hours_match.group(1)
                elif data_qa == 'client-contract-date':
                    # Extract contract date: "Member since Oct 26, 2022"
                    if 'Member since' in text_content:
                        date_match = re.search(r'Member since (.+)', text_content)
                        if date_match:
                            extracted['buyer_company_contractDate'] = date_match.group(1)
                elif data_qa in ('client-company-profile-size', 'client-company-profile'):
                    # Extract company size label from About the client block; prefer this DOM string over Nuxt indices
                    size_text = element.get_text().strip()
                    if size_text:
                        extracted['client_company_size'] = size_text
        
        # Look for payment verification status
        payment_verified_elements = soup.find_all(class_='payment-verified')
        if payment_verified_elements:
            extracted['payment_verified'] = True
        
        # Look for phone verification (if present)
        phone_verified_elements = soup.find_all(class_='phone-verified')
        if phone_verified_elements:
            extracted['phone_verified'] = True
        
        # Look for hourly rate ranges in specific HTML structure
        # Pattern: $10.00 - $25.00
        hourly_rate_elements = soup.find_all(attrs={'data-cy': 'clock-timelog'})
        for element in hourly_rate_elements:
            # Look for the rate structure in the parent element
            parent = element.find_parent()
            if parent:
                rate_text = parent.get_text()
                # Extract rates like "$10.00 - $25.00"
                rate_match = re.search(r'\$(\d+(?:\.\d{2})?)\s*-\s*\$(\d+(?:\.\d{2})?)', rate_text)
                if rate_match:
                    extracted['hourly_min'] = rate_match.group(1)
                    extracted['hourly_max'] = rate_match.group(2)
                    break
        
        # Look for category information in various formats
        category_elements = soup.find_all(attrs={'data-test': 'category'})
        for element in category_elements:
            text_content = element.get_text().strip()
            if text_content:
                extracted['category'] = text_content
        
        # Look for skills in various formats
        skills_elements = soup.find_all(attrs={'data-test': 'skills'})
        if skills_elements:
            skills_list = []
            for element in skills_elements:
                text_content = element.get_text().strip()
                if text_content:
                    skills_list.append(text_content)
            if skills_list:
                extracted['skills'] = skills_list
        
        # Look for skills in the specific HTML structure with air3-badge
        skills_badges = soup.find_all('a', class_='air3-badge')
        if skills_badges:
            skills_list = []
            for badge in skills_badges:
                # Get the text content from the line-clamp div
                line_clamp = badge.find('div', class_='air3-line-clamp')
                if line_clamp:
                    skill_text = line_clamp.get_text().strip()
                    if skill_text:
                        skills_list.append(skill_text)
            if skills_list:
                extracted['skills'] = skills_list
        
        # Also look for skills in skills-list containers
        skills_containers = soup.find_all('div', class_='skills-list')
        if skills_containers:
            skills_list = []
            for container in skills_containers:
                # Look for all badges within this container
                badges = container.find_all('a', class_='air3-badge')
                for badge in badges:
                    line_clamp = badge.find('div', class_='air3-line-clamp')
                    if line_clamp:
                        skill_text = line_clamp.get_text().strip()
                        if skill_text:
                            skills_list.append(skill_text)
            if skills_list:
                extracted['skills'] = skills_list
        
        # Look for questions
        questions_elements = soup.find_all(attrs={'data-test': 'questions'})
        if questions_elements:
            questions_list = []
            for element in questions_elements:
                text_content = element.get_text().strip()
                if text_content:
                    questions_list.append(text_content)
            if questions_list:
                extracted['questions'] = questions_list
        
        # Look for specific job information in the content
        # Extract deliverables
        deliverables = soup.find_all(attrs={'data-test': 'deliverable'})
        if deliverables:
            qual_list = []
            for del_item in deliverables:
                text = del_item.get_text().strip()
                if text:
                    qual_list.append(text)
            if qual_list:
                extracted['qualifications'] = qual_list
        
        # Look for job type information (prefer explicit signals, avoid defaulting)
        html_content = str(soup)
        if 'type' not in extracted:
            # If we captured hourly range earlier, we already set type; as a fallback, infer from other concrete signals
            if 'hourly_min' in extracted or 'hourly_max' in extracted:
                extracted['type'] = 'Hourly'
            elif 'fixed_budget_amount' in extracted:
                extracted['type'] = 'Fixed'
            else:
                # As a last resort, look for strong phrases
                text_lower = html_content.lower()
                if 'fixed price' in text_lower or 'fixed-price' in text_lower:
                    extracted['type'] = 'Fixed'
                elif '/hr' in text_lower or ' per hour' in text_lower:
                    extracted['type'] = 'Hourly'
        
        # Look for premium job indicators
        if 'premium' in html_content.lower():
            extracted['premium'] = True
        
        # Look for contract to hire indicators
        if 'contract to hire' in html_content.lower() or 'contract-to-hire' in html_content.lower():
            extracted['isContractToHire'] = True
        
        # Look for enterprise job indicators
        if 'enterprise' in html_content.lower():
            extracted['enterpriseJob'] = True
        
        # Look for job URL
        url_patterns = [
            r'href="(/jobs/[^"]*)"',
            r'href="(/freelance-jobs/[^"]*)"',
            r'data-test="job-url"[^>]*href="([^"]*)"',
            r'class="job-url"[^>]*href="([^"]*)"'
        ]
        
        for pattern in url_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            if matches:
                extracted['url'] = matches[0]
                break
        
        # Look for job ID in URL or data attributes
        job_id_patterns = [
            r'/jobs/(\d+)',
            r'/freelance-jobs/(\d+)',
            r'data-job-id="(\d+)"',
            r'data-test="job-id"[^>]*>(\d+)<'
        ]
        
        for pattern in job_id_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            if matches:
                extracted['job_id'] = matches[0]
                break
        
        # Look for skills in various formats
        skills_patterns = [
            r'data-test="skills"[^>]*>([^<]+)<',
            r'class="skills"[^>]*>([^<]+)<',
            r'<span[^>]*class="[^"]*skill[^"]*"[^>]*>([^<]+)</span>'
        ]
        
        for pattern in skills_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            if matches:
                skills_text = matches[0]
                skills = [skill.strip() for skill in skills_text.split(',') if skill.strip()]
                if skills:
                    extracted['skills'] = skills
                break
        
        # Look for budget information
        budget_patterns = [
            r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*USD',
            r'budget[^>]*>([^<]+)<'
        ]
        
        for pattern in budget_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            if matches:
                if 'fixed' in html_content.lower():
                    extracted['fixed_budget_amount'] = matches[0]
                elif 'hourly' in html_content.lower():
                    if 'hourly_min' not in extracted:
                        extracted['hourly_min'] = matches[0]
                    else:
                        extracted['hourly_max'] = matches[0]
                break
        
        # Look for duration information
        duration_patterns = [
            r'duration[^>]*>([^<]+)<',
            r'<span[^>]*class="[^"]*duration[^"]*"[^>]*>([^<]+)</span>'
        ]
        
        for pattern in duration_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            if matches:
                extracted['duration'] = matches[0].strip()
                break

        # Fallback: explicit duration phrases commonly used by Upwork UI
        if 'duration' not in extracted or not extracted['duration']:
            duration_phrase_pattern = (
                r'(More than 6 months|3 to 6 months|1 to 3 months|Less than 1 month)'
            )
            m = re.search(duration_phrase_pattern, html_content, re.IGNORECASE)
            if m:
                # Preserve original casing from the match
                extracted['duration'] = m.group(1)
        
        # Look for level information
        level_patterns = [
            r'level[^>]*>([^<]+)<',
            r'<span[^>]*class="[^"]*level[^"]*"[^>]*>([^<]+)</span>',
            r'(Entry|Intermediate|Expert|Advanced)',
            r'experience[^>]*level[^>]*>([^<]+)<',
            r'<div[^>]*class="[^"]*level[^"]*"[^>]*>([^<]+)</div>'
        ]
        
        for pattern in level_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            if matches:
                level_value = matches[0].strip()
                # Only use if it looks like a meaningful level, not CSS
                if level_value and not any(css_indicator in level_value for css_indicator in ['{', '}', ':', ';', '.', '#']):
                    extracted['level'] = level_value
                    break
        
        return extracted
    
    def _extract_missing_fields(self, html_content: str, extracted: Dict[str, Any], nuxt_lookup: Dict = None):
        """Enhanced method to extract missing fields using various patterns"""
        
        # Look for data in script tags with more patterns
        script_patterns = [
            r'window\.__NUXT__\s*=\s*({.*?});',
            r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
            r'window\.data\s*=\s*({.*?});',
            r'window\.job\s*=\s*({.*?});',
            r'window\.jobData\s*=\s*({.*?});',
            r'window\.__NUXT__\.data\s*=\s*({.*?});',
            r'window\.__NUXT__\.state\s*=\s*({.*?});',
            r'window\.__NUXT__\.payload\s*=\s*({.*?});'
        ]
        
        # Also look for Nuxt data in the HTML content directly
        nuxt_patterns = [
            r'"createdOn":(\d+)',
            r'"publishTime":(\d+)',
            r'"totalApplicants":(\d+)',
            r'"numberOfPositionsToHire":(\d+)',
            r'"requiredConnects":(\d+)',
            r'"score":(\d+(?:\.\d+)?)',
            r'"feedbackCount":(\d+)',
            r'"totalCharges":(\d+(?:\.\d+)?)',
            r'"activeAssignmentsCount":(\d+)',
            r'"hoursCount":(\d+(?:\.\d+)?)',
            r'"totalJobsWithHires":(\d+)',
            r'"invitationsSent":(\d+)',
            r'"totalHired":(\d+)',
            r'"totalInvitedToInterview":(\d+)',
            r'"unansweredInvites":(\d+)',
            r'"openCount":(\d+)',
            r'"postedCount":(\d+)',
            r'"title":"([^"]+)"',
            r'"description":"([^"]+)"',
            r'"category":"([^"]+)"',
            r'"name":"([^"]+)"',
            r'"currencyCode":"([^"]+)"',
            r'"country":"([^"]+)"',
            r'"industry":"([^"]+)"',
            r'"size":"([^"]+)"',
            r'"city":"([^"]+)"',
            r'"countryTimezone":"([^"]+)"',
            r'"contractorTier":"([^"]+)"',
            r'"label":"([^"]+)"',
            r'"isContractToHire":(true|false)',
            r'"isPaymentMethodVerified":(true|false)',
            r'"isPhoneVerified":(true|false)',
            r'"isPremium":(true|false)',
            r'"isEnterprise":(true|false)',
            # Additional patterns for location data
            r'"offsetFromUtcMillis":(\d+)',
            r'"countryTimezone":"([^"]+)"',
            r'"city":"([^"]+)"',
            r'"country":"([^"]+)"',
            r'"industry":"([^"]+)"',
            r'"size":"([^"]+)"',
            r'"contractDate":"([^"]+)"',
            # Look for specific Nuxt data patterns
            r'"offsetFromUtcMillis":(\d+),',
            r'"countryTimezone":(\d+),',
            r'"city":(\d+),',
            r'"country":(\d+),',
            r'"industry":(\d+),',
            r'"size":(\d+),',
            r'"isPhoneVerified":(\d+),',
            r'"isContractToHire":(\d+),',
            r'"questions":(\d+),',
            r'"durationIdV3":(\d+),',
            r'"durationLabel":(\d+),',
            # Additional patterns for missing fields
            r'"currencyCode":(\d+),',
            r'"lastBuyerActivity":(\d+),',
            # Category patterns
            r'"name":"([^"]+)"',
            r'"urlSlug":"([^"]+)"',
            # Look for category data in the format: {"name":84,"urlSlug":85},"Scripts & Utilities","scripts-utilities"
            r'"Scripts & Utilities"',
            r'"scripts-utilities"',
            r'"Web, Mobile & Software Dev"',
            r'"web-mobile-software-dev"',
            # Contractor tier pattern
            r'"contractorTier":(\d+)',
            # Hourly rate patterns
            r'\$(\d+(?:\.\d{2})?)',
            r'hourly[^>]*min[^>]*>(\d+(?:\.\d{2})?)<',
            r'hourly[^>]*max[^>]*>(\d+(?:\.\d{2})?)<'
        ]
        
        # Map Nuxt patterns to our target fields
        nuxt_field_mapping = {
            'createdOn': 'ts_create',
            'publishTime': 'ts_publish',
            'totalApplicants': 'applicants',
            'numberOfPositionsToHire': 'numberOfPositionsToHire',
            'requiredConnects': 'connects_required',
            'score': 'client_rating',
            'feedbackCount': 'client_reviews',
            'totalCharges': 'client_total_spent',
            'activeAssignmentsCount': 'buyer_stats_activeAssignmentsCount',
            'hoursCount': 'buyer_stats_hoursCount',
            'totalJobsWithHires': 'buyer_stats_totalJobsWithHires',
            'invitationsSent': 'clientActivity_invitationsSent',
            'totalHired': 'clientActivity_totalHired',
            'totalInvitedToInterview': 'clientActivity_totalInvitedToInterview',
            'unansweredInvites': 'clientActivity_unansweredInvites',
            'openCount': 'buyer_jobs_openCount',
            'postedCount': 'buyer_jobs_postedCount',
            'title': 'title',
            'description': 'description',
            'category': 'category',
            'name': 'category_name',
            'currencyCode': 'currency',
            'country': 'client_country',
            'industry': 'client_industry',
            'size': 'client_company_size',
            'city': 'buyer_location_city',
            'countryTimezone': 'buyer_location_countryTimezone',
            'offsetFromUtcMillis': 'buyer_location_offsetFromUtcMillis',
            'contractorTier': 'contractorTier',
            'label': 'level',
            'isContractToHire': 'isContractToHire',
            'isPaymentMethodVerified': 'payment_verified',
            'isPhoneVerified': 'phone_verified',
            'isPremium': 'premium',
            'isEnterprise': 'enterpriseJob',
            'contractDate': 'buyer_company_contractDate',
            # Additional mappings
            'name': 'category_name',
            'urlSlug': 'category_urlSlug',
            'industry': 'client_industry',
            'size': 'client_company_size',
            'isPhoneVerified': 'phone_verified',
            'isContractToHire': 'isContractToHire',
            'lastBuyerActivity': 'lastBuyerActivity'
        }
        
        # Extract Nuxt data using patterns
        for pattern in nuxt_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            if matches:
                # Find which field this pattern corresponds to
                for nuxt_field, target_field in nuxt_field_mapping.items():
                    if nuxt_field in pattern:
                        # Only set if field is truly missing or has invalid value
                        # For numeric fields, also check if current value is not a valid number
                        should_set_value = (
                            target_field not in extracted or 
                            extracted[target_field] == "Not found" or 
                            extracted[target_field] is None or 
                            extracted[target_field] == ""
                        )
                        
                        # For specific numeric fields, also check if current value is not a valid number
                        if target_field in ['buyer_stats_hoursCount', 'buyer_stats_totalJobsWithHires', 'client_hires', 'client_reviews', 'client_rating', 'buyer_hire_rate_pct']:
                            if target_field in extracted and extracted[target_field] != "Not found" and extracted[target_field] is not None and extracted[target_field] != "":
                                try:
                                    # If current value is a valid number, don't overwrite it
                                    float(extracted[target_field])
                                    should_set_value = False
                                except (ValueError, TypeError):
                                    # Current value is not a valid number, allow overwriting
                                    should_set_value = True
                        
                        if should_set_value:
                            value = matches[0].strip()
                            if value and self._is_valid_value(value):
                                # Convert boolean strings to actual booleans
                                if value.lower() in ['true', 'false']:
                                    extracted[target_field] = value.lower() == 'true'
                                else:
                                    # Normalize client_total_spent if needed
                                    if target_field == 'client_total_spent':
                                        extracted[target_field] = self._normalize_client_total_spent(value)
                                    else:
                                        extracted[target_field] = value
                        else:
                            # Field already has a value - check if we should skip overwriting it
                            if target_field == 'buyer_hire_rate_pct':
                                pass  # Skip hire rate from Nuxt
                            elif target_field in ['client_hires', 'buyer_stats_hoursCount', 'client_reviews', 'client_rating', 'buyer_stats_totalJobsWithHires']:
                                pass  # Skip targeted block fields from Nuxt
                            else:
                                pass
                        break
        
        # Search for location data via Nuxt index mapping present in HTML
        # Example pattern: {"offsetFromUtcMillis":139,"countryTimezone":140,"city":141,"country":142}
        loc_map_pattern = r'\{"offsetFromUtcMillis":(\d+),"countryTimezone":(\d+),"city":(\d+),"country":(\d+)\}'
        loc_map_matches = re.findall(loc_map_pattern, html_content)
        if loc_map_matches:
            try:
                off_idx, tz_idx, city_idx, country_idx = [int(x) for x in loc_map_matches[0]]
                if nuxt_lookup:
                    if off_idx in nuxt_lookup:
                        extracted['buyer_location_offsetFromUtcMillis'] = nuxt_lookup[off_idx]
                    if tz_idx in nuxt_lookup:
                        extracted['buyer_location_countryTimezone'] = nuxt_lookup[tz_idx]
                    if city_idx in nuxt_lookup:
                        city_candidate = nuxt_lookup[city_idx]
                        if not (isinstance(city_candidate, str) and re.match(r'^\s*\d{1,2}:\d{2}(\s*[AP]M)?\s*$', city_candidate, re.IGNORECASE)):
                            extracted['buyer_location_city'] = city_candidate
                    if country_idx in nuxt_lookup:
                        extracted['client_country'] = nuxt_lookup[country_idx]
            except Exception:
                pass

        # Fallback: heuristic based on proximity (kept for legacy pages)
        if nuxt_lookup and 'buyer_location_countryTimezone' not in extracted:
            for idx, value in nuxt_lookup.items():
                # Detect likely offset millis values by numeric magnitude (~hours in ms)
                if isinstance(value, int) and 1000 * 60 * 30 <= abs(value) <= 1000 * 60 * 60 * 24:
                    extracted['buyer_location_offsetFromUtcMillis'] = value
                    if idx + 1 in nuxt_lookup and 'buyer_location_countryTimezone' not in extracted:
                        extracted['buyer_location_countryTimezone'] = nuxt_lookup[idx + 1]
                    if idx + 2 in nuxt_lookup and 'buyer_location_city' not in extracted:
                        city_candidate = nuxt_lookup[idx + 2]
                        if not (isinstance(city_candidate, str) and re.match(r'^\s*\d{1,2}:\d{2}(\s*[AP]M)?\s*$', city_candidate, re.IGNORECASE)):
                            extracted['buyer_location_city'] = city_candidate
                    if idx + 3 in nuxt_lookup and 'client_country' not in extracted:
                        extracted['client_country'] = nuxt_lookup[idx + 3]
                    break
        
        
        # Pattern: {"industry":13,"size":13}
        nuxt_industry_pattern = r'\{"industry":(\d+),"size":(\d+)\}'
        industry_matches = re.findall(nuxt_industry_pattern, html_content)
        if industry_matches:
            industry_idx, size_idx = industry_matches[0]
            # Convert string indices to integers
            industry_idx = int(industry_idx)
            size_idx = int(size_idx)
            # Always resolve these indices to actual values if we have Nuxt lookup
            if nuxt_lookup and industry_idx in nuxt_lookup:
                extracted['client_industry'] = nuxt_lookup[industry_idx]
            if nuxt_lookup and size_idx in nuxt_lookup:
                if 'client_company_size' not in extracted or extracted['client_company_size'] == "Not found":
                    extracted['client_company_size'] = nuxt_lookup[size_idx]
        
        # Pattern: "currencyCode":91},0,"USD"
        currency_pattern = r'"currencyCode":(\d+)\},[^,]*,"([^"]+)"'
        currency_matches = re.findall(currency_pattern, html_content)
        if currency_matches:
            currency_idx, currency_value = currency_matches[0]
            # Always resolve the currency index to actual value if we have Nuxt lookup
            if nuxt_lookup and currency_idx in nuxt_lookup:
                extracted['currency'] = nuxt_lookup[currency_idx]
            else:
                # Fallback to the literal value found after the pattern
                extracted['currency'] = currency_value
        
        # Look for category and category group data
        # Pattern: {"name":84,"urlSlug":85},"Scripts & Utilities","scripts-utilities"
        category_pattern = r'\{"name":(\d+),"urlSlug":(\d+)\},"([^"]+)","([^"]+)"'
        category_matches = re.findall(category_pattern, html_content)
        if category_matches:
            name_id, url_slug_id, category_name, category_url_slug = category_matches[0]
            # Always override category fields with the correct values from the pattern
            extracted['category'] = category_name
            extracted['category_name'] = category_name
            extracted['category_urlSlug'] = category_url_slug
        
        # Look for category group data
        # Pattern: {"name":87,"urlSlug":88},"Web, Mobile & Software Dev","web-mobile-software-dev"
        category_group_pattern = r'\{"name":(\d+),"urlSlug":(\d+)\},"([^"]+)","([^"]+)"'
        category_group_matches = re.findall(category_group_pattern, html_content)
        if category_group_matches:
            # Get the second match (category group)
            if len(category_group_matches) > 1:
                name_id, url_slug_id, category_group_name, category_group_url_slug = category_group_matches[1]
                if 'categoryGroup_name' not in extracted or extracted['categoryGroup_name'] == "Not found":
                    extracted['categoryGroup_name'] = category_group_name
                if 'categoryGroup_urlSlug' not in extracted or extracted['categoryGroup_urlSlug'] == "Not found":
                    extracted['categoryGroup_urlSlug'] = category_group_url_slug

        
        for pattern in script_patterns:
            matches = re.findall(pattern, html_content, re.DOTALL)
            for match in matches:
                try:
                    json_data = json.loads(match)
                    json_extracted = self._extract_from_json(json_data)
                    extracted.update(json_extracted)
                except json.JSONDecodeError:
                    continue
        
        # Resolve indices to actual values using Nuxt lookup
        if nuxt_lookup:
            for key, value in extracted.items():
                if value != "Not found":
                    resolved_value = self._resolve_nuxt_index(value, nuxt_lookup)
                    if resolved_value != value:
                        extracted[key] = resolved_value
    
    def _is_valid_value(self, value: str) -> bool:
        """Check if extracted value is valid and not noise"""
        if not value or len(value) < 1:
            return False
        
        # Filter out very long values that are likely noise
        if len(value) > 500:
            return False
        
        # Filter out values that contain too much HTML/JSON noise
        if 'User Agreement' in value or 'Terms of Use' in value:
            return False
        
        # Filter out CSS/JS noise
        if value.startswith('li.') or value.startswith('.ma-scope') or value.startswith('@media'):
            return False
        
        return True

    def _extract_targeted_block(self, html_content: str, extracted: Dict[str, Any]):
        """Extract values from targeted Nuxt mapping block - runs AFTER all Nuxt resolution"""
        # Targeted extraction for buyer_stats_hoursCount from Nuxt mapping with trailing values
        # Example: {"totalAssignments":130,"activeAssignmentsCount":102,"hoursCount":131,"feedbackCount":132,"score":133,"totalJobsWithHires":134,"totalCharges":135},108,3582.33,73,4.35,92,
        hours_block_pattern = (
            r'\{"totalAssignments":(\d+),"activeAssignmentsCount":(\d+),"hoursCount":(\d+),"feedbackCount":(\d+),"score":(\d+),"totalJobsWithHires":(\d+),"totalCharges":(\d+)\}'
            r'\s*,\s*(\d+)\s*,\s*([\d\.]+)\s*,\s*(\d+)\s*,\s*([\d\.]+)\s*,\s*(\d+)'  # captures: totalAssignmentsVal, hoursVal, feedbackVal, scoreVal, totalJobsWithHiresVal
        )
        hours_block_match = re.search(hours_block_pattern, html_content)
        if hours_block_match:
            try:
                total_assignments_str = hours_block_match.group(8)
                hours_val_str = hours_block_match.group(9)  # The 2nd trailing value corresponds to hours
                feedback_count_str = hours_block_match.group(10)
                score_str = hours_block_match.group(11)
                total_jobs_with_hires_str = hours_block_match.group(12)

                # Normalize and assign - these values take precedence over any previous extraction
                # client_hires: use totalAssignments as total hires
                extracted['client_hires'] = str(int(float(total_assignments_str)))

                hours_val_num = int(float(hours_val_str))
                extracted['buyer_stats_hoursCount'] = str(hours_val_num)

                extracted['client_reviews'] = str(int(float(feedback_count_str)))

                # Keep rating with potential decimal
                try:
                    extracted['client_rating'] = str(float(score_str))
                except Exception:
                    extracted['client_rating'] = score_str

                extracted['buyer_stats_totalJobsWithHires'] = str(int(float(total_jobs_with_hires_str)))

            except Exception:
                pass

    def _cleanup_protected_fields(self, extracted: Dict[str, Any]):
        """Clean up random values for fields that should only have specific valid values"""
        protected_fields = {
            'buyer_stats_hoursCount': self._is_valid_hours_count,
            'client_hires': self._is_valid_hires_count,
            'buyer_stats_totalJobsWithHires': self._is_valid_jobs_with_hires,
            'client_reviews': self._is_valid_reviews_count,
            'client_rating': self._is_valid_rating
        }
        
        for field, validator in protected_fields.items():
            if field in extracted:
                value = extracted[field]
                if not validator(value):
                    extracted[field] = "0"  # Set to 0 instead of random values

    def _is_valid_hours_count(self, value: str) -> bool:
        """Check if value is a valid hours count (numeric, reasonable range)"""
        try:
            num = float(str(value))
            return 0 <= num <= 1000000  # Reasonable range for hours
        except (ValueError, TypeError):
            return False

    def _is_valid_hires_count(self, value: str) -> bool:
        """Check if value is a valid hires count (numeric, reasonable range)"""
        try:
            num = int(float(str(value)))
            return 0 <= num <= 10000  # Reasonable range for hires
        except (ValueError, TypeError):
            return False

    def _is_valid_jobs_with_hires(self, value: str) -> bool:
        """Check if value is a valid jobs with hires count (numeric, reasonable range)"""
        try:
            num = int(float(str(value)))
            return 0 <= num <= 10000  # Reasonable range for jobs
        except (ValueError, TypeError):
            return False

    def _is_valid_reviews_count(self, value: str) -> bool:
        """Check if value is a valid reviews count (numeric, reasonable range)"""
        try:
            num = int(float(str(value)))
            return 0 <= num <= 10000  # Reasonable range for reviews
        except (ValueError, TypeError):
            return False

    def _is_valid_rating(self, value: str) -> bool:
        """Check if value is a valid rating (numeric between 0-5)"""
        try:
            num = float(str(value))
            return 0 <= num <= 5.0  # Valid rating range
        except (ValueError, TypeError):
            return False

    def _normalize_client_total_spent(self, value: str) -> str:
        """Normalize client_total_spent values like '19K' to '19000'.

        - Accepts numbers with optional '$' and commas, optional trailing K/k.
        - If 'K' present, multiplies numeric by 1000.
        - Returns a numeric string without commas or currency symbols.
        - If parsing fails, returns the original value unchanged.
        """
        try:
            if value is None:
                return value
            text = str(value).strip()
            # Remove currency symbol and commas
            text = text.replace('$', '').replace(',', '').strip()
            m = re.match(r'^([\d]+(?:\.\d+)?)([Kk])?$', text)
            if not m:
                return value
            number_part = float(m.group(1))
            has_k = m.group(2) is not None
            normalized = number_part * 1000 if has_k else number_part
            # Output as integer string if it is effectively an integer
            if abs(normalized - int(normalized)) < 1e-9:
                return str(int(normalized))
            return str(normalized)
        except Exception:
            return value


# Convenience function for easy import and use
def extract_job_attributes(html_content: str, job_id: str = None) -> Dict[str, Any]:
    """
    Extract job attributes from HTML content string
    
    Args:
        html_content: HTML content as string
        job_id: Optional job ID to include in results
        
    Returns:
        Dictionary containing extracted job attributes
    """
    extractor = JobAttrExtractor()
    return extractor.extract_from_html(html_content, job_id)
