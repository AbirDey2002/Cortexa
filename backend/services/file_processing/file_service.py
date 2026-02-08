import os
import re
from typing import Tuple
from core.config import FileStorageConfigs, HostingConfigs



def sanitize_filename(filename: str) -> str:
    """
    Sanitize the filename to prevent path traversal and other attacks.
    """
    # Get only the base name
    filename = os.path.basename(filename)
    # Remove any characters that aren't alphanumeric, dots, hyphens, or underscores
    filename = re.sub(r'[^a-zA-Z0-9.\-_]', '', filename)
    # Ensure it's not empty and doesn't start with a dot
    if not filename or filename.startswith('.'):
        filename = f"uploaded_file_{os.urandom(4).hex()}"
    return filename








def _save_to_local(file) -> Tuple[bool, str, str | None]:
    try:
        uploads_dir = os.path.join(os.getcwd(), "uploads")
        os.makedirs(uploads_dir, exist_ok=True)
        
        filename = sanitize_filename(file.filename)
        destination_path = os.path.join(uploads_dir, filename)
        
        with open(destination_path, "wb") as out_f:
            out_f.write(file.file.read())
        url = f"{HostingConfigs.URL}/uploads/{filename}"
        return True, f"File '{filename}' saved locally.", url
    except Exception as e:
        return False, f"Error saving file locally: {e}", None


def _upload_to_firebase(file) -> Tuple[bool, str, str | None]:
    try:
        import firebase_admin
        from firebase_admin import credentials, storage
        from core.config import FirebaseConfigs
        
        # Initialize Firebase app if not already initialized
        if not firebase_admin._apps:
            # Check if service account file exists
            if not os.path.exists(FirebaseConfigs.SERVICE_ACCOUNT_PATH):
                return False, f"Service account file not found at {FirebaseConfigs.SERVICE_ACCOUNT_PATH}", None
            
            # Strip gs:// if present in bucket name
            bucket_name = FirebaseConfigs.STORAGE_BUCKET
            if bucket_name.startswith("gs://"):
                bucket_name = bucket_name[5:]
                
            cred = credentials.Certificate(FirebaseConfigs.SERVICE_ACCOUNT_PATH)
            firebase_admin.initialize_app(cred, {
                'storageBucket': bucket_name
            })

            
        bucket = storage.bucket()
        filename = sanitize_filename(file.filename)
        blob = bucket.blob(f"uploads/{filename}")
        
        # Ensure we start reading from the beginning
        file.file.seek(0)
        blob.upload_from_file(file.file, content_type=file.content_type)
        
        # Make public key
        blob.make_public()
        
        return True, f"File '{filename}' uploaded successfully to Firebase Storage.", blob.public_url

    except ImportError:
        return False, "firebase-admin package not installed. Run 'pip install firebase-admin'", None
    except Exception as e:
        return False, f"Error uploading file to Firebase: {e}", None


def upload_file_to_blob(file):
    provider = (FileStorageConfigs.PROVIDER or "local").lower()
    
    if provider == "firebase":
        return _upload_to_firebase(file)
    else:
        # Default to local if not firebase
        return _save_to_local(file)


