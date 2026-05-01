#!/usr/bin/env python3

"""Imprime la URL OAuth de Microsoft para conectar un estudiante."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from integrations.microsoft_graph.auth_client import build_microsoft_oauth_client_from_env


def main() -> int:
    args = _build_parser().parse_args()
    client = build_microsoft_oauth_client_from_env()
    request = client.build_authorization_request(
        student_id=args.student_id,
        state_token=args.state_token,
        redirect_uri=args.redirect_uri,
    )

    if not request.ready or not request.authorization_url:
        print(
            "microsoft_oauth_authorize failed",
            f"error={request.error_code}",
            f"detail={request.detail}",
        )
        return 1

    print("microsoft_oauth_authorize ok")
    print(f"state={request.state}")
    print(f"url={request.authorization_url}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Construye la URL OAuth de Microsoft Graph para un estudiante.",
    )
    parser.add_argument("--student-id", type=int, required=True)
    parser.add_argument("--state-token", default=None)
    parser.add_argument("--redirect-uri", default=None)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
