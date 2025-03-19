"""
This is a script that will review a PR and provide feedback on the changes. 
"""
import os
import requests
import PyPDF2
import subprocess
import json

# Set environment variables
gh_token = os.getenv("GITHUB_TOKEN")
repo = os.getenv("GITHUB_REPOSITORY")
event_path = os.getenv("GITHUB_EVENT_PATH")

# Parse PR number from GitHub event
with open(event_path, "r") as f:
    event_data = json.load(f)
pr_number = event_data["number"]


# Get changed .proto files from GitHub PR
def get_changed_proto_files(repo, pr_number):
    """
    Get changed .proto files from GitHub PR
    """
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files"
    headers = {"Authorization": f"Bearer {gh_token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    files = response.json()
    return [file["filename"] for file in files if file["filename"].endswith(".proto")]


# Extract text from API design guide PDF
def extract_guide_text(pdf_path):
    """
    Extract text from API design guide PDF
    """
    try:
        guide_text = ""
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            if len(reader.pages) == 0:
                raise ValueError("PDF file is empty")
            for page in reader.pages:
                guide_text += page.extract_text()
        
        if not guide_text.strip():
            raise ValueError("No text extracted from PDF")
        return guide_text
    except Exception as e:
        print(f"Error extracting guide text: {str(e)}")
        return "Please follow standard Protocol Buffer API design best practices."


# Analyze diff with llama2
def analyze_proto_diff(diff, guide_text):
    """
    Analyze diff with llama2
    """
    system_prompt = """You are an expert API design reviewer specialized in Protocol Buffers."""


    prompt=f"""Review the following Protocol Buffer changes and provide specific feedback in this exact format:

    # Protocol Buffer Review

    ## File: [filename]

    ### Issues Found:
    - ❌ Line [number]: [Issue description]
      * Violation: [Cite specific guideline text]
      * Solution: [Proposed fix]

    ### Suggestions:
    - 🟡 Line [number]: [Suggestion description]
      * Reference: [Cite specific guideline text]
      * Recommendation: [Proposed improvement]

    ### Good Practices:
    - ✅ Line [number]: [Description of good practice]
      * Reason: [Why this is good]

    Guidelines to check against, you must use these guidelines to provide feedback:
    {guide_text}

    Important:
    - Every issue (❌) and suggestion (🟡) MUST cite specific guidelines
    - Focus on API design best practices, naming conventions, and Proto3 standards ONLY using the design document provided.
    - Provide specific line numbers for each comment and feedback you provide.
    - Give actionable solutions for each issue
    - DO NOT provide any other feedback, DO NOT provide every DIFF, just the feedback you have. 
    - USE the EMOJIS to provide feedback, they are important in the formatting and styling of the feedback.
    - USE the ONLY the guidelines provided to you to provide feedback. 

    Here is the diff:
    {diff}
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    # Define the payload for the POST request
    payload = {
        "model": "llama2",
        "messages": messages,
        "stream": False,  # Set to True if you prefer streaming responses
    }

    # Define the headers, including the content type
    headers = {"Content-Type": "application/json"}

    # Send the POST request to the Ollama server's /api/chat endpoint
    response = requests.post(
        "http://localhost:11434/api/chat", headers=headers, data=json.dumps(payload)
    )

    # Check if the request was successful
    if response.status_code == 200:
        # Parse the JSON response
        response_data = response.json()
        # Extract and return the assistant's message content
        return response_data.get("message", {}).get("content", "")
    else:
        # Handle the error appropriately
        raise Exception(
            f"Request failed with status code {response.status_code}: {response.text}"
        )


# Post feedback comment to GitHub PR
def post_comment(repo, pr_number, feedback):
    """
    Post feedback comment to GitHub PR
    """
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {"Authorization": f"Bearer {gh_token}"}
    response = requests.post(url, headers=headers, json={"body": feedback})
    response.raise_for_status()


# Main execution
if __name__ == "__main__":
    proto_files = get_changed_proto_files(repo, pr_number)

    if not proto_files:
        print("No .proto file changes detected.")
        exit(0)

    guide_text = extract_guide_text(".github/api_design_guide.pdf")
    
    # Collect feedback for all files
    all_feedback = "# Protocol Buffer API Review\n\n"
    
    for proto_file in proto_files:
        diff = subprocess.check_output(
            ["git", "diff", "origin/main", proto_file]
        ).decode()
        
        # Add file separator and feedback
        file_feedback = analyze_proto_diff(diff, guide_text)
        all_feedback += f"\n---\n\n{file_feedback}\n"
    
    # Add summary section
    all_feedback += "\n## Summary\nPlease address all ❌ issues and consider the 🟡 suggestions for better API design."
    
    # Post combined feedback
    post_comment(repo, pr_number, all_feedback)

    print("Review feedback posted successfully!")
