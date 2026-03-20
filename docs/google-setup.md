# Google Calendar + Gmail Setup

Rook integrates with Google Calendar and Gmail via OAuth 2.0.

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **New Project** → name it "Rook" → Create
3. Select the project

## Step 2: Enable APIs

1. Go to **APIs & Services** → **Library**
2. Search and enable:
   - **Google Calendar API**
   - **Gmail API**

## Step 3: Create OAuth Credentials

1. Go to **APIs & Services** → **Credentials**
2. Click **Create Credentials** → **OAuth client ID**
3. If prompted, configure the OAuth consent screen:
   - User type: **External**
   - App name: "Rook"
   - Add your email as a test user
4. Application type: **Desktop app**
5. Click **Create**
6. Download the JSON file → rename to `credentials.json`
7. Place it in the Rook root directory

## Step 4: Run OAuth Flow

The setup wizard handles this automatically:

```bash
python -m rook.setup
```

Or manually:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]

flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
creds = flow.run_local_server(port=0)

with open("token.json", "w") as f:
    f.write(creds.to_json())
```

This opens a browser for consent. After approving, `token.json` is created automatically.

## Step 5: Verify

```bash
python -m rook.main
```

If you see "Google (Calendar + Gmail)" in the features list, you're good!

## Notes

- `token.json` auto-refreshes. You only need to do the OAuth flow once.
- Keep `credentials.json` and `token.json` private — never commit them.
- If token expires, delete `token.json` and run the flow again.
