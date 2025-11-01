from dotenv import dotenv_values
import cohere
import json
import difflib
import re

def get_ipo_decision( live_ipos, analysis_summaries, ipo_subscriptions):
    # Load env values from .env file
    env_vars=dotenv_values(".env")
    # Retrieve API Key
    CohereApiKey = env_vars.get("COHERE_API_KEY")
    print(f"Cohere API Key Loaded: {CohereApiKey}")
    if not CohereApiKey:
        raise ValueError("Cohere API Key not found in .env file.")
    # Create a Cohere client using the API key
    co = cohere.Client(api_key=CohereApiKey)
    """
    Analyzes live IPO data against analysis summaries using Cohere Command R+.
    
    Args:
        co (cohere.Client): Initialized Cohere client.
        live_ipos (list): List of dictionaries with current IPO details.
        analysis_summaries (list): List of dictionaries with IPO analysis summaries.
        
    Returns:
        list: A list of dictionaries with the structured analysis results.
    """
    
    field_descriptions = (
        "\n\n--- FIELD DESCRIPTIONS ---\n"
        "1. LiveIPOName: The company's name exactly as found in the LIVE IPOS list.\n"
        "2. IPOAnalysisTitle: The title of the analysis (e.g., 'Rubicon Research') or 'No Analysis Found'.\n"
        "3. Recommendation: The final action: 'Apply', 'Avoid', or 'Review'.\n"
        "4. RecommendationSource: The specific, short phrase from the analysis that justifies the recommendation (e.g., 'Shines like a Ruby!').\n"
        "5. SummarySnippet: A concise 1-2 sentence distillation of the analysis's main point.\n"
        "6. LiveIPODetails: An object containing the symbol, price_range, ipo_link, ipo_analysis_link, start_date, and end_date from the original LIVE IPOS data for easy reference.\n"
        "7. LiveIPOSubscriptionDetails: An object containing the latest subscription details (Total, QIB, NII, RII, P/E, GMP, IPO Price, Close Date) if available."
    )
    
    json_schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "LiveIPOName": { 
                    "type": "STRING", 
                    "description": "The Company name exactly as it appears in the live_ipos list." 
                },
                "IPOAnalysisTitle": { 
                    "type": "STRING", 
                    "description": "The title of the analysis article that was matched, or 'No Analysis Found'." 
                },
                "Recommendation": { 
                    "type": "STRING", 
                    "description": "The final decision based on the summary: 'Apply' (Strong positive analysis), 'Avoid' (Strong negative analysis), or 'Review' (Neutral/Mixed/No analysis)." 
                },
                "RecommendationSource": { 
                    "type": "STRING", 
                    "description": "The key sentiment or phrase from the analysis summary that directly supports the recommendation (e.g., 'Shines like a Ruby!', 'Avoid', 'Losing Market Share')." 
                },
                "SummarySnippet": { 
                    "type": "STRING", 
                    "description": "A concise, 1-2 sentence snippet of the main summary content." 
                },
                "LiveIPODetails": { 
                    "type": "OBJECT",
                    "properties": {
                        "symbol": { "type": "STRING" },
                        "price_range": { "type": "STRING" },
                        "ipo_link": { "type": "STRING" },
                        "ipo_analysis_link": { "type": "STRING" },
                        "start_date": { "type": "STRING" },
                        "end_date": { "type": "STRING" }
                    },
                    "description": "Relevant details from the live IPO data."
                },
                "LiveIPOSubscriptionDetails": {
                    "type": "OBJECT",
                    "properties": {
                        "Total": { "type": "STRING" },
                        "QIB": { "type": "STRING" },
                        "NII": { "type": "STRING" },
                        "RII": { "type": "STRING" },
                        "P/E": { "type": "STRING" },
                        "GMP": { "type": "STRING" },
                        "IPO Price": { "type": "STRING" },
                        "Close Date": { "type": "STRING" }
                    },
                    "description": "Latest subscription details if available."
                }
                
            },
            "required": ["LiveIPOName", "IPOAnalysisTitle", "Recommendation", "RecommendationSource", "SummarySnippet", "LiveIPODetails"]
        }
    }
    
    # Text version of the JSON schema for inclusion in the prompt
    json_schema_text = json.dumps(json_schema, indent=4)
    
    system_instruction = f"""
        You are a specialized Financial and IPO Analyst Bot. Your primary task is to find matches between the provided 'LIVE IPOS' list and the 'ANALYSIS SUMMARIES' list and the 'LIVE IPO SUBSCRIPTION DETAILS' list. For each match, you must synthesize the analysis summary to provide a clear, actionable investment recommendation (Apply, Avoid, or Review). The output MUST be a JSON array that strictly adheres to the provided JSON schema. Use case-insensitive sub-string or token matching for the company names. For any live IPO that cannot be matched to an analysis, set 'IPOAnalysisTitle' to 'No Analysis Found', 'Recommendation' to 'Review', and 'RecommendationSource' to 'No analysis available for decision.'. \n--- REQUIRED JSON SCHEMA ---\n{json_schema_text} \n--- FIELD DESCRIPTIONS ---\n{field_descriptions}
    """

    user_query = f"""
    Analyze the following two data sources to determine the investment recommendation for each LIVE IPO:

    LIVE IPOS:
    {json.dumps(live_ipos, indent=2)}

    ANALYSIS SUMMARIES:
    {json.dumps(analysis_summaries, indent=2)}

    LIVE IPO SUBSCRIPTION DETAILS:
    {json.dumps(ipo_subscriptions, indent=2)}
    
    Follow the matching and decision rules provided in the system instruction.
    """
    
    print("--- Sending Request to Cohere API ---")
    try:
        # Using the chat endpoint for its advanced reasoning capabilities and structured output
        
        response = co.chat(
            model='command-r-08-2024',  # Excellent for structured output and complex reasoning
            message=user_query,
            preamble=system_instruction
        )
        
        # The Cohere response object contains the JSON string in the text attribute
        json_string = response.text.strip()
        # print(f"RESPONSE: {json_string}")
        
        # Parse the JSON string into a Python list
        json_start_tag = 'json\n'
        json_end_tag = '\n'
        parsed_results=[]
        
        if json_start_tag in json_string and json_end_tag in json_string:
            # Find the start and end indices of the raw JSON content
            start_index = json_string.find(json_start_tag) + len(json_start_tag)
            end_index = json_string.rfind(json_end_tag)

            # Extract the JSON string
            json_string = json_string[start_index:end_index].strip()
            parsed_results = json.loads(json_string)
        else:
            # Fallback or error handling if the expected format is not found
            print("Error: JSON block delimiters not found in response.")
            json_string = None # Set to None or handle as needed
        
        return parsed_results
        
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON response from Cohere: {e}")
        # print(f"Raw response text: {json_string}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return []

def _normalize_name(s: str) -> str:
    """Light normalization for fallback similarity."""
    if not isinstance(s, str):
        return ""
    s = s.lower()
    s = re.sub(r"[\(\)\[\]\{\},.:'\"|/\\@!#\$%\^&\*\+\-]+", " ", s)
    s = re.sub(r"\blimited\b", "ltd", s)
    s = re.sub(r"\bltd\.\b", "ltd", s)
    s = re.sub(r"\bipo\b", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _similarity(a: str, b: str) -> float:
    """Hybrid similarity for fallback: token overlap + SequenceMatcher."""
    a_norm, b_norm = _normalize_name(a), _normalize_name(b)
    if not a_norm or not b_norm:
        return 0.0
    # Token Jaccard
    ta, tb = set(a_norm.split()), set(b_norm.split())
    j = len(ta & tb) / max(1, len(ta | tb))
    # Sequence similarity
    sm = difflib.SequenceMatcher(None, a_norm, b_norm).ratio()
    # Weighted blend
    return 0.6 * sm + 0.4 * j

def resolve_application_row_name(target_name: str, candidates: list[str]) -> str:
    """
    Given a target IPO name (from Zerodha/live IPO list) and the list of first-column
    names scraped from the HDFC application table, return exactly one of the candidates
    to click for application.

    Uses Cohere to choose; falls back to similarity if needed.
    """
    try:
        # Fast exits
        if not candidates:
            return target_name
        if target_name in candidates:
            return target_name

        env_vars = dotenv_values(".env")
        api_key = env_vars.get("COHERE_API_KEY")
        if not api_key:
            raise RuntimeError("No COHERE_API_KEY; using fallback")

        co = cohere.Client(api_key=api_key)

        system_instruction = (
            "You are an IPO name resolver. Choose the single best matching candidate "
            "from a provided list of names for placing an IPO application. "
            "Rules: "
            "- Return EXACTLY one string that appears in the candidates list. "
            "- Be case-sensitive to the extent of returning the original candidate string. "
            "- Prefer matches that normalize tokens (ignore case, punctuation, dots, hyphens, '&', and suffix variations: 'Limited' vs 'Ltd'). "
            "- Avoid inventing or modifying names. "
            "- If multiple are close, choose the closest by common tokens and order. "
            "- Output ONLY the chosen candidate string with no extra text."
        )

        user_prompt = (
            f"Target name:\n{target_name}\n\n"
            "Candidates:\n" + "\n".join(f"- {c}" for c in candidates) + "\n\n"
            "Respond with exactly one of the candidate lines as-is (no quotes, no JSON)."
        )

        resp = co.chat(
            model="command-r-08-2024",
            message=user_prompt,
            preamble=system_instruction
        )
        choice = (resp.text or "").strip()
        # Strip surrounding quotes if present
        if (choice.startswith('"') and choice.endswith('"')) or (choice.startswith("'") and choice.endswith("'")):
            choice = choice[1:-1].strip()

        if choice in candidates:
            return choice

        # Fall back if AI returned something not in list
        raise RuntimeError("AI choice not in candidates; using fallback")
    except Exception as _:
        # Fallback: best similarity
        best = None
        best_score = -1.0
        for c in candidates:
            score = _similarity(target_name, c)
            if score > best_score:
                best, best_score = c, score
        return best or target_name