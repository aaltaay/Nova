import os
from dotenv import load_dotenv
import requests

def verify_alpaca_connection():
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    load_dotenv(env_path)
    
    api_key = os.getenv("APCA_API_KEY_ID")
    api_secret = os.getenv("APCA_API_SECRET_KEY")
    base_url = os.getenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
    
    if not api_key or not api_secret:
        print("[ERROR] API Keys are missing in .env file.")
        return False
        
    print(f"Connecting to Alpaca via: {base_url}")
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret
    }
    
    try:
        response = requests.get(f"{base_url}/v2/account", headers=headers)
        if response.status_code == 200:
            print("[SUCCESS] Successfully authenticated with Alpaca Market Data!")
            account = response.json()
            print(f"Account Status: {account.get('status')}")
            return True
        else:
            print(f"[FAILED] Failed to connect. Status Code: {response.status_code}")
            print(f"Details: {response.text}")
            return False
            
    except Exception as e:
        print(f"[EXCEPTION] Exception occurred: {e}")
        return False

if __name__ == "__main__":
    verify_alpaca_connection()
