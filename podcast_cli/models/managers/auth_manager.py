import os
import logging

from dotenv import load_dotenv
from flask_jwt_extended import create_access_token

logger = logging.getLogger(__name__)

load_dotenv(override=True)

DEFAULT_USERNAME = os.getenv("DEFAULT_USERNAME")
DEFAULT_PASSWORD = os.getenv("DEFAULT_PASSWORD")


class AuthManager:
    def __init__(self):
        """Initialize JWT authentication manager"""
        self.valid_credentials = {
            "username": DEFAULT_USERNAME,
            "password": DEFAULT_PASSWORD,
        }

    def authenticate_user(self, username: str, password: str) -> dict:
        """Authenticate user with simple credentials"""
        if (
            username == self.valid_credentials["username"]
            and password == self.valid_credentials["password"]
        ):
            return {"username": username, "role": "admin"}
        return None

    def create_token(self, username: str) -> str:
        """Create JWT token for authenticated user"""
        return create_access_token(identity=username)
