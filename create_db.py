import json
from langchain_neo4j import Neo4jVector
from langchain_openai import OpenAIEmbeddings # or your preferred provider
from langchain_core.documents import Document
import os
from dotenv import load_dotenv

load_dotenv("sk.env")

# Load environment variables for Neo4j connection
neo4j_uri = os.environ["NEO4J_URI"]
neo4j_username = os.environ["NEO4J_USERNAME"]
neo4j_password = os.environ["NEO4J_PASSWORD"]
neo4j_database = os.environ["NEO4J_DATABASE"]

# Path to data files
data_dir = "data/scraped_data"

# Load ALL course data into a single dict (to handle cross-file prerequisites/corequisites)
all_courses = {}
for filename in os.listdir(data_dir):
    if filename.endswith(".json"):
        with open(os.path.join(data_dir, filename), 'r') as f:
            print(f"Loading courses from {filename}...")
            courses_data = json.load(f)
            all_courses.update(courses_data)

# Convert ALL courses into LangChain Documents
documents = []
for code, details in all_courses.items():

    # if code == "CS570":

    #     print("Code:", code)
    #     print("Title:", details['title'])
    #     print("Description:", details['description'][:100])  # Print first 100 chars of description for verification
    #     print("Prerequisites:", details['prerequisites'])
    #     print("Corequisites:", details['corequisites'])
    #     print("Credits:", details['credits'])
    #     print("College:", details['college'])
    #     print("Repeat Status:", details['repeat_status'])
    #     print("Writing Intensive:", details['writing_intensive'])
    #     print("Restrictions:", details.get('restrictions'))
    #     print("-----\n")
    doc = Document(
        page_content=details['description'],
        metadata={
            "id": code,
            "title": details['title'],
            "credits": details['credits'],
            "college": details['college'],
            "repeat_status": details['repeat_status'],
            "writing_intensive": details['writing_intensive'],
            "prerequisites": json.dumps(details.get('prerequisites')) if details.get('prerequisites') else None,  
            "corequisites": json.dumps(details.get('corequisites')) if details.get('corequisites') else None,    
            "restrictions": json.dumps(details.get('restrictions')) if details.get('restrictions') else None

        }
    )

    documents.append(doc)

    # if code == "CS570":
    #     print("Sample Document for CS570:")
    #     print("Metadata:", doc.metadata)
    #     print("Content:", doc.page_content[:200])  # Print first 200 chars of content for verification
    #     print("-----\n")


# Ingest ALL documents into Neo4j at once (creates Course nodes)
vector_db = Neo4jVector.from_documents(
    documents,
    embedding=OpenAIEmbeddings(),
    url=neo4j_uri,
    username=neo4j_username,
    password=neo4j_password,
    index_name="course_descriptions",
    node_label="Course",
    text_node_property="description",
    database=neo4j_database
)

# print("Ingestion complete. Vector index established for course descriptions.")

# # Run this directly — if it returns nothing, id is the problem
# print(vector_db.query("MATCH (c:Course) WHERE c.id = 'CS570' RETURN c.id"))

# # Neo4j sometimes requires backticks for reserved words
# print(vector_db.query("MATCH (c:Course) WHERE c.`id` = 'CS570' RETURN c.`id`"))

# Create college relationships
vector_db.query("""
MATCH (c:Course)
MERGE (col:College {name: c.college})
MERGE (c)-[:OFFERED_BY]->(col)
""")

# Helper function to extract course codes from prerequisite/corequisite tree
def extract_req_courses(req_obj):
    """Returns set of (course_code, min_grade, concurrent) tuples"""
    if not req_obj:
        return set()
    if req_obj.get('type') == 'course':
        return {(
            req_obj.get('course'),
            req_obj.get('min_grade'),       # e.g. 'C', 'B', None
            req_obj.get('concurrent', False)
        )}
    elif req_obj.get('type') in ['and', 'or']:
        courses = set()
        for operand in req_obj.get('operands', []):
            courses.update(extract_req_courses(operand))
        return courses
    return set()

# Create prerequisite and corequisite relationships
for code, details in all_courses.items():
    # Handle prerequisites
    prereq_obj = details.get('prerequisites')
    if prereq_obj:
        prereq_courses = extract_req_courses(prereq_obj)
        for prereq_code, min_grade, concurrent in prereq_courses:  # unpack tuple
            if prereq_code in all_courses:
                rel_type = "COREQUISITE_FOR" if concurrent else "PREREQUISITE_FOR"
                min_grade_value = f"'{min_grade}'" if min_grade else "null"
                vector_db.query(f"""
                MATCH (p:Course {{id: '{prereq_code}'}}), (c:Course {{id: '{code}'}})
                MERGE (p)-[r:{rel_type}]->(c)
                SET r.min_grade = {min_grade_value},
                    r.concurrent = {str(concurrent).lower()}
                """)
                print(f"Linked {prereq_code} -{rel_type}-> {code} (min_grade={min_grade})")

    # Handle corequisites
    coreq_obj = details.get('corequisites')
    if coreq_obj:
        coreq_courses = extract_req_courses(coreq_obj)
        for coreq_code, min_grade, concurrent in coreq_courses:  # unpack tuple
            if coreq_code in all_courses:
                min_grade_value = f"'{min_grade}'" if min_grade else "null"
                vector_db.query(f"""
                MATCH (p:Course {{id: '{coreq_code}'}}), (c:Course {{id: '{code}'}})
                MERGE (p)-[r:COREQUISITE_FOR]->(c)
                SET r.min_grade = {min_grade_value},
                    r.concurrent = {str(concurrent).lower()}
                """)
                print(f"Linked {coreq_code} -COREQUISITE_FOR-> {code} (min_grade={min_grade})")

print("Ingestion complete. Vector index, college relationships, prerequisite relationships, and corequisite relationships established.")