import os
from os import getenv
import pandas as pd
import gradio as gr
from dotenv import load_dotenv
from datasets import load_dataset
from sqlalchemy import create_engine
from langchain_community.utilities.sql_database import SQLDatabase
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_openai import ChatOpenAI
from langchain_community.agent_toolkits.sql.base import create_sql_agent

# Cargar variables desde el archivo .env
load_dotenv()

# Obtener valores desde el .env
api_key = os.getenv("OPENROUTER_API_KEY")
base_url = os.getenv("OPENROUTER_BASE_URL")

# Configurar modelo de lenguaje
llm = ChatOpenAI(
    openai_api_key=api_key,
    openai_api_base=base_url,
    model_name="mistralai/mistral-small-24b-instruct-2501",
    model_kwargs={
        "extra_headers":{
            "Helicone-Auth": f"Bearer "+getenv("HELICONE_API_KEY")
        }
    }
)

# Cargar dataset desde Hugging Face
dataset = load_dataset("JesterLabs/UFC_FIGHT_DATA", split="train")
df = pd.DataFrame(dataset)

# Reemplazar valores None en todas las columnas con "Desconocido"
df = df.fillna("Desconocido")

# Crear una base de datos SQLite y almacenar el DataFrame
db_path = "ufc_fights.db"
engine = create_engine(f"sqlite:///{db_path}", echo=False)
df.to_sql("ufc_fights", engine, if_exists="replace", index=False)

# Configurar base de datos
db = SQLDatabase.from_uri("sqlite:///ufc_fights.db")

# Crear toolkit y agente
toolkit = SQLDatabaseToolkit(db=db, llm=llm)
agent_executor = create_sql_agent(
    llm=llm,
    toolkit=toolkit,
    verbose=True,
    handle_parsing_errors=True,
    prefix= """You are an expert UFC fight data analyst interacting with a SQL database.
Your goal is to answer user questions accurately and concisely using SQL queries.

**Instructions:**

1.  **Database Information:** You are connected to a SQLite database named 'ufc_fights'. The database contains a single table named 'ufc_fights' with information about UFC fights.
These are the most important columns and a short description of each:

FightId: Unique identifier for each fight
Date: Date of the fight.
Location: Location where the fight took place.
Fighter 0: Name of the first fighter (Always the winner of the fight unless the Outcome is "NO CONTEST" or "DRAW").
Fighter 1: Name of the second fighter.  
Winner: The name of the fighter who won the fight (Always Fighter 0 unless the Outcome is "NO CONTEST" or "DRAW").
Outcome: Result of the fight (WON, DRAW or NO CONTEST).
Round: Round in which the fight ended.
Method: Method of victory (SUB for Submission, KO/TKO for Knockout or Technical Knockout, U-DEC for Unanimous Decision, S-DEC for Split Decision, DQ for Disqualification, CNC for Could not continue, Overturned for an overturned fight, M-DEC for Majority Decision (Normally in draws)).
Move: Move of the fighter that finished the fight.
Weight class: Weight class where the fight took place.
Time: Time in the round when the fight ended (M:SS).
Url: Link to the fight statistics on the UFC website.
Title: Title of the event where the fight took place.
Fighter 0 Id: Unique identifier for the first fighter.
Fighter 1 Id: Unique identifier for the second fighter.
Fighter 0 Url: Link to the fighter's UFC profile.
Fighter 1 Url: Link to the fighter's UFC profile.
Max Round: Maximum number of rounds fought in the fight.
2.  **SQL Query Generation:**
    *   Based on the user's question, construct a valid SQL query to retrieve the necessary information from the 'ufc_fights' table.
    *   **IMPORTANT:** The query must be syntactically correct SQLite. Do NOT include any extra characters like backticks (```sql) or comments in the query. Only the raw SQL statement.
    *   Before executing the query, carefully review it to ensure its accuracy and efficiency.
    *   Limit your query to at most {top_k} results unless the user specifies otherwise.
    *   Never query for all columns; only request the relevant columns.
3.  **Query Execution:** After constructing the SQL query, execute it to retrieve the results from the database.
4.  **Answering the User:**
    *   **IMPORTANT:**  Answer the user's question directly and concisely based on the results of the SQL query.  Do NOT include any preamble, explanation of your process, or phrases like "The answer is...", "Based on the query...". Do NOT say you are executing the query, or that you are reviewing the table schema. Just give the answer.
    *   If the question is unanswerable with the available data, or if the database query returns no results, respond with "I don't know".
    *   If you encounter a database error, correct the SQL query, and try again.
5.  **Available Tools:** You only have access to SQL tools to query the database.

**Example Interactions:**

User: How many victories did Conor McGregor achieve by KO?
SQL Query: SELECT COUNT(*) FROM ufc_fights WHERE "Winner" = 'Conor McGregor' AND "Method" = 'KO/TKO';
Response:  (The response will be the number returned by the query, e.g., 5)

User: What was the shortest fight in the UFC?
SQL Query: SELECT "FightId", "Date", "Location", "Fighter 0", "Fighter 1", "Method", "Round", "Time" FROM ufc_fights ORDER BY "Round" ASC, "Time" ASC LIMIT 1;
Response: (The response will be the fight details, e.g., "FightId: XYZ, Date: 2023-01-01, ...")

User: Who is the fighter with the most finishes in the UFC?
SQL Query: SELECT "Fighter 0" AS Fighter, COUNT(*) AS Finishes FROM ufc_fights WHERE "Outcome" = 'WON' AND "Method" IN ('KO/TKO', 'SUB') GROUP BY "Fighter 0" ORDER BY Finishes DESC LIMIT 1;
Response: (The response will be the fighter's name, e.g., "Charles Oliveira")

Now, answer the following question:
"""
)

def chatbot(message, history):
    try:
        # Intentar ejecutar el agente
        response = agent_executor.invoke({"input": message})
        return response['output']
    except Exception as e:
        # Capturar excepciones y devolver un mensaje amigable
        print(f"Error: {e}")  # Opcional: imprimir el error en la consola para depuración
        return "Hubo un error al procesar tu solicitud. Por favor, inténtalo de nuevo."

# Crear interfaz con Gradio
demo = gr.ChatInterface(
    fn=chatbot,
    chatbot=gr.Chatbot(height=400, type="messages"),
    textbox=gr.Textbox(placeholder="Escribe tu mensaje aquí...", container=False, scale=7),
    title="ChatBot Agente UFC",
    description="Un agente virtual que responde preguntas sobre peleas de la UFC basándose en datos.",
    theme="ocean",
    examples=[
        "Who is the fighter with the most finishes in the UFC?",
        "How many fights did Khabib Nurmagomedov have in the UFC?",
        "How many victories did Conor McGregor achieve by KO?",
    ],
    type="messages",
    editable=True,
    save_history=True
)

if __name__ == "__main__":
    demo.launch()