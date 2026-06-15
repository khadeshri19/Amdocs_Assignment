# Amdocs - Smart Financial Data Assistant

An interactive, natural-language data exploration chatbot designed for Telecom and Financial Services lending stakeholders to analyze portfolio risk and customer demographics. This application is pre-populated with the **German Credit Card Dataset** (1,000 credit profiles preprocessed with risk flags).

---

## Key Features

* **Natural Language Queries**: Ask questions in plain English (e.g., *"What is the average credit amount by housing type?"*, *"Show me the top 5 largest business loans"*).
* **Hybrid Execution Engine**:
  * **Local Rule-Based Parser (Default)**: Compiles and executes Pandas code locally in python. It is 100% free, runs offline, has zero uptime limits, and uses strict word-boundary regexes to prevent aggregate syntax mismatches.
  * **GenAI LLM Integration**: Provide your custom Google Gemini API Key in the settings panel to enable advanced open-ended reasoning using the official `google-genai` SDK and the `gemini-2.5-flash` model.
* **Auto-Visualization**: Automatically translates query results into tables and renders responsive charts (Bar, Pie, or Scatter) using **Chart.js** in real-time.
* **Syntax Code Inspection**: Visualizes the exact Pandas query that was executed on the dataset to maintain transparency for analysts.

---

## Tech Stack

* **Backend**: FastAPI (Python 3.13)
* **Frontend**: HTML5, Vanilla CSS3 (Slate dark theme / glassmorphic UI), and Vanilla JavaScript
* **Graphing Engine**: Chart.js
* **Data Processing**: Pandas, NumPy
* **LLM Client**: official `google-genai` SDK

---

## How to Run Locally

### 1. Install Dependencies
Make sure you have python installed, and run:
```bash
pip install fastapi uvicorn pandas google-genai pydantic
```

### 2. Start the Server
Navigate to the project root and run the FastAPI server:
```bash
python -m uvicorn ai_assistant.main:app --host 127.0.0.1 --port 8000
```

### 3. Open in Browser
Open your browser and navigate to:
```url
http://127.0.0.1:8000
```
