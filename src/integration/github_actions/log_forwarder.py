"""
GitHub Actions Log Forwarder

Executes shell commands with real-time stdout/stderr capture and progressive forwarding
to the Log Pipeline API. Implements buffering, chunking, retries, and deduplication.

Key features:
- Real-time capture of command output
- Configurable chunking (by lines, bytes, or time)
- Automatic retry with exponential backoff
- Duplicate prevention via event_id
- Secret redaction support
- Multi-job isolation
- Graceful finalization on command completion or failure
"""

import hashlib
import json
import logging
import os
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class LogBuffer:
    """Manages buffering and chunking of log output."""

    def __init__(
        self,
        max_lines: int = 100,
        max_bytes: int = 50000,
        max_seconds: float = 5.0,
        on_chunk_ready: Optional[Callable[[str, str], None]] = None,
    ):
        """
        Initialize buffer.
        
        Args:
            max_lines: Flush when buffer reaches this many lines
            max_bytes: Flush when buffer reaches this many bytes
            max_seconds: Flush if this long has passed since last flush
            on_chunk_ready: Callback(chunk_text, event_id) when buffer is ready to flush
        """
        self.max_lines = max_lines
        self.max_bytes = max_bytes
        self.max_seconds = max_seconds
        self.on_chunk_ready = on_chunk_ready

        self.lines: List[str] = []
        self.bytes_count = 0
        self.last_flush_time = time.time()
        self.lock = threading.Lock()
        self.chunk_sequence = 0

    def add(self, text: str) -> None:
        """Add text to buffer and check if flush is needed."""
        with self.lock:
            new_lines = text.split("\n")
            for line in new_lines:
                if line:  # Skip empty lines from split
                    self.lines.append(line)
                    self.bytes_count += len(line.encode("utf-8")) + 1  # +1 for newline

            if self._should_flush():
                self._flush()

    def flush(self) -> None:
        """Force flush current buffer."""
        with self.lock:
            if self.lines:
                self._flush()

    def _should_flush(self) -> bool:
        """Check if any flush condition is met."""
        if len(self.lines) >= self.max_lines:
            return True
        if self.bytes_count >= self.max_bytes:
            return True
        if time.time() - self.last_flush_time >= self.max_seconds:
            return True
        return False

    def _flush(self) -> None:
        """Flush accumulated lines and call callback."""
        if not self.lines:
            return

        chunk_text = "\n".join(self.lines)
        event_id = f"chunk_{self.chunk_sequence}_{uuid.uuid4().hex[:8]}"
        self.chunk_sequence += 1

        if self.on_chunk_ready:
            self.on_chunk_ready(chunk_text, event_id)

        self.lines = []
        self.bytes_count = 0
        self.last_flush_time = time.time()


class SecretRedactor:
    """Redacts secrets from log output."""

    def __init__(self):
        """Initialize with patterns for common secrets."""
        self.patterns = [
            # AWS keys
            (r"(aws_access_key_id\s*=\s*)[^\s]+", r"\1***REDACTED***"),
            (r"(aws_secret_access_key\s*=\s*)[^\s]+", r"\1***REDACTED***"),
            (r"AKIA[0-9A-Z]{16}", "***REDACTED***"),
            # GitHub tokens
            (r"(github_token\s*=\s*)[^\s]+", r"\1***REDACTED***"),
            (r"ghp_[a-zA-Z0-9]{36}", "***REDACTED***"),
            (r"ghs_[a-zA-Z0-9]{36}", "***REDACTED***"),
            # Generic API keys
            (r"(api[_-]?key\s*[:=]\s*)[^\s]+", r"\1***REDACTED***"),
            (r"(Authorization\s*:\s*Bearer\s+)[^\s]+", r"\1***REDACTED***"),
            # Passwords
            (r"(password\s*[:=]\s*)[^\s]+", r"\1***REDACTED***"),
        ]

    def redact(self, text: str) -> str:
        """Redact secrets from text."""
        for pattern, replacement in self.patterns:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        return text


class APIClient:
    """Client for communicating with the Log Pipeline API."""

    def __init__(
        self,
        api_url: str,
        api_key: Optional[str] = None,
        verify_ssl: bool = True,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """
        Initialize API client.
        
        Args:
            api_url: Base URL of the Log Pipeline API (e.g., https://localhost:8000)
            api_key: API key for authentication (from DEMO_API_KEY env var)
            verify_ssl: Whether to verify SSL certificates
            max_retries: Maximum number of retries for failed requests
            retry_delay: Initial delay between retries (seconds)
        """
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.verify_ssl = verify_ssl
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.redactor = SecretRedactor()
        self.submitted_event_ids: set = set()  # Track submitted event IDs for deduplication

    def create_run(
        self,
        repo_id: str,
        commit_sha: str,
        branch: str = "main",
        is_pr: bool = False,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Create a new run in the Log Pipeline.
        
        Returns:
            (success, run_id, error_message)
        """
        endpoint = f"{self.api_url}/api/demo/runs"
        payload = {
            "repo_id": repo_id,
            "commit_sha": commit_sha,
            "branch": branch,
            "is_pr": is_pr,
            "runtime_model": "logistic_regression",
            "auto_advance": False,  # Don't auto-advance; let log ingestion drive it
        }

        try:
            response = self._make_request("POST", endpoint, json=payload)
            if response.status_code == 200:
                data = response.json()
                run_id = data.get("run_id")
                logger.info(f"Created run: {run_id}")
                return True, run_id, None
            else:
                error = response.text
                logger.error(f"Failed to create run: {response.status_code} - {error}")
                return False, None, error
        except Exception as e:
            logger.error(f"Exception creating run: {e}")
            return False, None, str(e)

    def ingest_chunk(
        self,
        run_id: str,
        log_chunk: str,
        event_id: str,
        step_name: str = "Execute Step",
        stage: str = "execution",
        ci_run_id: Optional[str] = None,
        commit_sha: Optional[str] = None,
        step_outcome: Optional[str] = None,
        workflow_outcome: Optional[str] = None,
        exit_code: Optional[int] = None,
        is_final: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """
        Ingest a log chunk into the Log Pipeline.
        
        Returns:
            (success, error_message)
        """
        # Check for duplicate submission
        if event_id in self.submitted_event_ids:
            logger.debug(f"Duplicate event_id ignored: {event_id}")
            return True, None  # Treat as success (idempotent)

        endpoint = f"{self.api_url}/api/demo/runs/{run_id}/logs"
        
        # Redact secrets
        redacted_chunk = self.redactor.redact(log_chunk)
        
        payload = {
            "log_chunk": redacted_chunk,
            "event_id": event_id,
            "step_name": step_name,
            "stage": stage,
            "ci_run_id": ci_run_id,
            "commit_sha": commit_sha,
            "step_outcome": step_outcome,
            "workflow_outcome": workflow_outcome,
            "exit_code": exit_code,
            "is_final": is_final,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            response = self._make_request("POST", endpoint, json=payload)
            if response.status_code in (200, 201):
                self.submitted_event_ids.add(event_id)
                logger.debug(f"Ingested chunk {event_id}: {len(log_chunk)} bytes")
                return True, None
            else:
                error = response.text[:200]  # Truncate for logging
                # For 5xx errors that were retried, log as retriable
                if response.status_code in (500, 502, 503, 504):
                    logger.warning(
                        f"Failed to ingest chunk (transient error {response.status_code}): {error}"
                    )
                else:
                    # 4xx errors are permanent
                    logger.error(f"Failed to ingest chunk ({response.status_code}): {error}")
                return False, error
        except Exception as e:
            logger.error(f"Exception ingesting chunk: {e}")
            return False, str(e)

    def finalize_run(
        self,
        run_id: str,
        workflow_outcome: str,
        ci_run_id: Optional[str] = None,
        commit_sha: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Send finalization event for the run.
        
        Returns:
            (success, error_message)
        """
        endpoint = f"{self.api_url}/api/demo/runs/{run_id}/logs"
        
        payload = {
            "log_chunk": "",  # Empty chunk for finalization
            "event_id": f"final_{uuid.uuid4().hex[:8]}",
            "step_name": "Workflow Finalization",
            "stage": "finalization",
            "ci_run_id": ci_run_id,
            "commit_sha": commit_sha,
            "workflow_outcome": workflow_outcome,
            "is_final": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            response = self._make_request("POST", endpoint, json=payload)
            if response.status_code in (200, 201):
                logger.info(f"Finalized run {run_id} with outcome: {workflow_outcome}")
                return True, None
            else:
                error = response.text[:200]
                if response.status_code in (500, 502, 503, 504):
                    logger.warning(
                        f"Failed to finalize run (transient error {response.status_code}): {error}"
                    )
                else:
                    logger.error(f"Failed to finalize run ({response.status_code}): {error}")
                return False, error
        except Exception as e:
            logger.error(f"Exception finalizing run: {e}")
            return False, str(e)

    def _make_request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        """
        Make HTTP request with intelligent retries and authentication.
        
        Retries on:
        - Connection errors, timeouts, network failures
        - HTTP 500, 502, 503, 504 (transient server errors)
        
        Does NOT retry on:
        - HTTP 400, 401, 403, 404 (client errors)
        
        Raises:
        - Last exception if all retries exhausted
        """
        headers = kwargs.get("headers", {})
        
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        
        kwargs["headers"] = headers
        kwargs["verify"] = self.verify_ssl
        
        last_exception = None
        last_response = None
        
        for attempt in range(self.max_retries):
            try:
                if method == "POST":
                    response = requests.post(url, timeout=10, **kwargs)
                elif method == "GET":
                    response = requests.get(url, timeout=10, **kwargs)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                # Check if response is a permanent client error (do not retry)
                if response.status_code in (400, 401, 403, 404):
                    logger.error(
                        f"Permanent client error ({response.status_code}): {response.text[:200]}"
                    )
                    return response  # Return immediately, do not retry
                
                # Check if response is a transient server error (retry)
                if response.status_code in (500, 502, 503, 504):
                    last_response = response
                    if attempt < self.max_retries - 1:
                        wait_time = self.retry_delay * (2 ** attempt)
                        logger.warning(
                            f"Transient server error {response.status_code} "
                            f"(attempt {attempt + 1}/{self.max_retries}), "
                            f"retrying in {wait_time}s"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"Server error {response.status_code} after {self.max_retries} attempts")
                        return response  # Return final failed response
                
                # Success or other non-retryable status
                return response
                
            except requests.exceptions.ConnectionError as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Connection error (attempt {attempt + 1}/{self.max_retries}), "
                        f"retrying in {wait_time}s: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Connection error after {self.max_retries} attempts: {e}")
                    
            except requests.exceptions.Timeout as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Timeout (attempt {attempt + 1}/{self.max_retries}), "
                        f"retrying in {wait_time}s: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Timeout after {self.max_retries} attempts: {e}")
                    
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{self.max_retries}), "
                        f"retrying in {wait_time}s: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request failed after {self.max_retries} attempts: {e}")
        
        # All retries exhausted
        if last_exception:
            logger.error(f"Request failed permanently after {self.max_retries} attempts")
            raise last_exception
        elif last_response:
            logger.error(f"Request returned persistent error {last_response.status_code}")
            return last_response
        else:
            raise RuntimeError("Request failed with unknown error after all retries")


class CommandExecutor:
    """Executes shell commands with real-time log forwarding."""

    def __init__(
        self,
        api_client: APIClient,
        run_id: str,
        ci_run_id: str,
        commit_sha: str,
        job_name: str = "default",
        strict_mode: bool = True,
    ):
        """
        Initialize command executor.
        
        Args:
            api_client: APIClient instance for uploading logs
            run_id: Log Pipeline run ID
            ci_run_id: GitHub Actions run ID
            commit_sha: Git commit SHA
            job_name: GitHub Actions job name
            strict_mode: If True, fail job if log forwarding fails; otherwise best-effort
        """
        self.api_client = api_client
        self.run_id = run_id
        self.ci_run_id = ci_run_id
        self.commit_sha = commit_sha
        self.job_name = job_name
        self.strict_mode = strict_mode
        self.forwarder_errors: List[str] = []

    def execute(
        self,
        command: str,
        step_name: str = "Execute Step",
        stage: str = "execution",
    ) -> int:
        """
        Execute a shell command with real-time log forwarding.
        
        Args:
            command: Shell command to execute
            step_name: Name of the step (for logging)
            stage: Pipeline stage (setup, build, test, etc.)
        
        Returns:
            Exit code of the command
        """
        logger.info(f"Executing command: {command}")
        
        buffer = LogBuffer(
            max_lines=100,
            max_bytes=50000,
            max_seconds=5.0,
            on_chunk_ready=self._on_chunk_ready,
        )
        
        self.current_step_name = step_name
        self.current_stage = stage
        
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            
            # Read output line-by-line and add to buffer
            for line in iter(process.stdout.readline, ""):
                if line:
                    # Display to console
                    print(line.rstrip())
                    # Add to buffer
                    buffer.add(line)
            
            # Wait for process to complete
            exit_code = process.wait()
            
            # Flush remaining buffer
            buffer.flush()
            
            # Determine step outcome
            step_outcome = "success" if exit_code == 0 else "failure"
            
            logger.info(f"Command completed with exit code: {exit_code}")
            
            return exit_code
        
        except Exception as e:
            error_msg = f"Command execution error: {e}"
            logger.error(error_msg)
            if self.strict_mode:
                raise
            self.forwarder_errors.append(error_msg)
            return 1

    def _on_chunk_ready(self, chunk_text: str, event_id: str) -> None:
        """Callback when a log chunk is ready to be sent."""
        try:
            success, error = self.api_client.ingest_chunk(
                run_id=self.run_id,
                log_chunk=chunk_text,
                event_id=event_id,
                step_name=getattr(self, "current_step_name", "Execute Step"),
                stage=getattr(self, "current_stage", "execution"),
                ci_run_id=self.ci_run_id,
                commit_sha=self.commit_sha,
                step_outcome=None,  # Only set on finalization
                exit_code=None,  # Only set on finalization
                is_final=False,
            )
            
            if not success:
                error_msg = f"Failed to ingest chunk {event_id}: {error}"
                logger.warning(error_msg)
                if self.strict_mode:
                    raise RuntimeError(error_msg)
                self.forwarder_errors.append(error_msg)
        
        except Exception as e:
            error_msg = f"Exception sending chunk: {e}"
            logger.error(error_msg)
            if self.strict_mode:
                raise
            self.forwarder_errors.append(error_msg)

    def finalize(self, workflow_outcome: str = "success") -> None:
        """Send finalization event."""
        success, error = self.api_client.finalize_run(
            run_id=self.run_id,
            workflow_outcome=workflow_outcome,
            ci_run_id=self.ci_run_id,
            commit_sha=self.commit_sha,
        )
        
        if not success:
            error_msg = f"Failed to finalize run: {error}"
            logger.warning(error_msg)
            if self.strict_mode:
                raise RuntimeError(error_msg)
            self.forwarder_errors.append(error_msg)


def run_with_forwarding(
    api_url: str,
    api_key: Optional[str],
    repo_id: str,
    commit_sha: str,
    ci_run_id: str,
    branch: str = "main",
    is_pr: bool = False,
    job_name: str = "default",
    commands: Optional[List[Dict[str, str]]] = None,
    strict_mode: bool = True,
) -> int:
    """
    High-level function to run commands with log forwarding.
    
    Args:
        api_url: Base URL of the Log Pipeline API
        api_key: API key for authentication
        repo_id: Repository identifier
        commit_sha: Commit SHA
        ci_run_id: GitHub Actions run ID
        branch: Git branch
        is_pr: Whether this is a PR
        job_name: Job name
        commands: List of commands to execute, each with 'cmd', 'step_name', 'stage'
        strict_mode: If True, fail if log forwarding fails
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    logger.info(f"Starting log forwarding run: repo={repo_id}, commit={commit_sha}")
    
    # Initialize API client
    api_client = APIClient(api_url, api_key, verify_ssl=True, max_retries=3)
    
    # Create run
    success, run_id, error = api_client.create_run(
        repo_id=repo_id,
        commit_sha=commit_sha,
        branch=branch,
        is_pr=is_pr,
    )
    
    if not success:
        logger.error(f"Failed to create run: {error}")
        return 1
    
    # Initialize executor
    executor = CommandExecutor(
        api_client=api_client,
        run_id=run_id,
        ci_run_id=ci_run_id,
        commit_sha=commit_sha,
        job_name=job_name,
        strict_mode=strict_mode,
    )
    
    # Execute commands
    exit_code = 0
    if commands:
        for cmd_spec in commands:
            cmd = cmd_spec.get("cmd")
            step_name = cmd_spec.get("step_name", "Execute Step")
            stage = cmd_spec.get("stage", "execution")
            
            cmd_exit_code = executor.execute(cmd, step_name, stage)
            if cmd_exit_code != 0:
                exit_code = cmd_exit_code  # Preserve failure status
    
    # Finalize run
    workflow_outcome = "failure" if exit_code != 0 else "success"
    executor.finalize(workflow_outcome)
    
    logger.info(f"Run completed with exit code: {exit_code}")
    
    return exit_code
