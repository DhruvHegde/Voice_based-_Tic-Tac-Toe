#!/usr/bin/env python3
"""
GitHub Actions Log Forwarding Wrapper

Usage:
    python gh_run_with_logs.py --api-url <url> --repo <owner/repo> \
        --commit <sha> --run-id <run_id> --command "npm test"

Environment Variables:
    GH_LOG_API_KEY: API key for authentication (optional, uses DEMO_API_KEY if not set)
    GH_LOG_API_URL: Override --api-url via environment
    GH_LOG_STRICT: Set to "0" for best-effort mode (default: strict mode)
"""

import argparse
import logging
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.integration.github_actions.log_forwarder import run_with_forwarding

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Execute commands with log forwarding to Log Pipeline API",
        # Allow positional arguments after known args
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("GH_LOG_API_URL"),
        help="Base URL of the Log Pipeline API (required if GH_LOG_API_URL not set)",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("GH_LOG_API_KEY") or os.getenv("DEMO_API_KEY"),
        help="API key for authentication (optional)",
    )
    parser.add_argument(
        "--repo",
        default=os.getenv("GITHUB_REPOSITORY", "unknown/repo"),
        help="Repository (owner/repo)",
    )
    parser.add_argument(
        "--commit",
        default=os.getenv("GITHUB_SHA", "unknown"),
        help="Commit SHA",
    )
    parser.add_argument(
        "--run-id",
        default=os.getenv("GITHUB_RUN_ID", "0"),
        help="GitHub Actions run ID",
    )
    parser.add_argument(
        "--run-attempt",
        default=os.getenv("GITHUB_RUN_ATTEMPT", "1"),
        help="GitHub Actions run attempt",
    )
    parser.add_argument(
        "--branch",
        default=os.getenv("GITHUB_REF_NAME", "main"),
        help="Branch name",
    )
    parser.add_argument(
        "--job",
        default=os.getenv("GITHUB_JOB", "default"),
        help="Job name",
    )
    parser.add_argument(
        "--is-pr",
        action="store_true",
        default=os.getenv("GITHUB_EVENT_NAME") == "pull_request",
        help="Whether this is a pull request",
    )
    parser.add_argument(
        "--step-name",
        default="Execute Step",
        help="Step name for logging",
    )
    parser.add_argument(
        "--stage",
        default="execution",
        help="Pipeline stage (setup, build, test, teardown)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=os.getenv("GH_LOG_STRICT", "1") != "0",
        help="Fail job if log forwarding fails (default: True)",
    )
    # Remaining positional arguments are the command
    parser.add_argument(
        "command_parts",
        nargs=argparse.REMAINDER,
        help="Command to execute (can be positional args or use --command)",
    )
    
    args = parser.parse_args()
    
    # Handle command: either from positional args or from --command
    if args.command_parts:
        command = " ".join(args.command_parts)
    elif hasattr(args, 'command') and args.command:
        command = args.command
    else:
        parser.error("No command specified. Use positional arguments or implement --command flag.")
    
    logger.info(
        f"Forwarding logs from GitHub Actions: repo={args.repo}, commit={args.commit}"
    )
    
    # Create CI run ID from GitHub context
    ci_run_id = f"gh_{args.run_id}_attempt_{args.run_attempt}"
    
    # Validate required env vars
    if not args.api_url:
        parser.error("GH_LOG_API_URL environment variable or --api-url argument is required")
    
    # Execute command with forwarding
    exit_code = run_with_forwarding(
        api_url=args.api_url,
        api_key=args.api_key,
        repo_id=args.repo,
        commit_sha=args.commit,
        ci_run_id=ci_run_id,
        branch=args.branch,
        is_pr=args.is_pr,
        job_name=args.job,
        commands=[
            {
                "cmd": command,
                "step_name": args.step_name,
                "stage": args.stage,
            }
        ],
        strict_mode=args.strict,
    )
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
