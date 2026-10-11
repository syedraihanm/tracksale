"""Generate Fernet encryption key and secret key."""
import secrets

from cryptography.fernet import Fernet


def main():
    fernet_key = Fernet.generate_key().decode()
    secret_key = secrets.token_urlsafe(32)
    print(f"PASSCODE_ENCRYPTION_KEY={fernet_key}")
    print(f"SECRET_KEY={secret_key}")


if __name__ == "__main__":
    main()
