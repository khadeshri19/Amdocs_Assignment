import os
import re
import pandas as pd
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from google import genai
from google.genai import types

app = FastAPI(
    title="Smart Financial Data Assistant API",
    description="Unified API for the Amdocs German Credit Data Assistant",
    version="1.0.0"
)

# Enable CORS for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load the dataset locally from the same directory
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(CURRENT_DIR, "german_credit_clean.csv")

try:
    df_clean = pd.read_csv(CSV_PATH)
except Exception as e:
    # Fail-safe search
    try:
        df_clean = pd.read_csv("../data/german_credit_clean.csv")
    except Exception:
        df_clean = pd.DataFrame()

class QueryEngine:
    def __init__(self, dataframe=df_clean):
        self.df = dataframe.copy()
        
    def query(self, user_query: str, api_key: str = None) -> dict:
        user_query_clean = user_query.strip().lower()
        
        # If API key is provided, try the LLM approach first
        if api_key:
            try:
                return self._query_gemini(user_query, api_key)
            except Exception as e:
                print(f"Gemini query failed: {e}. Falling back to rule-based engine.")
        
        # Rule-based processing
        return self._query_rule_based(user_query_clean)

    def _query_gemini(self, user_query: str, api_key: str) -> dict:
        client = genai.Client(api_key=api_key)
        
        schema_info = """
        The dataset is loaded in a Pandas DataFrame named `df`. Here are the columns:
        - `Age` (int): Age of the borrower in years.
        - `Sex` (str): Gender ('male', 'female').
        - `Job` (int): Job category (0=unskilled non-resident, 1=unskilled resident, 2=skilled, 3=highly skilled/mgmt).
        - `Housing` (str): Home ownership ('own', 'free', 'rent').
        - `Saving accounts` (str): Savings categories ('unknown', 'little', 'moderate', 'quite rich', 'rich').
        - `Checking account` (str): Checking balance categories ('little', 'moderate', 'rich', 'unknown').
        - `Credit amount` (int): Loan amount in DM (currency).
        - `Duration` (int): Loan duration in months.
        - `Purpose` (str): Purpose of loan ('radio/TV', 'education', 'furniture/equipment', 'car', 'business', 'domestic appliances', 'repairs', 'vacation/others').
        - `Age_Group` (str): Age categories ('18-25', '26-35', '36-50', '51+').
        - `Credit_Band` (str): Credit size categories ('<1K', '1K-3K', '3K-6K', '6K-10K', '>10K').
        - `High_Risk_Proxy` (int): Risk flag (1 = High Risk (Credit amount > 5000 and Duration > 30), 0 = Low Risk).
        """

        prompt = f"""
        You are a data assistant that translates natural language queries into Pandas Python code.
        {schema_info}
        
        User Query: "{user_query}"
        
        Task:
        1. Write a small python code block that performs the query on the DataFrame `df`.
        2. Assign the final result to a variable called `result_df`. 
           - If the result is a single value, wrap it as a DataFrame: e.g. `result_df = pd.DataFrame([{"result": value}])`.
           - If it is a Series or GroupBy, use `.reset_index()` to convert it back to a standard DataFrame.
        3. Do NOT import pandas or load data. The DataFrame `df` is already in local scope.
        4. Explain the result in 2-3 sentences.
        5. Identify a suitable chart type ('bar', 'pie', 'line', 'scatter', or 'none'). If grouping or comparing categories, use 'bar' or 'pie'. If plotting duration vs credit amount, use 'scatter'.
        6. Specify what columns to use for X and Y labels of the chart.
        
        Output format: Return ONLY a valid JSON string with no markdown formatting around it (do NOT wrap it in ```json blocks). The JSON must have these exact keys:
        {{
            "pandas_code": "code block to run",
            "explanation_template": "A string explaining what this data shows.",
            "chart_type": "bar/pie/line/scatter/none",
            "x_label": "column_for_x_axis_or_empty",
            "y_label": "column_for_y_axis_or_empty"
        }}
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        import json
        res_data = json.loads(response.text.strip())
        
        pandas_code = res_data.get("pandas_code", "")
        chart_type = res_data.get("chart_type", "none")
        x_label = res_data.get("x_label", "")
        y_label = res_data.get("y_label", "")
        
        local_vars = {"df": self.df, "pd": pd, "np": np}
        exec(pandas_code, {}, local_vars)
        result_df = local_vars.get("result_df", None)
        
        if result_df is None:
            raise ValueError("Variable 'result_df' was not created by the generated code.")
            
        if not isinstance(result_df, pd.DataFrame):
            if isinstance(result_df, pd.Series):
                result_df = result_df.reset_index()
            else:
                result_df = pd.DataFrame([{"result": result_df}])
        
        result_data = result_df.to_dict(orient="records")
        
        summary_prompt = f"""
        Based on the user's query: "{user_query}"
        And the query result data: {result_data}
        
        Provide a clear, structured response that explains these results to a business stakeholder in a helpful, analytical tone. Include the numbers and highlight key observations.
        """
        
        summary_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=summary_prompt
        )
        
        explanation = summary_response.text.strip()
        
        return {
            "success": True,
            "answer": explanation,
            "data": result_data,
            "chart_type": chart_type,
            "x_label": x_label,
            "y_label": y_label,
            "sql_or_pandas": pandas_code,
            "data_used": "german_credit_clean.csv",
            "error": None
        }

    def _query_rule_based(self, q: str) -> dict:
        df_temp = self.df.copy()
        filters_applied = []
        
        # 1. Apply single-value filters (Only filter gender if we are not grouping/comparing gender)
        has_gender_group = re.search(r'\bsex\b|\bgender\b|\bmale vs female\b|\bfemale vs male\b', q) is not None
        if not has_gender_group and "vs" not in q and "compare" not in q:
            if re.search(r'\bfemale\b', q):
                df_temp = df_temp[df_temp["Sex"] == "female"]
                filters_applied.append("Gender = female")
            elif re.search(r'\bmale\b', q):
                df_temp = df_temp[df_temp["Sex"] == "male"]
                filters_applied.append("Gender = male")
            
        # Housing filter (avoiding substring matching)
        if re.search(r'\bown\b|\bowning\b', q):
            df_temp = df_temp[df_temp["Housing"] == "own"]
            filters_applied.append("Housing = own")
        elif re.search(r'\brent\b|\brenting\b', q):
            df_temp = df_temp[df_temp["Housing"] == "rent"]
            filters_applied.append("Housing = rent")
        elif re.search(r'\bfree\b', q):
            df_temp = df_temp[df_temp["Housing"] == "free"]
            filters_applied.append("Housing = free")
            
        # Purpose filter
        purposes = {
            r'\bcar\b|\bcars\b': "car",
            r'\beducation\b|\bschool\b': "education",
            r'\bbusiness\b|\bcompany\b': "business",
            r'\bradio\b|\btv\b': "radio/TV",
            r'\bfurniture\b|\bbed\b|\bchair\b': "furniture/equipment",
            r'\bappliance\b|\bappliances\b': "domestic appliances",
            r'\brepair\b|\brepairs\b': "repairs",
            r'\bvacation\b|\btravel\b': "vacation/others"
        }
        for pattern, p_val in purposes.items():
            if re.search(pattern, q):
                df_temp = df_temp[df_temp["Purpose"] == p_val]
                filters_applied.append(f"Purpose = {p_val}")
                break
                
        # Savings level filter
        for s in ["little", "moderate", "quite rich", "rich", "unknown"]:
            if re.search(r'\b' + re.escape(s) + r'\b.*savings?\b|\bsavings?\b.*\b' + re.escape(s) + r'\b', q):
                df_temp = df_temp[df_temp["Saving accounts"] == s]
                filters_applied.append(f"Savings = {s}")
                break

        # Checking level filter
        for c in ["little", "moderate", "rich", "unknown"]:
            if re.search(r'\b' + re.escape(c) + r'\b.*checking\b|\bchecking\b.*\b' + re.escape(c) + r'\b', q):
                df_temp = df_temp[df_temp["Checking account"] == c]
                filters_applied.append(f"Checking = {c}")
                break

        # Risk filter
        is_risk_filter = re.search(r'\bhigh[ -]risk\b|\brisky\b', q) is not None
        if is_risk_filter and not re.search(r'\brates?\b|\bpercentages?\b|\bby\b|\bvs\b', q):
            df_temp = df_temp[df_temp["High_Risk_Proxy"] == 1]
            filters_applied.append("Risk = High Risk")
            
        # 2. Identify aggregation column (using strict word boundary patterns to avoid "average" -> "age" mismatches)
        agg_col = "Credit amount"
        agg_label = "Credit amount"
        
        if re.search(r'\bduration\b|\bmonths?\b|\bterm\b', q):
            agg_col = "Duration"
            agg_label = "Duration"
        elif re.search(r'\bage\b|\bages\b', q) and not re.search(r'\bage[ -]group\b', q):
            agg_col = "Age"
            agg_label = "Age"
            
        # 3. Identify Group By
        group_col = None
        group_label = None
        if re.search(r'\bhousing\b', q):
            group_col = "Housing"
            group_label = "Housing Status"
        elif re.search(r'\bsex\b|\bgender\b|\bmale vs female\b|\bfemale vs male\b', q):
            group_col = "Sex"
            group_label = "Gender"
        elif re.search(r'\bpurpose\b', q):
            group_col = "Purpose"
            group_label = "Loan Purpose"
        elif re.search(r'\bsavings?\b', q):
            group_col = "Saving accounts"
            group_label = "Savings Level"
        elif re.search(r'\bchecking\b', q):
            group_col = "Checking account"
            group_label = "Checking Level"
        elif re.search(r'\bage[ -]group\b|\bdemographics?\b', q):
            group_col = "Age_Group"
            group_label = "Age Group"
            
        # 4. Handle sorting / top rankings
        limit_match = re.search(r'\btop\s+(\d+)\b', q)
        if limit_match or re.search(r'\blargest\b|\bhighest\b|\blongest\b', q):
            limit = int(limit_match.group(1)) if limit_match else 5
            sort_col = "Duration" if re.search(r'\bduration\b|\blongest\b', q) else "Credit amount"
            
            result_df = df_temp.sort_values(by=sort_col, ascending=False).head(limit)
            
            ans_desc = f"Here are the top {limit} records sorted by {sort_col}."
            if filters_applied:
                ans_desc += f" (Filters applied: {', '.join(filters_applied)})"
                
            ans_details = ""
            for idx, r in enumerate(result_df.itertuples(), 1):
                ans_details += f"\n{idx}. Client (Age: {r.Age}, Sex: {r.Sex}): {sort_col} = {getattr(r, sort_col.replace(' ', '_'))} DM for {r.Purpose} ({r.Housing} housing)."
            
            return {
                "success": True,
                "answer": ans_desc + ans_details,
                "data": result_df[["Age", "Sex", "Housing", "Credit amount", "Duration", "Purpose", "High_Risk_Proxy"]].to_dict(orient="records"),
                "chart_type": "bar" if len(result_df) > 1 else "none",
                "x_label": "Purpose",
                "y_label": sort_col,
                "sql_or_pandas": f"df.sort_values(by='{sort_col}', ascending=False).head({limit})",
                "data_used": "german_credit_clean.csv",
                "error": None
            }
            
        # 5. Perform aggregations
        filter_str = f" [Filters: {', '.join(filters_applied)}]" if filters_applied else ""
        
        # Risk rate queries (using strict word boundary check to avoid "duration" matching "rate")
        is_rate_query = re.search(r'\brates?\b|\bpercentages?\b|\bratios?\b', q) is not None
        if is_rate_query:
            if group_col:
                res = df_temp.groupby(group_col)["High_Risk_Proxy"].mean().reset_index()
                res["High_Risk_Proxy"] = (res["High_Risk_Proxy"] * 100).round(1)
                res = res.rename(columns={"High_Risk_Proxy": "High Risk Rate (%)"})
                
                chart_type = "bar"
                ans = f"Here is the high-risk loan rate (%) grouped by {group_label}{filter_str}:"
                for idx, r in res.iterrows():
                    ans += f"\n- {r[group_col]}: {r['High Risk Rate (%)']}%"
                
                return {
                    "success": True,
                    "answer": ans,
                    "data": res.to_dict(orient="records"),
                    "chart_type": chart_type,
                    "x_label": group_col,
                    "y_label": "High Risk Rate (%)",
                    "sql_or_pandas": f"df.groupby('{group_col}')['High_Risk_Proxy'].mean() * 100",
                    "data_used": "german_credit_clean.csv",
                    "error": None
                }
            else:
                rate = (df_temp["High_Risk_Proxy"].mean() * 100).round(1)
                count = int(df_temp["High_Risk_Proxy"].sum())
                total = len(df_temp)
                ans = f"The overall high-risk loan rate is **{rate}%**{filter_str}. Out of {total} total matching credit profiles, **{count}** loans are classified as high risk."
                
                return {
                    "success": True,
                    "answer": ans,
                    "data": [{"rate_percent": rate, "high_risk_count": count, "total_count": total}],
                    "chart_type": "none",
                    "x_label": "",
                    "y_label": "",
                    "sql_or_pandas": "df['High_Risk_Proxy'].mean() * 100",
                    "data_used": "german_credit_clean.csv",
                    "error": None
                }
                
        # Count queries
        if re.search(r'\bhow many\b|\bcount\b|\bnumber of\b', q):
            if group_col:
                res = df_temp.groupby(group_col).size().reset_index(name="Loan Count")
                chart_type = "pie" if group_col in ["Sex", "Housing"] else "bar"
                
                ans = f"Here is the loan count grouped by {group_label}{filter_str}:"
                for idx, r in res.iterrows():
                    ans += f"\n- {r[group_col]}: {r['Loan Count']} loans"
                    
                return {
                    "success": True,
                    "answer": ans,
                    "data": res.to_dict(orient="records"),
                    "chart_type": chart_type,
                    "x_label": group_col,
                    "y_label": "Loan Count",
                    "sql_or_pandas": f"df.groupby('{group_col}').size()",
                    "data_used": "german_credit_clean.csv",
                    "error": None
                }
            else:
                cnt = len(df_temp)
                ans = f"There are **{cnt}** matching credit records{filter_str} in the dataset."
                return {
                    "success": True,
                    "answer": ans,
                    "data": [{"count": cnt}],
                    "chart_type": "none",
                    "x_label": "",
                    "y_label": "",
                    "sql_or_pandas": "len(df)",
                    "data_used": "german_credit_clean.csv",
                    "error": None
                }
                
        # Average / Mean queries
        if re.search(r'\baverage\b|\bmean\b', q):
            if group_col:
                res = df_temp.groupby(group_col)[agg_col].mean().reset_index()
                res[agg_col] = res[agg_col].round(1)
                res = res.rename(columns={agg_col: f"Average {agg_label}"})
                
                chart_type = "bar"
                ans = f"Here is the average {agg_label.lower()} grouped by {group_label}{filter_str}:"
                for idx, r in res.iterrows():
                    val = r[f"Average {agg_label}"]
                    unit = " DM" if agg_col == "Credit amount" else (" months" if agg_col == "Duration" else " years")
                    ans += f"\n- {r[group_col]}: {val}{unit}"
                    
                return {
                    "success": True,
                    "answer": ans,
                    "data": res.to_dict(orient="records"),
                    "chart_type": chart_type,
                    "x_label": group_col,
                    "y_label": f"Average {agg_label}",
                    "sql_or_pandas": f"df.groupby('{group_col}')['{agg_col}'].mean()",
                    "data_used": "german_credit_clean.csv",
                    "error": None
                }
            else:
                mean_val = df_temp[agg_col].mean().round(1)
                unit = " DM" if agg_col == "Credit amount" else (" months" if agg_col == "Duration" else " years")
                ans = f"The average **{agg_label.lower()}** is **{mean_val}{unit}**{filter_str}."
                return {
                    "success": True,
                    "answer": ans,
                    "data": [{f"average_{agg_col.lower().replace(' ', '_')}": mean_val}],
                    "chart_type": "none",
                    "x_label": "",
                    "y_label": "",
                    "sql_or_pandas": f"df['{agg_col}'].mean()",
                    "data_used": "german_credit_clean.csv",
                    "error": None
                }

        # Sum queries
        if re.search(r'\btotal\b|\bsum\b', q):
            if group_col:
                res = df_temp.groupby(group_col)["Credit amount"].sum().reset_index()
                res = res.rename(columns={"Credit amount": "Total Credit (DM)"})
                chart_type = "bar"
                
                ans = f"Here is the total credit volume (DM) grouped by {group_label}{filter_str}:"
                for idx, r in res.iterrows():
                    ans += f"\n- {r[group_col]}: {r['Total Credit (DM)']} DM"
                    
                return {
                    "success": True,
                    "answer": ans,
                    "data": res.to_dict(orient="records"),
                    "chart_type": chart_type,
                    "x_label": group_col,
                    "y_label": "Total Credit (DM)",
                    "sql_or_pandas": f"df.groupby('{group_col}')['Credit amount'].sum()",
                    "data_used": "german_credit_clean.csv",
                    "error": None
                }
            else:
                total_val = int(df_temp["Credit amount"].sum())
                ans = f"The total credit volume is **{total_val} DM**{filter_str}."
                return {
                    "success": True,
                    "answer": ans,
                    "data": [{"total_credit_amount": total_val}],
                    "chart_type": "none",
                    "x_label": "",
                    "y_label": "",
                    "sql_or_pandas": "df['Credit amount'].sum()",
                    "data_used": "german_credit_clean.csv",
                    "error": None
                }

        # General correlation / scatter fallback
        if re.search(r'\bscatter\b|\brelation\b|\bcompare\b', q):
            scatter_data = df_temp.sample(min(150, len(df_temp)))[["Credit amount", "Duration", "Housing", "Age", "High_Risk_Proxy"]].to_dict(orient="records")
            return {
                "success": True,
                "answer": "Here is a comparison scatter representation of credit amount vs. duration. (Sample limited to 150 points for visualization).",
                "data": scatter_data,
                "chart_type": "scatter",
                "x_label": "Credit amount",
                "y_label": "Duration",
                "sql_or_pandas": "df[['Credit amount', 'Duration', 'Housing']]",
                "data_used": "german_credit_clean.csv",
                "error": None
            }

        # Catch-all fallback default summary description
        total_records = len(df_temp)
        avg_credit = round(df_temp["Credit amount"].mean(), 1)
        avg_dur = round(df_temp["Duration"].mean(), 1)
        risk_pct = round(df_temp["High_Risk_Proxy"].mean() * 100, 1)
        
        fallback_ans = (
            f"I analyzed the credit records matching your filter parameters{filter_str}:\n"
            f"- Total Matching Records: **{total_records}**\n"
            f"- Average Credit Amount: **{avg_credit} DM**\n"
            f"- Average Duration: **{avg_dur} months**\n"
            f"- High Risk Loan Rate: **{risk_pct}%**\n\n"
            f"Please ask a query like: 'What is the average credit amount by housing type?' or 'Show me the top 5 largest business loans'."
        )
        
        return {
            "success": True,
            "answer": fallback_ans,
            "data": [{
                "count": total_records, 
                "average_credit": avg_credit, 
                "average_duration": avg_dur, 
                "high_risk_rate_percent": risk_pct
            }],
            "chart_type": "none",
            "x_label": "",
            "y_label": "",
            "sql_or_pandas": "df.describe()",
            "data_used": "german_credit_clean.csv",
            "error": None
        }

engine = QueryEngine(df_clean)

# Routes to serve simplified web page
@app.get("/")
def get_index():
    return FileResponse(os.path.join(CURRENT_DIR, "index.html"))

@app.get("/style.css")
def get_style():
    return FileResponse(os.path.join(CURRENT_DIR, "style.css"))

@app.get("/app.js")
def get_app():
    return FileResponse(os.path.join(CURRENT_DIR, "app.js"))

class QueryRequest(BaseModel):
    query: str
    api_key: Optional[str] = None

@app.post("/api/query")
def run_query(request: QueryRequest):
    query = request.query
    api_key = request.api_key
    
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
        
    try:
        result = engine.query(query, api_key)
        return result
    except Exception as e:
        return {
            "success": False,
            "answer": "An error occurred while processing your request.",
            "data": [],
            "chart_type": "none",
            "x_label": "",
            "y_label": "",
            "sql_or_pandas": "",
            "data_used": "german_credit_clean.csv",
            "error": str(e)
        }

