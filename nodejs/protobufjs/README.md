# protobuf.js - TypeScript

Check out [./client.ts](./client.ts) for the client code.

## Running the client

1. Do the general setup as described in the [root README](/README.md#general-setup).

1. Install the dependencies:

   ```bash
   npm install --dev
   ```

1. Generate the TypeScript code from the Protobuf definitions:

   ```bash
   npm run compile
   ```

1. Run the client:

   ```bash
   GRPC_HOST=<device_ip> npm start
   ```
