#!/usr/bin/env python3

import json
import os
import subprocess
import getpass
from collections import defaultdict
from decimal import Decimal, ROUND_UP


# ============================================================
# Configuration
# ============================================================

SMALL_THRESHOLD = Decimal("50.0")

# Small UTXOs and anchors must have the same minimum
# confirmation requirement.
MIN_CONFIRMATIONS = 5

# An anchor must be at least this large.
MIN_ANCHOR_AMOUNT = Decimal("50.0")

# An address must own at least this much total PINK
# to be considered for consolidation.
MIN_ADDRESS_BALANCE = Decimal("5.0")

# Maximum total inputs in one transaction.
MAX_INPUTS = 650

FEE_PER_KB = Decimal("0.01")
FEE_QUANTUM = Decimal("0.01")


def calculate_fee(size_bytes):
    fee = (Decimal(size_bytes) / Decimal("1000")) * FEE_PER_KB
    return fee.quantize(FEE_QUANTUM, rounding=ROUND_UP)

# Directory where unsigned raw transactions are saved.
RAW_TX_DIRECTORY = os.path.expanduser(
    "~/.pink2/consolidator-signed-txs"
)
os.makedirs(RAW_TX_DIRECTORY, mode=0o700, exist_ok=True)


# ============================================================
# Helpers
# ============================================================

def pink_staker_rpc(command, *args):
    cmd = ["pink2d", command] + [str(x) for x in args]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"pink2d {command} failed:\n"
            f"{result.stderr.strip()}"
        )


    if command == "createrawtransaction":
        return result.stdout.strip()

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"Could not parse pink2d {command} output:\n{result.stdout}"
        )


def money(value):
    return Decimal(str(value))


def format_pink(value):
    return f"{value:.8f}"


def account_for_address(address, by_address):
    accounts = sorted(
        {
            u.get("account", "")
            for u in by_address[address]
            if u.get("account", "")
        }
    )

    if len(accounts) == 1:
        return accounts[0]

    if accounts:
        return " / ".join(accounts)

    return "(no account)"


def raw_tx_filename(number, address):
    # Keep filenames simple and safe.
    safe_address = "".join(
        c for c in address
        if c.isalnum()
    )

    return os.path.join(
        RAW_TX_DIRECTORY,
        f"consolidation-{number:02d}-{safe_address}.hex"
    )


# ============================================================
# Header
# ============================================================

print()
print("Pinkcoin UTXO consolidation RAW TRANSACTION TEST")
print("=" * 60)
print()
print(
    f"Small UTXO threshold:       "
    f"< {SMALL_THRESHOLD} PINK"
)
print(
    f"Minimum confirmations:      "
    f">= {MIN_CONFIRMATIONS}"
)
print(
    f"Minimum anchor amount:      "
    f">= {MIN_ANCHOR_AMOUNT} PINK"
)
print(
    f"Minimum address balance:    "
    f">= {MIN_ADDRESS_BALANCE} PINK"
)
print(
    f"Maximum inputs/transaction: "
    f"{MAX_INPUTS}"
)
print()


# ============================================================
# Get wallet UTXOs
# ============================================================

utxos = pink_staker_rpc(
    "listunspent",
    MIN_CONFIRMATIONS,
    9999999
)

if not isinstance(utxos, list):
    raise RuntimeError("listunspent did not return an array.")

print(f"UTXOs returned by wallet: {len(utxos)}")
print()


# ============================================================
# Group UTXOs by exact address
# ============================================================

by_address = defaultdict(list)

for u in utxos:
    address = u.get("address")

    if not address:
        continue

    by_address[address].append(u)


# ============================================================
# Select consolidation candidates
# ============================================================

plans = []

for address, address_utxos in sorted(by_address.items()):

    # --------------------------------------------------------
    # Address-level balance rule.
    #
    # This is the TOTAL value owned by this address among the
    # UTXOs returned by listunspent.
    #
    # It is completely independent of the amount being
    # consolidated.
    # --------------------------------------------------------

    address_balance = sum(
        (money(u["amount"]) for u in address_utxos),
        Decimal("0")
    )

    if address_balance < MIN_ADDRESS_BALANCE:
        continue

    # --------------------------------------------------------
    # Find qualifying small UTXOs and anchors.
    # --------------------------------------------------------

    small = []
    anchors = []

    for u in address_utxos:

        amount = money(u["amount"])
        confirmations = int(u.get("confirmations", 0))

        if (
            confirmations >= MIN_CONFIRMATIONS
            and amount < SMALL_THRESHOLD
        ):
            small.append(u)

        elif (
            confirmations >= MIN_CONFIRMATIONS
            and amount >= MIN_ANCHOR_AMOUNT
        ):
            anchors.append(u)

    # Nothing small to consolidate.
    if not small:
        continue

    # --------------------------------------------------------
    # There must actually be something to consolidate.
    #
    # One qualifying UTXO by itself is not a consolidation.
    # This is what naturally excludes the mysterious 0.01 PINK
    # one-UTXO address.
    # --------------------------------------------------------

    if len(small) < 2:
        continue

    # --------------------------------------------------------
    # The small UTXOs are deterministic: smallest first.
    # --------------------------------------------------------

    small.sort(
        key=lambda u: (
            money(u["amount"]),
            u["txid"],
            int(u["vout"])
        )
    )

    # --------------------------------------------------------
    # Choose the least-confirmed qualifying anchor.
    #
    # Anchor size does not affect priority.
    # --------------------------------------------------------

    anchors.sort(
        key=lambda u: (
            int(u.get("confirmations", 0)),
            u["txid"],
            int(u["vout"])
        )
    )

    anchor = anchors[0] if anchors else None

    # --------------------------------------------------------
    # Determine how many small UTXOs fit.
    #
    # Anchor present:
    #     1 input reserved for anchor
    #     maximum 649 small inputs
    #
    # No anchor:
    #     maximum 650 small inputs
    # --------------------------------------------------------

    if anchor is not None:
        max_small_inputs = MAX_INPUTS - 1
    else:
        max_small_inputs = MAX_INPUTS

    batch_small = small[:max_small_inputs]
    remaining_small = small[max_small_inputs:]

    # --------------------------------------------------------
    # Re-check that the actual batch still contains at least
    # two small UTXOs.
    # --------------------------------------------------------

    if len(batch_small) < 2:
        continue

    small_total = sum(
        (money(u["amount"]) for u in batch_small),
        Decimal("0")
    )

    # --------------------------------------------------------
    # The 5-PINK rule is an ADDRESS rule, not a consolidation
    # amount rule. It was already checked above.
    #
    # This output is simply the provisional test output:
    #
    #     total inputs
    #
    # The final fee calculation will replace this later.
    # --------------------------------------------------------

    anchor_amount = (
        money(anchor["amount"])
        if anchor is not None
        else Decimal("0")
    )

    total_input = small_total + anchor_amount

    provisional_output = total_input

    if provisional_output <= 0:
        raise RuntimeError(
            f"Provisional output would be non-positive for "
            f"{address}"
        )

    plans.append({
        "address": address,
        "address_balance": address_balance,
        "small": batch_small,
        "anchor": anchor,
        "small_total": small_total,
        "anchor_amount": anchor_amount,
        "total_input": total_input,
        "provisional_output": provisional_output,
        "remaining_small": len(remaining_small),
        "remaining_anchors": max(0, len(anchors) - 1),
    })


# ============================================================
# Create output directory
# ============================================================

os.makedirs(
    RAW_TX_DIRECTORY,
    mode=0o700,
    exist_ok=True
)


# ============================================================
# Create unsigned raw transactions
# ============================================================

print("=" * 60)
print("RAW TRANSACTION CREATION")
print("=" * 60)
print()

if not plans:
    print("No addresses currently have eligible consolidation batches.")
    print()

created = []

for number, plan in enumerate(plans, 1):

    address = plan["address"]
    account = account_for_address(address, by_address)

    small = plan["small"]
    anchor = plan["anchor"]

    # --------------------------------------------------------
    # Build the raw transaction input list.
    # --------------------------------------------------------

    selected_inputs = []

    for u in small:
        selected_inputs.append({
            "txid": u["txid"],
            "vout": int(u["vout"]),
        })

    if anchor is not None:
        selected_inputs.append({
            "txid": anchor["txid"],
            "vout": int(anchor["vout"]),
        })

    # --------------------------------------------------------
    # Build exactly ONE output to the same address.
    # --------------------------------------------------------

    outputs = {
        address: float(plan["provisional_output"])
    }

    print(f"[{number}] {account}")
    print(f"    Address:            {address}")
    print(
        f"    Address balance:    "
        f"{format_pink(plan['address_balance'])} PINK"
    )
    print(
        f"    Small UTXOs:        "
        f"{len(small)}"
    )
    print(
        f"    Small total:        "
        f"{format_pink(plan['small_total'])} PINK"
    )

    if anchor is not None:
        print()
        print("    Anchor:")
        print(f"        txid:           {anchor['txid']}")
        print(f"        vout:           {anchor['vout']}")
        print(
            f"        amount:         "
            f"{format_pink(plan['anchor_amount'])} PINK"
        )
        print(
            f"        confirmations:  "
            f"{anchor['confirmations']}"
        )
    else:
        print()
        print("    Anchor:             NONE")
        print("    Proceeding without an anchor.")

    print()
    print(
        f"    Total inputs:       "
        f"{len(selected_inputs)}"
    )
    print(
        f"    Total input value:  "
        f"{format_pink(plan['total_input'])} PINK"
    )
    print(
        f"    Provisional output: "
        f"{format_pink(plan['provisional_output'])} PINK"
    )
    print(
        f"    Destination:        SAME ADDRESS"
    )

    # --------------------------------------------------------
    # First pass: create a zero-fee transaction and sign it
    # solely so we can measure its exact serialized size.
    # --------------------------------------------------------

    raw_hex = pink_staker_rpc(
        "createrawtransaction",
        json.dumps(selected_inputs, separators=(",", ":")),
        json.dumps(outputs, separators=(",", ":"))
    )

    if not isinstance(raw_hex, str) or not raw_hex:
        raise RuntimeError(
            f"createrawtransaction returned an invalid result "
            f"for {address}"
        )

    if len(raw_hex) % 2 != 0:
        raise RuntimeError(
            f"createrawtransaction returned odd-length hex "
            f"for {address}"
        )

    raw_size = len(raw_hex) // 2

    signed_result = pink_staker_rpc(
        "signrawtransaction",
        raw_hex
    )

    if not isinstance(signed_result, dict):
        raise RuntimeError(
            f"signrawtransaction did not return an object "
            f"for {address}"
        )

    if not signed_result.get("complete"):
        raise RuntimeError(
            f"signrawtransaction did not produce a complete "
            f"transaction for {address}"
        )

    signed_hex = signed_result.get("hex")

    if not signed_hex:
        raise RuntimeError(
            f"signrawtransaction returned no signed hex "
            f"for {address}"
        )

    if len(signed_hex) % 2 != 0:
        raise RuntimeError(
            f"signrawtransaction returned odd-length hex "
            f"for {address}"
        )

    signed_size = len(signed_hex) // 2
    required_fee = calculate_fee(signed_size)

    # --------------------------------------------------------
    # Second pass: rebuild the transaction using the exact
    # fee calculated from the signed transaction size.
    # --------------------------------------------------------

    final_output = plan["total_input"] - required_fee

    if final_output <= 0:
        raise RuntimeError(
            f"Final output would be non-positive for {address}"
        )

    outputs = {
        address: float(final_output)
    }

    raw_hex = pink_staker_rpc(
        "createrawtransaction",
        json.dumps(selected_inputs, separators=(",", ":")),
        json.dumps(outputs, separators=(",", ":"))
    )

    if not isinstance(raw_hex, str) or not raw_hex:
        raise RuntimeError(
            f"createrawtransaction returned an invalid result "
            f"for {address} on final pass"
        )

    if len(raw_hex) % 2 != 0:
        raise RuntimeError(
            f"createrawtransaction returned odd-length hex "
            f"for {address} on final pass"
        )

    raw_size = len(raw_hex) // 2

    final_signed_result = pink_staker_rpc(
        "signrawtransaction",
        raw_hex
    )

    if not isinstance(final_signed_result, dict):
        raise RuntimeError(
            f"Final signrawtransaction did not return an object "
            f"for {address}"
        )

    if not final_signed_result.get("complete"):
        raise RuntimeError(
            f"Final signrawtransaction did not produce a complete "
            f"transaction for {address}"
        )

    final_signed_hex = final_signed_result.get("hex")

    if not final_signed_hex:
        raise RuntimeError(
            f"Final signrawtransaction returned no signed hex "
            f"for {address}"
        )

    if len(final_signed_hex) % 2 != 0:
        raise RuntimeError(
            f"Final signrawtransaction returned odd-length hex "
            f"for {address}"
        )

    final_signed_size = len(final_signed_hex) // 2
    final_required_fee = calculate_fee(final_signed_size)
    actual_fee = plan["total_input"] - final_output

    if actual_fee != final_required_fee:
        raise RuntimeError(
            f"Final fee mismatch for {address}: "
            f"actual {format_pink(actual_fee)} PINK, "
            f"required {format_pink(final_required_fee)} PINK"
        )

    # --------------------------------------------------------
    # Save the final unsigned transaction temporarily so it
    # can be decoded and verified below.
    # --------------------------------------------------------

    output_path = raw_tx_filename(number, address)
    signed_output_path = output_path.replace(
        ".hex",
        ".signed.hex"
    )

    with open(output_path, "w", encoding="ascii") as f:
        f.write(raw_hex)
        f.write("\n")

    os.chmod(output_path, 0o600)

    with open(signed_output_path, "w", encoding="ascii") as f:
        f.write(final_signed_hex)
        f.write("\n")

    os.chmod(signed_output_path, 0o600)

    # --------------------------------------------------------
    # Decode the final unsigned transaction immediately so we
    # can verify what pink2d actually constructed.
    # --------------------------------------------------------

    decoded = pink_staker_rpc(
        "decoderawtransaction",
        raw_hex
    )

    if not isinstance(decoded, dict):
        raise RuntimeError(
            f"decoderawtransaction did not return an object "
            f"for {address}"
        )

    decoded_inputs = decoded.get("vin", [])
    decoded_outputs = decoded.get("vout", [])

    if len(decoded_inputs) != len(selected_inputs):
        raise RuntimeError(
            f"Decoded input count mismatch for {address}: "
            f"expected {len(selected_inputs)}, "
            f"got {len(decoded_inputs)}"
        )

    if len(decoded_outputs) != 1:
        raise RuntimeError(
            f"Decoded output count mismatch for {address}: "
            f"expected 1, got {len(decoded_outputs)}"
        )

    print()
    print(
        f"    UNSIGNED RAW SIZE:   "
        f"{raw_size} bytes"
    )
    print(
        f"    SIGNED RAW SIZE:     "
        f"{final_signed_size} bytes"
    )
    print(
        f"    Calculated fee:      "
        f"{format_pink(final_required_fee)} PINK"
    )
    print(
        f"    Final output:        "
        f"{format_pink(final_output)} PINK"
    )
    print(
        f"    Saved signed to:     "
        f"{signed_output_path}"
    )

    print()
    print("    Raw transaction verification:")
    print(
        f"        Inputs decoded:  "
        f"{len(decoded_inputs)}"
    )
    print(
        f"        Outputs decoded: "
        f"{len(decoded_outputs)}"
    )

    # --------------------------------------------------------
    # Verify every decoded input corresponds to one of the
    # selected outpoints.
    # --------------------------------------------------------

    expected_outpoints = {
        (u["txid"], int(u["vout"]))
        for u in selected_inputs
    }

    actual_outpoints = {
        (v["txid"], int(v["vout"]))
        for v in decoded_inputs
    }

    if actual_outpoints != expected_outpoints:
        raise RuntimeError(
            f"Decoded input outpoints do not match the "
            f"selected UTXOs for {address}"
        )

    print(
        "        Input outpoints: MATCH"
    )

    # --------------------------------------------------------
    # Verify that the transaction has exactly one output and
    # that it pays the intended same address.
    #
    # Pinkcoin's decoder may represent the address under
    # scriptPubKey["addresses"] depending on its version.
    # If it does, verify it. If not, still retain the decoded
    # transaction for manual inspection rather than inventing
    # an address interpretation.
    # --------------------------------------------------------

    decoded_output = decoded_outputs[0]

    decoded_script = decoded_output.get(
        "scriptPubKey",
        {}
    )

    decoded_addresses = decoded_script.get(
        "addresses",
        []
    )

    if decoded_addresses:
        if address not in decoded_addresses:
            raise RuntimeError(
                f"Decoded output does not pay the intended "
                f"same address for {address}"
            )

        print(
            "        Output address:  MATCH"
        )
    else:
        print(
            "        Output address:  "
            "decoder did not expose address list; inspect decoded TX"
        )

    # --------------------------------------------------------
    # Verify the decoded output amount when available.
    # --------------------------------------------------------

    decoded_amount = decoded_output.get("value")

    if decoded_amount is not None:
        decoded_amount = money(decoded_amount)

        if decoded_amount != final_output:
            raise RuntimeError(
                f"Decoded output amount mismatch for {address}: "
                f"expected {format_pink(final_output)}, "
                f"got {format_pink(decoded_amount)}"
            )

        print(
            "        Output amount:   MATCH"
        )

    # All transaction verification checks have passed, so the
    # temporary unsigned transaction is no longer needed.
    os.remove(output_path)

    print()
    print(
        "    *** CREATED AND SIGNED — NOT BROADCAST ***"
    )

    if plan["remaining_small"] > 0:
        print(
            f"    Small UTXOs deferred: "
            f"{plan['remaining_small']}"
        )

    if plan["remaining_anchors"] > 0:
        print(
            f"    Additional anchors: "
            f"{plan['remaining_anchors']}"
        )

    print()

    created.append({
        "address": address,
        "raw_hex": raw_hex,
        "raw_size": raw_size,
        "path": signed_output_path,
    })


# ============================================================
# Final summary
# ============================================================

print("=" * 60)
print("SUMMARY")
print("=" * 60)
print()

print(
    f"Addresses eligible:       "
    f"{len(plans)}"
)

print(
    f"Transactions created:     "
    f"{len(created)}"
)

if created:
    print()
    for item in created:
        print(
            f"    {item['address']}"
            f"  {item['raw_size']} bytes"
            f"  {item['path']}"
        )
