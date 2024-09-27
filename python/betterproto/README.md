# betterproto

Check out [./client.py](./client.py) for the client code.

## Running the client

1. Do the general setup as described in the [root README](/README.md#general-setup).

1. Install the dependencies:

   ```bash
   poetry install
   ```

1. Generate the TypeScript code from the Protobuf definitions:

   ```bash
   poe compile
   ```

1. Run the client:

   ```bash
   poe start
   ```
