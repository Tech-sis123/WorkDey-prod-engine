import requests
from config import Config

def list_models():
    res = requests.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {Config.GROQ_API_KEY}"}
    )
    if res.ok:
        data = res.json()
        models = [m["id"] for m in data.get("data", [])]
        print("Available models:", models)
    else:
        print("Error:", res.status_code, res.text)

if __name__ == "__main__":
    list_models()
