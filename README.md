# Pinkcoin UTXO Consolidator

A Python tool for consolidating small Pinkcoin UTXOs generated through regular staking, particularly for wallets using side staking.

## Why this exists

Consistent staking can generate a large number of small unspent transaction outputs (UTXOs) over time. Side staking can make this problem significantly worse by producing additional UTXOs across multiple staking addresses.

As the number of UTXOs grows, the wallet and node may have to process and manage an unnecessarily large number of transaction outputs. This can increase CPU usage and create other avoidable overhead.

The Pinkcoin UTXO Consolidator is designed to periodically combine eligible small UTXOs into larger outputs, reducing the total number of UTXOs while preserving address isolation.

## What it does

The consolidator:

- Finds eligible Pinkcoin UTXOs.
- Keeps UTXOs isolated by their originating address.
- Selects eligible inputs according to the consolidation rules.
- Builds a consolidation transaction for each eligible address.
- Signs the resulting transactions.
- Saves the signed transactions for later review or submission.

The core consolidator **does not broadcast transactions**.

This makes it useful as a standalone tool while also allowing it to serve as the core component of a larger automated consolidation system.

## Requirements

- Python 3
- A synchronized Pinkcoin/Pink2D wallet or staking node
- The `pink2d` executable available in the operating system's `PATH`
- A wallet capable of signing the resulting transactions

### Pink2D configuration

The Pink2D configuration must have RPC server functionality enabled and configured for the commands used by this tool.

The configuration must include:

- `server=1`
- An RPC username
- An RPC password
- An appropriate RPC listening/bind address or interface
- Any other RPC access settings required by the local Pink2D installation

The exact configuration file location and additional RPC settings may vary depending on the Pink2D installation.

## Usage

Run the consolidator with:

```bash
python3 consolidator-signer.py
```

The current implementation requires the wallet to be **completely unlocked** when the consolidator is run, because it needs to sign the generated transactions.

Signed transactions are saved by default in:

```text
~/.pink2/consolidator-signed-txs
```

If a different output directory is desired, change the `RAW_TX_DIRECTORY` variable in `consolidator-signer.py` from:

```python
RAW_TX_DIRECTORY = os.path.expanduser("~/.pink2/consolidator-signed-txs")
```

to a custom path, for example:

```python
RAW_TX_DIRECTORY = "/my/custom/folder"
```

The custom path must be enclosed in quotation marks.

If you modify the script, make sure it remains executable:

```bash
chmod +x consolidator-signer.py
```

The generated transactions are **not broadcast automatically**.

After the signed transactions have been generated, the wallet can be locked again. The wallet does **not** need to remain unlocked in order to submit an already-signed transaction.

## Submitting a signed transaction

A generated signed transaction can be submitted using:

```bash
pink2d sendrawtransaction "$(cat /path/to/transaction.signed.hex)"
```

Replace `/path/to/transaction.signed.hex` with the path to the signed transaction file you want to submit.

The transaction should be reviewed before submission.

## Safety

This tool creates and signs transactions but does not submit them to the Pinkcoin network.

Always review generated transactions before broadcasting them.

Never place wallet passwords, private keys, wallet files, RPC credentials, or other sensitive information in this repository.

## Automation

The core consolidator is intentionally separate from the automation layer.

A future wrapper can provide functionality such as:

- Scheduled execution
- Wallet unlock and password management
- Selecting and submitting a consolidation transaction
- Managing submitted transactions
- Repeating consolidation runs automatically

Keeping these functions separate allows the core consolidator to remain useful on its own while providing a foundation for a fully automated consolidation system.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for the full license text.
