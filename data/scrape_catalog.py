import re

import requests
from bs4 import BeautifulSoup
import json


# Function to parse the prerequisite string into structured JSON
def parse_prerequisites(prereq_str):
    if not prereq_str or prereq_str.lower() == 'none':
        return None
    
    def parse_expr(expr):
        expr = expr.strip()
        if not expr:
            return None
        
        # Handle parentheses
        if expr.startswith('(') and expr.endswith(')'):
            return parse_expr(expr[1:-1])
        
        # Split on ' and ' (but not inside parentheses)
        if ' and ' in expr:
            parts = split_on_operator(expr, ' and ')
            return {
                "type": "and",
                "operands": [parse_expr(p) for p in parts]
            }
        
        # Split on ' or ' (but not inside parentheses)
        if ' or ' in expr:
            parts = split_on_operator(expr, ' or ')
            return {
                "type": "or",
                "operands": [parse_expr(p) for p in parts]
            }
        
        # Base case: single course (updated to handle concurrent note)
        # match = re.match(r'([A-Z]{4}\s*\d{3})\s*\[Min Grade:\s*([A-Z0-9\-]+)\]\s*(\(Can be taken Concurrently\))?', expr)
        match = re.match(r'([A-Z]{2,}\s*\d{3})\s*\[Min Grade:\s*([A-Z\-]+)\]\s*(\(Can be taken Concurrently\))?', expr)

        if match:
            course = match.group(1).replace(' ', '')
            grade = match.group(2)
            concurrent = bool(match.group(3))  # True if the note is present
            return {
                "type": "course",
                "course": course,
                "min_grade": grade,
                "concurrent": concurrent
            }
        
        # Fallback (if parsing fails)
        return {"type": "unknown", "raw": expr}
    
    def split_on_operator(expr, op):
        # Split on operator, respecting parentheses
        parts = []
        level = 0
        current = ""
        i = 0
        while i < len(expr):
            if expr[i] == '(':
                level += 1
            elif expr[i] == ')':
                level -= 1
            elif level == 0 and expr[i:i+len(op)] == op:
                parts.append(current.strip())
                current = ""
                i += len(op) - 1
            else:
                current += expr[i]
            i += 1
        if current.strip():
            parts.append(current.strip())
        return parts
    
    return parse_expr(prereq_str)

# Iterate through the CSV file and scrape course data for each program
with open("./data/course_descriptions.csv", "r") as f:
    lines = f.readlines()  

# Remove empty lines
lines = [line.strip() for line in lines if line.strip()]  

for line in lines[1:]:  # Skip header
    print(line)
    course_structure = line.split(',')[0]
    program_type = line.split(',')[1]
    program_code = line.split(',')[2]

    # The URL we want to scrape
    url = f"https://catalog.drexel.edu/coursedescriptions/{course_structure}/{program_type}/{program_code}/"

    # Send an HTTP request to the URL
    response = requests.get(url)

    # Check if the request was successful (Status Code 200)
    if response.status_code == 200:
        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        

        courses = soup.find_all('div', class_='courseblock')
        
        all_courses = {}
        
        print(f"Found {len(courses)} courses:\n")

        
        for course in courses:
            # Extract course code and title
            soup = BeautifulSoup(str(course), 'html.parser')
            title_elem = soup.find('p', class_='courseblocktitle')
            spans = title_elem.find_all('span', class_='cdspacing')
            course_title = spans[1].get_text(strip=True).replace('\xa0', '')
            credits_match = re.search(r"(\d+\.?\d*(?:-\d+\.?\d*)?)\s*<span class=\"cdspacing\">Credits", str(title_elem))
            credits = credits_match.group(1) if credits_match else "N/A"

            # Extract course code
            course_code_string = spans[0].get_text(strip=True).replace('\xa0', '')
            course_code_parts = course_code_string.split()
            course_code = course_code_parts[0]

            # Writing Intensive 
            writing_intensive = '[WI]' in course_code_parts


            # Extract description
            description = soup.find('p', class_='courseblockdesc').get_text(strip=True)
            description = re.sub(r'[^\x00-\x7F]+', '', description)

            # Extract metadata (College, Repeat Status, Prerequisites)
            text = soup.get_text()
            lines = [line.strip() for line in text.split('\n') if line.strip()]

            # Initialize variables
            prereq_str = None
            coreq_str = None


            course_data = {
                'code': course_code,
                'title': course_title,
                'credits': credits,
                'description': description,
                'prerequisites': None,
                'corequisites': None,
                'restrictions': None,
                'writing_intensive': writing_intensive

            }

            
            # Parse key-value pairs
            for line in lines:
                if line.startswith('College/Department:'):
                    course_data['college'] = line.replace('College/Department:', '').strip()
                elif line.startswith('Repeat Status:'):
                    course_data['repeat_status'] = line.replace('Repeat Status:', '').strip()
                elif line.startswith('Prerequisites:'):
                    prereq_str = line.replace('Prerequisites:', '').strip()
                elif line.startswith('Corequisite:'):  
                    coreq_str = line.replace('Corequisite:', '').strip()

            # Update course_data
            course_data['prerequisites'] = parse_prerequisites(prereq_str)
            course_data['corequisites'] = parse_prerequisites(coreq_str)

            all_courses[course_code] = course_data

            # print(course_data)

        # Write all course data to a JSON file
        file_name = f"{course_structure}_{program_type}_{program_code}_courses.json"
        with open(f"./data/scraped_data/{file_name}", 'w') as f:
            json.dump(all_courses, f, indent=4)

        print(f"Course data saved to {file_name}\n")

    else:
        print(f"Failed to retrieve the page. Status code: {response.status_code}")

