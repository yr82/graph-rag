# Constants and configuration for the application

# Imports
import os

from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate, ChatPromptTemplate
from langchain_openai import ChatOpenAI

from pydantic import BaseModel, Field
from typing import Literal

from dotenv import load_dotenv

# Load environment variables
load_dotenv("sk.env")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Route a user query to the most relevant datasource.
class RouteQuery(BaseModel):
    datasource: Literal["vector_search", "graph_query", "both"] = Field(
        description=(
            "Given a user question, choose to route it to vector search "
            "for semantic/exploratory questions, or graph query for "
            "structural questions about prerequisites, corequisites, or relationships." 
            "If the question is ambiguous, you can choose 'both' to route to both."
        )
    )

# Function to format retrieved documents for display in the Streamlit app
def format_docs(docs):
    
    for doc in docs:
        print(f"Document metadata: {doc.metadata}")
        print(f"Document content: {doc.page_content[:200]}...")  # Print first 200 chars for brevity


    return "\n\n".join(
        f"**{d.metadata['title']} ({d.metadata['id']})**\n{d.page_content}"
        for d in docs
    )

# Initialize the LLM 
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# Retrieval query for Neo4j vector search (used by Neo4jVector retriever)
semantic_retrieval_query = """
    RETURN
        node.description AS text,
        score,
        {
            id:                node.`id`,
            title:             node.title,
            credits:           node.credits,
            college:           node.college,
            repeat_status:     node.repeat_status,
            writing_intensive: node.writing_intensive
        } AS metadata
    """

# Prompt for synthesizing vector search results
vector_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful university course advisor. Use the following course descriptions to answer the question.\n\nCourses:\n{context}"),
    ("human", "{question}"),
])

# Few-shot examples to fix LLM Cypher generation (used by GraphQAChain)
few_shot_examples = [
    {
        "question": "What are the prerequisites for CS510?",
        "query": (
            "MATCH (p:Course)-[:PREREQUISITE_FOR]->(c:Course {{id: 'CS510'}}) "
            "RETURN p.id AS prerequisite_code, p.title AS prerequisite_title, c.id AS course_id"
        ),
    },
    {
        "question": "What is the repeat status of CS510?",
        "query": (
            "MATCH (c:Course {{id: 'CS510'}}) "
            "RETURN c.repeat_status AS repeat_status, c.id AS course_id"
        ),
    },
    {
        "question": "What is the title of CS401?",
        "query": (
            "MATCH (c:Course {{id: 'CS401'}}) "
            "RETURN c.title AS title, c.id AS course_id"
        ),
    },
    {
        "question": "How many credits is MATH201?",
        "query": (
            "MATCH (c:Course {{id: 'MATH201'}}) "
            "RETURN c.credits AS credits, c.id AS course_id"
        ),
    },
    {
        "question": "Is CS310 writing intensive?",
        "query": (
            "MATCH (c:Course {{id: 'CS310'}}) "
            "RETURN c.writing_intensive AS writing_intensive, c.id AS course_id"
        ),
    },
    {
        "question": "What college offers CS510?",
        "query": (
            "MATCH (c:Course {{id: 'CS510'}})-[:OFFERED_BY]->(col:College) "
            "RETURN col.name AS college, c.id AS course_id"
        ),
    },
    {
        "question": "What courses require CS101 as a prerequisite?",
        "query": (
            "MATCH (c:Course {{id: 'CS101'}})-[:PREREQUISITE_FOR]->(downstream:Course) "
            "RETURN downstream.id AS course_code, downstream.title AS course_title, c.id AS course_id"
        ),
    },
    {
        "question": "What are the corequisites for CS310?",
        "query": (
            "MATCH (co:Course)-[:COREQUISITE_FOR]->(c:Course {{id: 'CS310'}}) "
            "RETURN co.id AS corequisite_code, co.title AS corequisite_title, c.id AS course_id"
        ),
    },
    {
        "question": "What are the prerequisites and repeat status for CS510?",
        "query": (
            "MATCH (c:Course {{id: 'CS510'}}) "
            "OPTIONAL MATCH (p:Course)-[:PREREQUISITE_FOR]->(c) "
            "RETURN c.repeat_status AS repeat_status, "
            "collect(p.id) AS prerequisite_codes, "
            "collect(p.title) AS prerequisite_titles, c.id AS course_id"
        ),
    },
    {
        "question": "What courses does the College of Computing and Informatics offer?",
        "query": (
            "MATCH (c:Course)-[:OFFERED_BY]->(col:College {{name: 'College of Computing and Informatics'}}) "
            "RETURN c.id AS course_id, c.title AS course_title"
        ),
    },

        {
        "question": "What are the prerequisites for CS613 and their minimum grades?",
        "query": (
            "MATCH (p:Course)-[r:PREREQUISITE_FOR]->(c:Course {{id: 'CS613'}}) "
            "RETURN p.id AS prerequisite_code, p.title AS prerequisite_title, "
            "r.min_grade AS min_grade, c.id AS course_id"
        ),
    },

    {
        "question": "Find the computer science prerequisites for CS613 and the minimum grade for them",
        "query": (
            "MATCH (p:Course)-[r:PREREQUISITE_FOR]->(c:Course {{id: 'CS613'}}) "
            "WHERE p.id STARTS WITH 'CS' "
            "RETURN p.id AS prerequisite_code, p.title AS prerequisite_title, "
            "r.min_grade AS min_grade, c.id AS course_id"
        ),
    },
    {
        "question": "What prerequisites for CS613 require a minimum grade of B or higher?",
        "query": (
            "MATCH (p:Course)-[r:PREREQUISITE_FOR]->(c:Course {{id: 'CS613'}}) "
            "WHERE r.min_grade IN ['A', 'B'] "
            "RETURN p.id AS prerequisite_code, p.title AS prerequisite_title, "
            "r.min_grade AS min_grade, c.id AS course_id"
        ),
    }
]

# Prompts for Cypher generation with few-shot examples and explicit schema/rules
few_shot_example_prompt = PromptTemplate.from_template(
    "Question: {question}\nCypher: {query}"
)

cypher_prompt = FewShotPromptTemplate(
    examples=few_shot_examples,
    example_prompt=few_shot_example_prompt,
    prefix="""You are a Neo4j Cypher expert for a university course database.
Write a Cypher query that answers the question using ONLY the schema and rules below.

Schema:
{schema}

RULES — non-negotiable:
1. ALWAYS match Course nodes using the `id` property (the course code).
   RIGHT:  MATCH (c:Course {{id: 'CS510'}})
   WRONG:  MATCH (c:Course {{title: 'CS510'}})
2. Course codes (e.g. CS510, MATH201, ECE301) are ALWAYS stored in `id`, never in `title`.
3. Prerequisite direction — the prerequisite points TO the course that needs it:
   RIGHT:  MATCH (p:Course)-[:PREREQUISITE_FOR]->(c:Course {{id: 'CS510'}})
   WRONG:  MATCH (c:Course {{id: 'CS510'}})-[:PREREQUISITE_FOR]->(p:Course)
4. Use OPTIONAL MATCH when a property or relationship may not exist.
5. Always alias RETURN values (e.g. RETURN c.title AS title).

Here are examples:
""",
    suffix="Question: {question}\nCypher:",
    input_variables=["schema", "question"],
)

# Schema for the graph (used in prompts to guide LLM Cypher generation)
preferred_schema  = """
Node properties:
- Course: {id: STRING, title: STRING, credits: STRING, college: STRING, writing_intensive: BOOLEAN, repeat_status: STRING}
- College: {name: STRING}

Relationship properties:
- PREREQUISITE_FOR: {min_grade: STRING, concurrent: BOOLEAN}

Relationships:
- (:Course)-[:PREREQUISITE_FOR {min_grade, concurrent}]->(:Course)
- (:Course)-[:COREQUISITE_FOR]->(:Course)
- (:Course)-[:OFFERED_BY]->(:College)

CRITICAL RULES:
1. ALWAYS match Course nodes using `id` (e.g. {id: 'CS613'}), never `title`.
2. Prerequisite direction: (prereq)-[:PREREQUISITE_FOR]->(target_course)
3. min_grade is a property ON the relationship, not the node. Access it as `r.min_grade`.
"""

# Set up the structured output router
structured_llm_query_router = llm.with_structured_output(RouteQuery)

# System prompt for routing user questions to the appropriate datasource
system_prompt_route_query = """You are an expert at routing university course queries.

Route to GRAPH QUERY for:
- Prerequisites or corequisites for a specific course
- Courses offered by a specific college/department  
- Relationships between specific named courses (e.g. "CS310", "MATH201")
- Questions about the details of specific courses (e.g. "What are the credits for CS510?", "Is CS310 writing intensive?")

Route to VECTOR SEARCH for:
- Exploratory or thematic questions ("courses about AI", "data science classes")
- Course recommendations
- Questions about course content or topics

Route to BOTH for:
- Ambiguous questions that could be answered by either semantic or structural search
- Complex questions that require both types of information (e.g. "What are the prerequisites for courses about machine learning?")
"""


# Take the user question and route it to the appropriate search method
route_prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt_route_query),
    ("human", "{question}"),
])

# Combine the prompt and the structured output router into a single chain for routing user questions
question_router = route_prompt | structured_llm_query_router






