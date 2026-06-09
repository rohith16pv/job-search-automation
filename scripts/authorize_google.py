"""
One-time Google OAuth authorization.

Run this once to authorize access to Google Docs and Sheets:

    python scripts/authorize_google.py

A browser window will open asking you to sign in with your Google account
and grant the app access. The token is saved to config/google_token.json
and used automatically on every subsequent run — you won't need to do this again
unless you revoke access or delete the token file.

Requirements already in requirements.txt:
  google-auth-oauthlib, google-auth-httplib2, google-api-python-client
"""
import os
import sys

# Allow running from project root or from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

_SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
_CREDS_PATH = os.environ.get(
    "GOOGLE_OAUTH_CREDENTIALS",
    os.path.join(_PROJECT_ROOT, "config", "google_oauth_credentials.json"),
)
_TOKEN_PATH = os.environ.get(
    "GOOGLE_TOKEN_PATH",
    os.path.join(_PROJECT_ROOT, "config", "google_token.json"),
)


def main():
    if not os.path.exists(_CREDS_PATH):
        print(f"ERROR: credentials file not found at:\n  {_CREDS_PATH}")
        print("\nExpected the OAuth client secret JSON downloaded from Google Cloud Console.")
        sys.exit(1)

    if os.path.exists(_TOKEN_PATH):
        print(f"Token already exists at: {_TOKEN_PATH}")
        # Try loading and validating it
        try:
            creds = Credentials.from_authorized_user_file(_TOKEN_PATH, _SCOPES)
            if creds.valid:
                print("✓ Token is valid — nothing to do.")
                print("\nTo re-authorize, delete the token file and re-run this script.")
                return
            print("Token exists but is expired/invalid — re-authorizing...")
        except Exception as e:
            print(f"Token file is unreadable ({e}) — re-authorizing...")

    print("Opening browser for Google authorization...")
    print("Sign in with the Google account that owns your Docs and Sheets.\n")

    flow = InstalledAppFlow.from_client_secrets_file(_CREDS_PATH, _SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")

    os.makedirs(os.path.dirname(_TOKEN_PATH), exist_ok=True)
    with open(_TOKEN_PATH, "w") as f:
        f.write(creds.to_json())

    print(f"\n✓ Authorization successful!")
    print(f"  Token saved to: {_TOKEN_PATH}")
    print("\nYou can now run the orchestrator:")
    print("  python orchestrator.py --dry-run")


if __name__ == "__main__":
    main()
