
import secrets
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def generate_api_key() -> str:
    random_part = secrets.token_urlsafe(32)
    return f"sk_live_{random_part}"

def hash_key(key: str) -> str:
    return pwd_context.hash(key)

if __name__ == "__main__":
    key = generate_api_key()
    print(f"Generated Key: {key}")
    print(f"Key Length: {len(key)}")
    
    try:
        hashed = hash_key(key)
        print(f"Hashed Key: {hashed}")
        print("Success!")
    except Exception as e:
        print(f"Error: {e}")
