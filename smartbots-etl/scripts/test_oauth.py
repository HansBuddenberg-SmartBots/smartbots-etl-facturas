"""Test OAuth authentication and token refresh."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.oauth_google_drive_adapter import OAuthGoogleDriveAdapter
from src.infrastructure.oauth_gmail_notifier import OAuthGmailNotifier

print("Testing OAuth authentication...")

try:
    # Test Drive adapter
    print("\n1. Testing Google Drive connection...")
    drive = OAuthGoogleDriveAdapter(
        credentials_path="credentials/credentials.json",
        token_path="credentials/token.json",
    )

    # Try to list files in root
    print("   Listing files in root folder...")
    files = (
        drive.service.files()
        .list(
            pageSize=5,
            fields="files(id, name)",
        )
        .execute()
    )

    print(f"   ✓ Connected! Found {len(files.get('files', []))} files in root")
    for f in files.get("files", [])[:3]:
        print(f"     - {f['name']} ({f['id']})")

    # Test Gmail notifier
    print("\n2. Testing Gmail connection...")
    gmail = OAuthGmailNotifier(
        credentials_path="credentials/credentials.json",
        token_path="credentials/token.json",
        sender="h.buddenberg@gmail.com",
        templates_dir=Path("src/templates"),
    )
    print("   ✓ Gmail service created (send-only scope)")

    print("\n✅ All OAuth tests passed!")

except Exception as e:
    print(f"\n❌ OAuth test failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
