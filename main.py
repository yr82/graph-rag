import os
import streamlit as st
from dotenv import load_dotenv

from langchain_neo4j import Neo4jGraph, Neo4jVector, GraphCypherQAChain
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate, ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda

from pyvis.network import Network

import streamlit.components.v1 as components

import config

# Load environment variables
load_dotenv("sk.env")

NEO4J_URI = os.environ.get("NEO4J_URI")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Cache the Neo4jVector instance to reuse connections across queries (used for semantic search)
@st.cache_resource
def get_neo4j_vector_store():
    vector_store = Neo4jVector.from_existing_index(
        embedding=OpenAIEmbeddings(),
        url=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
        index_name="course_descriptions",
        node_label="Course",
        text_node_properties=["description"],
        embedding_node_property="embedding",
        retrieval_query=config.semantic_retrieval_query,
    )
    vector_retriever = vector_store.as_retriever(search_kwargs={"k": 5})
    return vector_retriever

# Cache the Neo4jGraph instance to reuse connections across queries (used for LangChain Cypher QA by the llm)
@st.cache_resource
def get_neo4j_graph():
    graph = Neo4jGraph(
        url=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD)
    
    graph.schema = config.preferred_schema

    return graph

# Cache the LangChain Cypher QA chain to avoid reinitializing LLM and graph on every query
@st.cache_resource
def get_langchain_cypher_chain(_graph):

    # Unable to get read-only access with the free version of Neo4j Aura so I need to allow dangerous requests.
    return GraphCypherQAChain.from_llm(config.llm, 
                                       graph=_graph, 
                                       cypher_prompt=config.cypher_prompt, 
                                       return_intermediate_steps=True, 
                                       allow_dangerous_requests=True, 
                                       verbose=True)

# Set up the vector retriever and chain
vector_retriever = get_neo4j_vector_store()

vector_chain = (
    {"context": vector_retriever | config.format_docs, "question": RunnablePassthrough()}
    | config.vector_prompt
    | config.llm
    | StrOutputParser()
)

# Set up the graph retriever and chain
graph_retriever = get_neo4j_graph()
graph_chain = get_langchain_cypher_chain(graph_retriever)

# Router function
def route(inputs: dict):
    question = inputs["question"]
    result = config.question_router.invoke({"question": question})
    
    print(f"Routing to: {result.datasource}")
    
    if result.datasource == "both":
        vector_answer = vector_chain.invoke(question)
        graph_answer = graph_chain.invoke({"query": question})["result"]

        # Merge with a final LLM call
        merge_prompt_for_both = f"""
        Semantic search found: {vector_answer}
        Graph query found: {graph_answer}
        Synthesize a combined answer for: {question}
        """
        return config.llm.invoke(merge_prompt_for_both).content

    elif result.datasource == "vector_search":
        return vector_chain.invoke(question)
    else:
        return graph_chain.invoke({"query": question})["result"]


# Complete pipeline
complete_pipeline = RunnableLambda(route)

# Streamlit app -------------------------------------------------

def app():
    st.set_page_config(layout="wide", page_title="Dragon Course Graph Search")
    st.title("Dragon Course Graph Search 🐉")

    col1, col2 = st.columns([2, 2])

    with col1:
        st.subheader("Query the Drexel course catalog with any question!")
        question = st.text_area("Ask a question about the details (description, credits, etc.) of any course currently in the catalog", value="What are the prerequisites for CS510?", height=150)

        if st.button("Ask question") and question.strip():
        
            with st.spinner("Querying Neo4j through LangChain..."):
                try:
                    print("Invoking LangChain chain with question:", question)
                    response = complete_pipeline.invoke({"question": question})
                except Exception as e:
                    st.error(f"LangChain query failed: {e}")
                    response = None

            if response is not None:
                print("LangChain response:", response)
                st.markdown("**Response:**")
                st.write(response)       

    with col2:
        st.subheader("Related courses")
        st.info("Graph visualization coming soon! This will show the relevant subgraph for the query.")



if __name__ == "__main__":
    app()





