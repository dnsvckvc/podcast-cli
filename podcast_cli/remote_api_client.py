import os
import time
import logging
import requests
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()


class RemoteAPIClient:
    """
    Client for communicating with the remote Podcast Summarizer API.
    
    Handles authentication, task submission, status polling, and result retrieval
    from the Hugging Face hosted API endpoint.
    """

    def __init__(self, api_url: str = None, timeout: int = 300):
        """
        Initialize API client.
        
        Args:
            api_url (str): API base URL (default: HF space URL)
            timeout (int): Default request timeout in seconds
        """
        self.api_url = api_url or "https://dnsvckvc-podcast-transcriber.hf.space"
        self.timeout = timeout
        self.token = None
        self.session = requests.Session()
        self.session.timeout = timeout
        
        # Setup logging
        self.logger = logging.getLogger("remote_api_client")
        
        # Get credentials from environment
        self.username = os.getenv("API_USERNAME")
        self.password = os.getenv("API_PASSWORD")
        
        if not self.username or not self.password:
            raise ValueError(
                "API_USERNAME and API_PASSWORD environment variables must be set for remote processing"
            )

    def authenticate(self) -> str:
        """
        Authenticate with the API and store the token.
        
        Returns:
            str: Authentication token
            
        Raises:
            Exception: If authentication fails
        """
        self.logger.info("Authenticating with remote API...")
        
        login_data = {
            "username": self.username,
            "password": self.password
        }
        
        try:
            response = self.session.post(
                f"{self.api_url}/api/auth/login", 
                json=login_data
            )
            response.raise_for_status()
            
            data = response.json()
            if data.get("success"):
                self.token = data["token"]
                self.logger.info("Authentication successful")
                return self.token
            else:
                raise Exception(f"Authentication failed: {data.get('error', 'Unknown error')}")
                
        except requests.RequestException as e:
            raise Exception(f"Authentication request failed: {str(e)}")

    def _get_headers(self) -> Dict[str, str]:
        """Get headers with authentication token."""
        if not self.token:
            self.authenticate()
        
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def _handle_auth_retry(self, func, *args, **kwargs):
        """Handle requests with automatic re-authentication on 401 errors."""
        try:
            return func(*args, **kwargs)
        except requests.HTTPError as e:
            if e.response.status_code == 401:
                self.logger.warning("Authentication expired, re-authenticating...")
                self.token = None  # Clear expired token
                self.authenticate()  # Get new token
                # Update headers in kwargs if present
                if 'headers' in kwargs:
                    kwargs['headers'] = self._get_headers()
                return func(*args, **kwargs)  # Retry with new token
            else:
                raise

    def submit_task(self, source_url: str, platform: str, 
                   episode_name: Optional[str] = None, 
                   detail_level: float = 0.5) -> str:
        """
        Submit a processing task to the API.
        
        Args:
            source_url (str): Source URL to process
            platform (str): Platform type ('youtube' or 'rss')
            episode_name (Optional[str]): Episode name for RSS feeds
            detail_level (float): Summary detail level (0.0-1.0)
            
        Returns:
            str: Task ID for status tracking
            
        Raises:
            Exception: If task submission fails
        """
        self.logger.info(f"Submitting task for {platform}: {source_url}")
        
        task_data = {
            "source_url": source_url,
            "episode_name": episode_name,
            "detail_level": detail_level,
            "platform": platform
        }
        
        def _submit():
            response = self.session.post(
                f"{self.api_url}/api/summarize",
                json=task_data,
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response
        
        try:
            response = self._handle_auth_retry(_submit)
            
            data = response.json()
            if data.get("success"):
                task_id = data["task_id"]
                self.logger.info(f"Task submitted successfully: {task_id}")
                return task_id
            else:
                errors = data.get("errors", data.get("error", "Unknown error"))
                raise Exception(f"Task submission failed: {errors}")
                
        except requests.RequestException as e:
            raise Exception(f"Task submission request failed: {str(e)}")

    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current status of a task.
        
        Args:
            task_id (str): Task ID to check
            
        Returns:
            Optional[Dict[str, Any]]: Task status information or None if not found
        """
        def _get_status():
            response = self.session.get(
                f"{self.api_url}/api/status/{task_id}",
                headers=self._get_headers()
            )
            
            if response.status_code == 404:
                return None
                
            response.raise_for_status()
            return response
        
        try:
            response = self._handle_auth_retry(_get_status)
            
            if response is None:
                return None
            
            data = response.json()
            if data.get("success"):
                return data["task"]
            
            return None
            
        except requests.RequestException as e:
            self.logger.warning(f"Failed to get task status: {str(e)}")
            return None

    def wait_for_completion(self, task_id: str, max_wait_minutes: int = 30, 
                          progress_callback=None) -> Dict[str, Any]:
        """
        Wait for task completion and return the result.
        
        Args:
            task_id (str): Task ID to monitor
            max_wait_minutes (int): Maximum wait time in minutes
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dict[str, Any]: Task result data
            
        Raises:
            Exception: If task fails or times out
        """
        self.logger.info(f"Waiting for task {task_id} to complete...")
        
        max_attempts = max_wait_minutes * 6  # Check every 10 seconds
        
        for attempt in range(max_attempts):
            task_info = self.get_task_status(task_id)
            
            if not task_info:
                raise Exception(f"Could not get status for task {task_id}")
            
            status = task_info.get("status")
            progress = task_info.get("progress", 0)
            message = task_info.get("message", "")
            
            # Call progress callback if provided
            if progress_callback:
                progress_callback(status, progress, message)
            
            # Log progress periodically
            if attempt % 6 == 0:  # Every minute
                self.logger.info(f"Task {task_id}: {status} - {progress}% - {message}")
            
            if status == "completed":
                result = task_info.get("result")
                if result:
                    self.logger.info(f"Task {task_id} completed successfully!")
                    return result
                else:
                    raise Exception("Task completed but no result returned")
                    
            elif status == "failed":
                error = task_info.get("error", "Unknown error")
                raise Exception(f"Task failed: {error}")
            
            time.sleep(10)
        
        raise Exception(f"Task {task_id} timed out after {max_wait_minutes} minutes")

    def validate_url(self, url: str, platform: str) -> Dict[str, Any]:
        """
        Validate a URL using the API.
        
        Args:
            url (str): URL to validate
            platform (str): Platform type
            
        Returns:
            Dict[str, Any]: Validation result
        """
        validation_data = {
            "url": url,
            "platform": platform
        }
        
        def _validate():
            response = self.session.post(
                f"{self.api_url}/api/validate",
                json=validation_data,
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response
        
        try:
            response = self._handle_auth_retry(_validate)
            
            return {
                "valid": response.status_code == 200,
                "response": response.json() if response.status_code == 200 else response.text
            }
            
        except requests.RequestException as e:
            return {
                "valid": False,
                "error": f"Validation request failed: {str(e)}"
            }

    def get_api_info(self) -> Dict[str, Any]:
        """Get API information and health status."""
        try:
            response = self.session.get(f"{self.api_url}/")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {"error": f"Failed to get API info: {str(e)}"}