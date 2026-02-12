from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import json

# Load credentials
creds_path = Path('credentials/credentials.json')
token_path = Path('credentials/token.json')

try:
    with open(creds_path) as f:
        creds_data = json.load(f)
        print(f'Credentials loaded from: {creds_path}')
except Exception as e:
    print(f'Error loading credentials: {e}')
    
# Try to authenticate with token
try:
    with open(token_path) as f:
        token_data = json.load(f)
        print(f'Token loaded successfully')
        print(f'Token expires: {token_data.get("expiry", "unknown")}')
except Exception as e:
    print(f'Error loading token: {e}')
    
# Build service and check folders
service = build('drive', 'v3')

# First, check exact folder structure
print('Checking Google Drive folder structure...')

# List files in parent directory
parent_query = "'Bot RPA/Tocornal Export/Operaciones' in parents"
results = service.files().list(pageSize=100, fields='name,parents', q=parent_query)

if results.get('files'):
    parent_folder = results.get('files', [])[0]
    parent_id = parent_folder.get('id')
    print(f'Parent folder found: {parent_folder.get("name")} (ID: {parent_id})')
    
    # List all items in the parent folder
    items = service.files().list(pageSize=100, fields='name,parents', q=f"'{parent_id} in parents'")
    
    print(f'Total items in folder: {len(items.get("files", []))}')
    
    # Categorize items
    folders = []
    files = []
    
    for item in items.get('files', []):
        name = item.get('name', 'Unknown')
        mime_type = item.get('mimeType', 'Unknown')
        is_folder = mime_type == 'application/vnd.google-apps.folder'
        
        if is_folder:
            folders.append(name)
            print(f'FOLDER: {name}')
        else:
            files.append(name)
            print(f'FILE: {name}')
    
    print('Summary:')
    print(f'Folders ({len(folders)}): {", ".join(folders)}')
    print(f'Files ({len(files)}): {", ".join(files)}')
    
    # Check for three key subfolders
    print('Checking for specific folders...')
    
    # Check for "En Proceso" folder
    en_proceso = [f for f in folders if 'En Proceso' in f or 'en proceso' in f.lower()]
    print(f'En Proceso folder: {"EXISTS" if en_proceso else "NOT FOUND"}')
    
    # Check for "Consolidado" folder  
    consolidado = [f for f in folders if 'Consolidado' in f or f.lower() == 'consolidado']
    print(f'Consolidado folder: {"EXISTS" if consolidado else "NOT FOUND"}')
    
    # Check if there are any source files (XLSX) in root
    xlsx_files = [f for f in files if f.endswith('.xlsx')]
    print(f'Source XLSX files: {len(xlsx_files)}')
    if xlsx_files:
        for xf in xlsx_files[:5]:
            print(f'  - {xf}')
    
except Exception as e:
    print(f'Error: {e}')
