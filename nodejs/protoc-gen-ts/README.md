# protoc-gen-ts

_Note: This client is not recommended for ubo at the moment because it doesn't support optional fields yet which makes optional fields take default value instead of being unset. It is being tracked [here](https://github.com/thesayyn/protoc-gen-ts/issues/252)._

Check out [./client.ts](./client.ts) for the client code.

## Running the client

1. Do the general setup as described in the [root README](/README.md#general-setup).

1. Install the dependencies:

   ```bash
   npm install
   ```

1. Generate the TypeScript code from the Protobuf definitions:

   ```bash
   npm run generate
   ```

1. Run the client:

   ```bash
   npm start
   ```
