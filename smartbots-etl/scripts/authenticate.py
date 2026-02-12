"""Google OAuth authentication script for generating and refreshing tokens.

Usage:
    python scripts/authenticate.py                    # Authenticate with both Drive and Gmail scopes
    python scripts/authenticate.py --drive-only       # Authenticate with Drive scopes only
    python scripts/authenticate.py --gmail-only       # Authenticate with Gmail scopes only
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("❌ Missing required packages. Install with:")
    print("   pip install google-auth-oauthlib")
    sys.exit(1)

# Google API scopes
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def authenticate(
    credentials_path: str,
    token_path: str,
    scopes: list[str],
    force_refresh: bool = False,
) -> Credentials:
    """Authenticate with Google OAuth and return credentials.

    Args:
        credentials_path: Path to OAuth client credentials (credentials.json)
        token_path: Path to save/load token (token.json)
        scopes: OAuth scopes to request
        force_refresh: If True, force re-authentication even if token exists

    Returns:
        OAuth Credentials object
    """
    creds_path = Path(token_path)
    creds = None

    # Load existing token if available
    if creds_path.exists() and not force_refresh:
        with open(creds_path) as f:
            token_data = json.load(f)
        creds = Credentials.from_authorized_user_info(token_data, scopes)

        # Refresh if expired
        if creds and creds.expired and creds.refresh_token:
            print(f"🔄 Token expired, refreshing...")
            creds.refresh(Request())
            _save_token(creds, creds_path)
            print(f"✅ Token refreshed successfully!")
            return creds

    # If no valid credentials, run OAuth flow
    if not creds or not creds.valid:
        if creds_path.exists() and force_refresh:
            print(f"🔄 Force refresh requested, starting OAuth flow...")

        print(f"🔐 Starting OAuth flow...")
        print(f"📧 Scopes: {', '.join(scopes)}")
        print(f"🌐 A browser window will open for authentication...")

        flow = InstalledAppFlow.from_client_secrets_file(credentials_path, scopes)
        creds = flow.run_local_server(
            port=0,
            prompt="consent",
            access_type="offline",  # Enables refresh token
        )

        _save_token(creds, creds_path)
        print(f"✅ Authentication successful! Token saved to {token_path}")

    return creds


def _save_token(creds: Credentials, token_path: Path) -> None:
    """Save credentials to token file."""
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps(token_data, indent=2))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Authenticate with Google APIs using OAuth2")
    parser.add_argument(
        "--credentials",
        default="credentials/credentials.json",
        help="Path to OAuth client credentials (default: credentials/credentials.json)",
    )
    parser.add_argument(
        "--token",
        default="credentials/token.json",
        help="Path to save/load token (default: credentials/token.json)",
    )
    parser.add_argument(
        "--drive-only",
        action="store_true",
        help="Authenticate with Drive scopes only",
    )
    parser.add_argument(
        "--gmail-only",
        action="store_true",
        help="Authenticate with Gmail scopes only",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force re-authentication even if valid token exists",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.drive_only and args.gmail_only:
        print("❌ Cannot specify both --drive-only and --gmail-only")
        sys.exit(1)

    # Determine scopes
    if args.drive_only:
        scopes = DRIVE_SCOPES
        print("🎯 Drive-only authentication")
    elif args.gmail_only:
        scopes = GMAIL_SCOPES
        print("🎯 Gmail-only authentication")
    else:
        scopes = DRIVE_SCOPES + GMAIL_SCOPES
        print("🎯 Full authentication (Drive + Gmail)")

    # Check if credentials file exists
    creds_file = Path(args.credentials)
    if not creds_file.exists():
        print(f"❌ Credentials file not found: {args.credentials}")
        print(f"\n📋 To create credentials:")
        print(f"   1. Go to: https://console.cloud.google.com/")
        print(f"   2. Create a project or select existing one")
        print(f"   3. Enable Google Drive API and Gmail API")
        print(f"   4. Go to Credentials → Create OAuth 2.0 Client ID")
        print(f"   5. Application type: Desktop app")
        print(f"   6. Download JSON and save as: {args.credentials}")
        sys.exit(1)

    # Authenticate
    try:
        authenticate(
            credentials_path=args.credentials,
            token_path=args.token,
            scopes=scopes,
            force_refresh=args.force_refresh,
        )

        print(f"\n✅ Authentication complete!")
        print(f"📝 Token saved to: {args.token}")
        print(f"\n💡 Next steps:")
        print(f"   - Run: python scripts/test_oauth.py")
        print(f"   - Your app can now use these credentials")

    except Exception as e:
        print(f"\n❌ Authentication failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
