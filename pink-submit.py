#!/usr/bin/env python3

"""
Pinkcoin raw transaction submitter.

Submits a signed raw transaction from a .signed.hex file directly to the
Pinkcoin JSON-RPC server.

The transaction is read from the file and sent over HTTP JSON-RPC rather
than being passed as a command-line argument. This avoids operating-system
argument-size limitations with large transactions.

Configuration:
    RPC_USER      JSON-RPC username
    RPC_PASSWORD  JSON-RPC password
    RPC_PORT      JSON-RPC port

Usage:
    pink-submit.py <signed-transaction-file>
"""

import base64
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ---------------------------------------------------------------------------
# USER CONFIGURATION
# ---------------------------------------------------------------------------

RPC_USER = "YOUR_RPC_USERNAME"
RPC_PASSWORD = "YOUR_RPC_PASSWORD"
RPC_PORT = 23424  # Change if your Pinkcoin RPC server uses a different port.

# RPC server address. Pinkcoin RPC is normally accessed locally.
RPC_HOST = "127.0.0.1"

# ---------------------------------------------------------------------------

def usage():
    print(f"Usage: {Path(sys.argv[0]).name} <signed-transaction-file>")


def main():
    if len(sys.argv) != 2:
        usage()
        return 1

    tx_file = Path(sys.argv[1])

    if not tx_file.is_file():
        print(f"Error: transaction file not found: {tx_file}", file=sys.stderr)
        return 1

    try:
        tx_hex = tx_file.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError) as e:
        print(f"Error reading transaction file: {e}", file=sys.stderr)
        return 1

    if not tx_hex:
        print("Error: transaction file is empty.", file=sys.stderr)
        return 1

    # Verify that the file contains valid hexadecimal data before sending it.
    try:
        bytes.fromhex(tx_hex)
    except ValueError:
        print(
            "Error: transaction file does not contain valid hexadecimal data.",
            file=sys.stderr,
        )
        return 1

    request_body = json.dumps(
        {
            "jsonrpc": "1.0",
            "id": "pink-submit",
            "method": "sendrawtransaction",
            "params": [tx_hex],
        }
    ).encode("utf-8")

    url = f"http://{RPC_HOST}:{RPC_PORT}/"

    credentials = f"{RPC_USER}:{RPC_PASSWORD}".encode("utf-8")
    auth_header = base64.b64encode(credentials).decode("ascii")

    request = Request(
        url,
        data=request_body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth_header}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            response_body = response.read().decode("utf-8")

    except HTTPError as e:
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            error_body = str(e)

        print(
            f"RPC HTTP error {e.code}: {error_body}",
            file=sys.stderr,
        )
        return 1

    except URLError as e:
        print(
            f"Error connecting to Pinkcoin RPC at {url}: {e.reason}",
            file=sys.stderr,
        )
        return 1

    except TimeoutError:
        print("Error: connection to Pinkcoin RPC timed out.", file=sys.stderr)
        return 1

    try:
        result = json.loads(response_body)
    except json.JSONDecodeError:
        print(
            f"Error: Pinkcoin returned invalid JSON:\n{response_body}",
            file=sys.stderr,
        )
        return 1

    if result.get("error") is not None:
        error = result["error"]

        if isinstance(error, dict):
            code = error.get("code", "unknown")
            message = error.get("message", "unknown RPC error")
            print(
                f"RPC error {code}: {message}",
                file=sys.stderr,
            )
        else:
            print(f"RPC error: {error}", file=sys.stderr)

        return 1

    txid = result.get("result")

    if not txid:
        print(
            f"Error: RPC response did not contain a transaction ID:\n"
            f"{response_body}",
            file=sys.stderr,
        )
        return 1

    print(txid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
