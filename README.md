# Pinkcoin UTXO Consolidator

A Python tool for consolidating small [Pinkcoin](https://with.pink/) UTXOs, typically generated through side-staking.

## Why this exists

[knifecatcher.crypto](https://x.com/MyEmpireOfShit) started staking for/with friends almost a decade ago and quickly realized and wondered why the CPU usage eventally got what he considered "disproportionately high for what it's doing." Side-staking is an easy way to to implement what is effectively "pooled staking," which is what he did. Somewhat problematically though, it also generates a large number of small unspent transaction outputs (UTXOs) over time. As the number of UTXOs grows, the wallet and node has to process and manage an unnecessarily large number of transaction outputs. This drastically increases CPU usage and creates other avoidable overhead. It gets EXTREMELEY TEDIOUS to manually use coin control to select inputs and otherwise create/send the necessary consolidation transactions.

The Pinkcoin UTXO Consolidator is designed to periodically combine eligible small UTXOs into larger outputs, reducing the total number of UTXOs while preserving address isolation. When this script is used, every address within the wallet takes a few seconds to consolidate. When knifecatcher.crypto or the user eventually automates the process, consolidation can require no manual intervention at all.

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
- [`consolidator-signer.py`](consolidator-signer.py) and [`pink-submit.py`](pink-submit.py) from this repository

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

The generated transactions are **not broadcast automatically**.

After the signed transactions have been generated, the wallet can be locked again. The wallet does **not** need to remain unlocked in order to submit an already-signed transaction.

## Submitting Signed Transactions

The generated signed transactions should be submitted using the included pink-submit.py utility for reliability. Large transactions can exceed the command-line argument limit if passed directly to pink2d, resulting in an Argument list too long error.

Before using pink-submit.py, configure the following variables in the file to match your Pinkcoin node:

```python
RPC_HOST = "127.0.0.1"
RPC_PORT = 23424
RPC_USER = "YOUR_RPC_USERNAME"
RPC_PASSWORD = "YOUR_RPC_PASSWORD"
```

Then run:

```bash
./pink-submit.py /path/to/transaction.signed.hex
```

The utility reads the signed transaction directly from the file and submits it through Pinkcoin JSON-RPC. On success, it prints the transaction ID.

pink-submit.py uses only the Python 3 standard library and requires no additional Python packages.

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
